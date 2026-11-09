"""Fake tools for runner tests.

They live at module level (not inside test functions) because medium and
heavy tools run in a separate process, which must be able to import them.
"""

import os
import time

from pydantic import BaseModel

from chemsidekick.core.registry import Registry
from chemsidekick.core.runner import workdir
from chemsidekick.core.schemas import Artifact, ToolError, ToolResult

REG = Registry()


class Seconds(BaseModel):
    seconds: float = 0.0


class Megabytes(BaseModel):
    mb: int = 0


class Empty(BaseModel):
    pass


@REG.tool(name="quick", number=1, title="Quick", summary="", category="reference")
def quick(inp: Seconds) -> ToolResult:
    time.sleep(inp.seconds)
    return ToolResult(answer="done")


@REG.tool(
    name="sleeper",
    number=1,
    title="Sleeper",
    summary="",
    category="structure",
    resources="medium",
    timeout=lambda inp: 1.0 + inp.seconds,
)
def sleeper(inp: Seconds) -> ToolResult:
    time.sleep(inp.seconds)
    return ToolResult(answer=f"slept {inp.seconds}")


@REG.tool(name="hog", number=2, title="Hog", summary="", category="structure", resources="medium")
def hog(inp: Megabytes) -> ToolResult:
    block = bytearray(inp.mb * 1_000_000)  # zero-filled, so the pages are really used
    time.sleep(10)
    return ToolResult(answer=str(len(block)))


@REG.tool(name="env", number=3, title="Env", summary="", category="structure", resources="medium")
def env(inp: Empty) -> ToolResult:
    return ToolResult(answer=os.environ.get("OMP_NUM_THREADS", "unset"))


@REG.tool(
    name="writer", number=4, title="Writer", summary="", category="structure", resources="medium"
)
def writer(inp: Empty) -> ToolResult:
    path = workdir() / "out.xyz"
    path.write_text("1\n\nH 0 0 0\n")
    return ToolResult(answer="written", artifacts=[Artifact(kind="xyz", path=path)])


@REG.tool(
    name="refuser", number=5, title="Refuser", summary="", category="structure", resources="medium"
)
def refuser(inp: Empty) -> ToolResult:
    raise ToolError("bad input, explained")


@REG.tool(
    name="crasher", number=6, title="Crasher", summary="", category="structure", resources="medium"
)
def crasher(inp: Empty) -> ToolResult:
    raise RuntimeError("boom")


@REG.tool(name="dier", number=7, title="Dier", summary="", category="structure", resources="medium")
def dier(inp: Empty) -> ToolResult:
    os._exit(3)


@REG.tool(name="big", number=8, title="Big", summary="", category="structure", resources="heavy")
def big(inp: Empty) -> ToolResult:
    return ToolResult(answer="heavy done")


@REG.tool(
    name="needs-xtb",
    number=9,
    title="Needs xtb",
    summary="",
    category="structure",
    resources="medium",
    requires=["fake-xtb"],
)
def needs_xtb(inp: Empty) -> ToolResult:
    return ToolResult(answer="ran")
