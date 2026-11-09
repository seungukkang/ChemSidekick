"""Tool registry: the @tool decorator, tool discovery, and search.

A tool is a plain function that takes one Pydantic input model and returns a
ToolResult. The decorator attaches a label (name, ID, category, resources, ...)
and stores the function in a registry. Interfaces (CLI, UI) only read the
registry, so adding a tool never requires changing interface code.

Every tool has a permanent ID: <category code>-<number>, e.g. REF-01.
Numbers are never reused, even if a tool is removed.
"""

import importlib
import pkgutil
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, get_args, get_type_hints

from pydantic import BaseModel

from chemsidekick.core.schemas import ToolResult


@dataclass(frozen=True)
class Category:
    code: str  # three capital letters, used in tool IDs
    title: str  # display name (UI tab)


# Add one line here for a new category. Codes must never change.
CATEGORIES: dict[str, Category] = {
    "structure": Category("STR", "Structure"),
    "reference": Category("REF", "Reference"),
}

Resources = Literal["light", "medium", "heavy"]
RESOURCE_LEVELS: tuple[str, ...] = get_args(Resources)

# Built-in CLI commands. A tool cannot use these names.
RESERVED_NAMES = frozenset({"list", "search", "doctor", "ui", "recent", "save", "help"})

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")

ToolFunc = Callable[[BaseModel], ToolResult]


class RegistryError(Exception):
    """A tool was declared incorrectly."""


@dataclass(frozen=True)
class ToolSpec:
    """Everything an interface needs to know about one tool."""

    name: str
    number: int
    title: str
    summary: str
    category: str
    keywords: tuple[str, ...]
    resources: Resources
    requires: tuple[str, ...]
    input_model: type[BaseModel]
    func: ToolFunc
    # Optional: time limit (s) computed from the input, e.g. more isomers -> more time.
    timeout: Callable[[BaseModel], float] | None = None
    # Optional: Material Symbols icon name for the UI grid, e.g. "science".
    icon: str = ""
    # Optional: name of the view shown when the tool is opened in the UI. If set,
    # the tool runs once with its default input (light tools only), e.g. the
    # element tool shows the periodic table.
    start_view: str = ""

    @property
    def id(self) -> str:
        return f"{CATEGORIES[self.category].code}-{self.number:02d}"

    def run(self, inp: BaseModel) -> ToolResult:
        """Call the tool directly, without resource limits (see core/runner.py)."""
        return self.func(inp)


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    # -- registration -------------------------------------------------------

    def tool(
        self,
        *,
        name: str,
        number: int,
        title: str,
        summary: str,
        category: str,
        keywords: list[str] | tuple[str, ...] = (),
        resources: Resources = "light",
        requires: list[str] | tuple[str, ...] = (),
        timeout: Callable[[BaseModel], float] | None = None,
        icon: str = "",
        start_view: str = "",
    ) -> Callable[[ToolFunc], ToolFunc]:
        """Decorator that registers a tool function."""

        def decorator(func: ToolFunc) -> ToolFunc:
            spec = ToolSpec(
                name=name,
                number=number,
                title=title,
                summary=summary,
                category=category,
                keywords=tuple(keywords),
                resources=resources,
                requires=tuple(requires),
                input_model=_input_model_of(func),
                func=func,
                timeout=timeout,
                icon=icon,
                start_view=start_view,
            )
            self.register(spec)
            return func

        return decorator

    def register(self, spec: ToolSpec) -> None:
        if not _NAME_PATTERN.match(spec.name):
            raise RegistryError(
                f"tool name {spec.name!r} must be lowercase letters, digits, or '-'"
            )
        if spec.name in RESERVED_NAMES:
            raise RegistryError(f"tool name {spec.name!r} is reserved for a built-in command")
        if spec.name in self._tools:
            raise RegistryError(f"tool name {spec.name!r} is already registered")
        if spec.category not in CATEGORIES:
            raise RegistryError(
                f"tool {spec.name!r}: unknown category {spec.category!r} "
                f"(known: {', '.join(CATEGORIES)})"
            )
        if spec.resources not in RESOURCE_LEVELS:
            raise RegistryError(
                f"tool {spec.name!r}: resources must be one of {', '.join(RESOURCE_LEVELS)}"
            )
        if spec.start_view and spec.resources != "light":
            raise RegistryError(f"tool {spec.name!r}: start_view is only allowed for light tools")
        if not 1 <= spec.number <= 99:
            raise RegistryError(f"tool {spec.name!r}: number must be between 1 and 99")
        for other in self._tools.values():
            if other.id == spec.id:
                raise RegistryError(
                    f"tool {spec.name!r}: ID {spec.id} is already used by {other.name!r}"
                )
        self._tools[spec.name] = spec

    # -- lookup -------------------------------------------------------------

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(f"no tool named {name!r}") from None

    def all(self) -> list[ToolSpec]:
        """All tools, ordered by ID (category order, then number)."""
        order = list(CATEGORIES)
        return sorted(self._tools.values(), key=lambda s: (order.index(s.category), s.number))

    def by_id(self, tool_id: str) -> ToolSpec:
        for spec in self._tools.values():
            if spec.id == tool_id.upper():
                return spec
        raise KeyError(f"no tool with ID {tool_id!r}")

    def by_category(self) -> dict[str, list[ToolSpec]]:
        """Tools grouped by category, in CATEGORIES order. Empty categories are omitted."""
        groups: dict[str, list[ToolSpec]] = {}
        for cat in CATEGORIES:
            members = [s for s in self.all() if s.category == cat]
            if members:
                groups[cat] = members
        return groups

    def search(self, query: str) -> list[ToolSpec]:
        """Tools matching `query`, best match first. An empty query returns all tools."""
        q = query.strip().lower()
        if not q:
            return self.all()
        scored = [(score, spec) for spec in self._tools.values() if (score := _score(spec, q))]
        scored.sort(key=lambda pair: (-pair[0], pair[1].id))
        return [spec for _, spec in scored]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)


def _score(spec: ToolSpec, q: str) -> int:
    """Search relevance: name > keyword > title > summary. 0 means no match."""
    keywords = [k.lower() for k in spec.keywords]
    if spec.name == q or spec.id.lower() == q:
        return 100
    if spec.name.startswith(q):
        return 80
    if q in keywords:
        return 60
    if any(q in k for k in keywords):
        return 40
    if q in spec.title.lower():
        return 30
    if q in spec.summary.lower():
        return 10
    return 0


def _input_model_of(func: ToolFunc) -> type[BaseModel]:
    """Read the input model from the tool's type hints and check the signature."""
    hints = get_type_hints(func)
    params = [p for p in hints if p != "return"]
    if len(params) != 1:
        raise RegistryError(f"tool function {func.__name__}() must take exactly one argument")
    model = hints[params[0]]
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        raise RegistryError(
            f"tool function {func.__name__}(): the argument must be annotated with a Pydantic model"
        )
    if hints.get("return") is not ToolResult:
        raise RegistryError(f"tool function {func.__name__}() must be annotated -> ToolResult")
    return model


# ---------------------------------------------------------------------------
# The default registry used by the real tools and interfaces
# ---------------------------------------------------------------------------

REGISTRY = Registry()
tool = REGISTRY.tool

_discovered = False


def discover(package: str = "chemsidekick.tools") -> Registry:
    """Import every module under `package` so that their @tool decorators run."""
    global _discovered
    if not _discovered:
        pkg = importlib.import_module(package)
        for info in pkgutil.walk_packages(pkg.__path__, prefix=f"{package}."):
            importlib.import_module(info.name)
        _discovered = True
    return REGISTRY
