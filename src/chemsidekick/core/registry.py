"""Tool registry: the @tool decorator, tool discovery, and search.

A tool is a plain function that takes one Pydantic input model and returns a
ToolResult. The decorator attaches a label (name, category, resources, ...)
and stores the function in a registry. Interfaces (CLI, UI) only read the
registry, so adding a tool never requires changing interface code.
"""

import importlib
import pkgutil
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, get_args, get_type_hints

from pydantic import BaseModel

from chemsidekick.core.schemas import ToolResult

# Category id -> display name (UI tab). Add one line here for a new category.
CATEGORIES: dict[str, str] = {
    "structure": "Structure",
    "reference": "Reference",
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
    title: str
    summary: str
    category: str
    keywords: tuple[str, ...]
    resources: Resources
    requires: tuple[str, ...]
    input_model: type[BaseModel]
    func: ToolFunc

    def run(self, inp: BaseModel) -> ToolResult:
        return self.func(inp)


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    # -- registration -------------------------------------------------------

    def tool(
        self,
        *,
        name: str,
        title: str,
        summary: str,
        category: str,
        keywords: list[str] | tuple[str, ...] = (),
        resources: Resources = "light",
        requires: list[str] | tuple[str, ...] = (),
    ) -> Callable[[ToolFunc], ToolFunc]:
        """Decorator that registers a tool function."""

        def decorator(func: ToolFunc) -> ToolFunc:
            spec = ToolSpec(
                name=name,
                title=title,
                summary=summary,
                category=category,
                keywords=tuple(keywords),
                resources=resources,
                requires=tuple(requires),
                input_model=_input_model_of(func),
                func=func,
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
        self._tools[spec.name] = spec

    # -- lookup -------------------------------------------------------------

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(f"no tool named {name!r}") from None

    def all(self) -> list[ToolSpec]:
        return sorted(self._tools.values(), key=lambda s: s.name)

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
        scored.sort(key=lambda pair: (-pair[0], pair[1].name))
        return [spec for _, spec in scored]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)


def _score(spec: ToolSpec, q: str) -> int:
    """Search relevance: name > keyword > title > summary. 0 means no match."""
    keywords = [k.lower() for k in spec.keywords]
    if spec.name == q:
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
