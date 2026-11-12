"""Fake tools that fail in every way the JSON contract reports.

Module level, because the medium tool runs in a separate process that must be
able to import it.
"""

import time

from pydantic import BaseModel

from chemsidekick.core.registry import Registry
from chemsidekick.core.schemas import ToolResult

REG = Registry()


class Seconds(BaseModel):
    seconds: float = 0.0


@REG.tool(name="ok", number=1, title="OK", summary="Always works", category="reference")
def ok(inp: Seconds) -> ToolResult:
    return ToolResult(answer="fine")


@REG.tool(name="boom", number=2, title="Boom", summary="Has a bug", category="reference")
def boom(inp: Seconds) -> ToolResult:
    raise RuntimeError("a bug in the tool")


@REG.tool(name="slow", number=1, title="Slow", summary="", category="structure", resources="medium")
def slow(inp: Seconds) -> ToolResult:
    time.sleep(inp.seconds)
    return ToolResult(answer="slept")


@REG.tool(name="big", number=2, title="Big", summary="", category="structure", resources="heavy")
def big(inp: Seconds) -> ToolResult:
    return ToolResult(answer="heavy done")


@REG.tool(
    name="needs-xtb",
    number=3,
    title="Needs a program",
    summary="",
    category="reference",
    requires=["not-a-real-program"],
)
def needs(inp: Seconds) -> ToolResult:
    return ToolResult(answer="unreachable")
