"""The JSON contract between ChemSidekick and its interfaces (Raycast now, HTTP later).

With `--json`, every csk command prints exactly one JSON object on stdout:

    {"contract": 1, "csk_version": "...", "ok": true,  ...}   success
    {"contract": 1, "csk_version": "...", "ok": false, "error": {...}}   failure

The models below define those objects. A local API (v0.3) will return the same
objects over HTTP, so an interface can switch from running csk to calling the
API without changing its screens.

Versioning: CONTRACT_VERSION changes only when a field is removed or renamed, or
its meaning changes. Adding fields, error types, tools, or artifact kinds keeps
the version; readers must ignore what they do not know. The JSON Schemas in
schemas/contract-v<N>/ are generated from these models (scripts/export_contract.py)
and a test fails if they drift.
"""

import traceback as tb
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from chemsidekick import __version__
from chemsidekick.core.config import Config, ConfigError
from chemsidekick.core.external import MissingProgram, require
from chemsidekick.core.registry import CATEGORIES, ToolSpec
from chemsidekick.core.runner import (
    ConfirmationRequired,
    ResourceLimitExceeded,
    RunError,
    ToolCrashed,
)
from chemsidekick.core.schemas import Frame, ToolError, ToolResult

CONTRACT_VERSION = 1

ErrorType = Literal["input", "limit", "crash", "confirm", "missing_program", "config"]

# Exit codes of csk commands. 2 is Typer's own code for command-line usage errors
# (unknown option, missing argument); those are printed as text, never as JSON.
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_CODES: dict[str, int] = {
    "input": 1,
    "limit": 3,
    "crash": 4,
    "confirm": 5,
    "missing_program": 6,
    "config": 7,
}


class _Envelope(BaseModel):
    contract: int = CONTRACT_VERSION
    # A factory, not a default, so the JSON Schema does not change with every release.
    csk_version: str = Field(default_factory=lambda: __version__)


# ---------------------------------------------------------------------------
# Running a tool
# ---------------------------------------------------------------------------


class RunInfo(BaseModel):
    tool: str
    tool_id: str
    # Number in the recent-results store (for `csk save <number>`); None with --no-record.
    number: int | None
    folder: str  # absolute path of the folder holding the result's files
    recorded: bool
    elapsed_s: float
    peak_memory_mb: float | None  # measured only for medium/heavy tools


class RunResponse(_Envelope):
    ok: Literal[True] = True
    result: ToolResult
    run: RunInfo


class ErrorDetail(BaseModel):
    field: str = ""  # input field, e.g. "max_isomers"; "" if not about one field
    message: str


class ErrorInfo(BaseModel):
    type: ErrorType
    message: str  # meant for the user, shown as-is
    details: list[ErrorDetail] = []
    traceback: str = ""  # only for "crash"


class ErrorResponse(_Envelope):
    ok: Literal[False] = False
    error: ErrorInfo


# ---------------------------------------------------------------------------
# Listing tools
# ---------------------------------------------------------------------------


class CategoryInfo(BaseModel):
    name: str
    code: str
    title: str


class ToolInfo(BaseModel):
    id: str
    name: str
    title: str
    summary: str
    category: str
    keywords: list[str]
    resources: Literal["light", "medium", "heavy"]
    requires: list[str]
    available: bool  # every program in `requires` was found
    unavailable_reason: str = ""
    icon: str = ""
    start_view: str = ""
    # JSON Schema of the tool's input model. Display hints are in each property:
    # label, positional, multiline, file_input, flag, short.
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ToolListResponse(_Envelope):
    ok: Literal[True] = True
    categories: list[CategoryInfo]
    tools: list[ToolInfo]


# ---------------------------------------------------------------------------
# Saving a recent result
# ---------------------------------------------------------------------------


class SaveResponse(_Envelope):
    ok: Literal[True] = True
    number: int
    saved_to: str  # absolute path of the saved copy


# ---------------------------------------------------------------------------
# Rotating 3D view (`csk gif`): a view of a result's structure, not a tool
# ---------------------------------------------------------------------------


class GifRequest(BaseModel):
    """Input of `csk gif`, as JSON on standard input."""

    model_config = ConfigDict(extra="forbid")
    frame: Frame  # one frame of a result's Structure3D (symbols, coords in Å, comment)
    # One wide card: the 2D drawing from bonds inferred from the coordinates on
    # the left, the rotating view on the right (for xyz results).
    beside_2d: bool = False


class GifResponse(_Envelope):
    ok: Literal[True] = True
    path: str  # absolute path of the animated GIF (a fresh file every time)
    frames: int


# ---------------------------------------------------------------------------
# Building responses
# ---------------------------------------------------------------------------


def tool_info(spec: ToolSpec, config: Config) -> ToolInfo:
    available, reason = True, ""
    if spec.requires:
        try:
            require(spec.requires, config)
        except MissingProgram as e:
            available, reason = False, str(e)
    return ToolInfo(
        id=spec.id,
        name=spec.name,
        title=spec.title,
        summary=spec.summary,
        category=spec.category,
        keywords=list(spec.keywords),
        resources=spec.resources,
        requires=list(spec.requires),
        available=available,
        unavailable_reason=reason,
        icon=spec.icon,
        start_view=spec.start_view,
        input_schema=spec.input_model.model_json_schema(),
    )


def tool_list(specs: list[ToolSpec], config: Config) -> ToolListResponse:
    return ToolListResponse(
        categories=[
            CategoryInfo(name=n, code=c.code, title=c.title) for n, c in CATEGORIES.items()
        ],
        tools=[tool_info(s, config) for s in specs],
    )


def error_info(e: BaseException) -> ErrorInfo:
    """Classify an exception into the contract's error types."""
    if isinstance(e, ValidationError):
        details = [
            ErrorDetail(field=".".join(str(p) for p in err["loc"]), message=err["msg"])
            for err in e.errors()
        ]
        message = "; ".join(f"{d.field or 'input'}: {d.message}" for d in details)
        return ErrorInfo(type="input", message=message, details=details)
    if isinstance(e, MissingProgram):  # before ToolError: it is a subclass
        return ErrorInfo(type="missing_program", message=str(e))
    if isinstance(e, ToolError):
        return ErrorInfo(type="input", message=str(e))
    if isinstance(e, ConfirmationRequired):
        return ErrorInfo(type="confirm", message=str(e))
    if isinstance(e, ResourceLimitExceeded):
        return ErrorInfo(type="limit", message=str(e))
    if isinstance(e, ConfigError):
        return ErrorInfo(type="config", message=str(e))
    if isinstance(e, ToolCrashed):
        # "the tool crashed:\n<traceback from the child process>"
        message, _, trace = str(e).partition("\n")
        return ErrorInfo(type="crash", message=message.rstrip(":"), traceback=trace)
    if isinstance(e, RunError):
        return ErrorInfo(type="crash", message=str(e))
    trace = "".join(tb.format_exception(e))
    return ErrorInfo(type="crash", message=f"{type(e).__name__}: {e}", traceback=trace)


def exit_code(error_type: str) -> int:
    return EXIT_CODES[error_type]
