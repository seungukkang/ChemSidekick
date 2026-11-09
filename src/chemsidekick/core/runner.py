"""Run tools within their declared resource level.

    light   same process; a warning if it is slower than expected
    medium  separate process; killed if it exceeds time, memory limits
    heavy   like medium, but only after the user confirms

macOS does not enforce per-process memory limits (RLIMIT_AS), so the
parent process watches the child's memory with psutil and kills it when
it goes over. CPU use is limited through the thread-count environment
variables that most scientific libraries respect.
"""

import multiprocessing as mp
import os
import tempfile
import time
import traceback
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

import psutil
from pydantic import BaseModel

from chemsidekick.core.config import Config
from chemsidekick.core.external import require
from chemsidekick.core.registry import ToolFunc, ToolSpec
from chemsidekick.core.schemas import ToolError, ToolResult


@dataclass(frozen=True)
class Limits:
    cpus: int
    memory_mb: int
    timeout_s: float | None  # None: no default; the tool or the user must give one


# To be tuned with measurements on the reference machine (M1 Pro, 16 GB).
LIMITS: dict[str, Limits] = {
    "light": Limits(cpus=1, memory_mb=256, timeout_s=5.0),
    "medium": Limits(cpus=2, memory_mb=1024, timeout_s=60.0),
    "heavy": Limits(cpus=4, memory_mb=4096, timeout_s=None),
}

THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "RAYON_NUM_THREADS",
)

POLL_INTERVAL_S = 0.2


class RunError(Exception):
    """The tool could not finish (not the user's input's fault)."""


class ResourceLimitExceeded(RunError):
    pass


class ConfirmationRequired(RunError):
    """A heavy tool was started without the user's confirmation."""


class ToolCrashed(RunError):
    pass


@dataclass(frozen=True)
class RunOutcome:
    result: ToolResult
    elapsed_s: float
    peak_memory_mb: float | None  # measured only for medium/heavy


# ---------------------------------------------------------------------------
# Working directory for files a tool writes (SVG, SDF, ...)
# ---------------------------------------------------------------------------

_WORKDIR: ContextVar[Path | None] = ContextVar("chemsidekick_workdir", default=None)


def workdir() -> Path:
    """The folder where the running tool should write its files.

    Inside the runner this is the result's folder in the recent-results store.
    When a tool is called directly (e.g. in tests) a temporary folder is used.
    """
    current = _WORKDIR.get()
    if current is None:
        current = Path(tempfile.mkdtemp(prefix="chemsidekick-"))
        _WORKDIR.set(current)
    return current


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def effective_limits(spec: ToolSpec, inp: BaseModel, timeout_s: float | None) -> Limits:
    """The limits for this run: user override > tool's own estimate > level default."""
    base = LIMITS[spec.resources]
    timeout = timeout_s
    if timeout is None and spec.timeout is not None:
        timeout = spec.timeout(inp)
    if timeout is None:
        timeout = base.timeout_s
    return Limits(cpus=base.cpus, memory_mb=base.memory_mb, timeout_s=timeout)


def run_tool(
    spec: ToolSpec,
    inp: BaseModel,
    *,
    workdir: Path,
    config: Config | None = None,
    timeout_s: float | None = None,
    confirmed: bool = False,
    limits: Limits | None = None,
) -> RunOutcome:
    """Run one tool with the limits of its resource level.

    Raises ToolError (bad input, missing program), ConfirmationRequired,
    ResourceLimitExceeded, or ToolCrashed.
    """
    require(spec.requires, config or Config())
    if spec.resources == "heavy" and not confirmed:
        raise ConfirmationRequired(f"{spec.title} is a heavy tool and needs confirmation.")
    limits = limits or effective_limits(spec, inp, timeout_s)
    if spec.resources == "heavy" and limits.timeout_s is None:
        raise ToolError(f"{spec.title} needs a time limit: pass --timeout <seconds>.")

    if spec.resources == "light":
        return _run_in_process(spec.func, inp, workdir, limits)
    return _run_in_subprocess(spec.func, inp, workdir, limits)


def _run_in_process(func: ToolFunc, inp: BaseModel, wd: Path, limits: Limits) -> RunOutcome:
    token = _WORKDIR.set(wd)
    start = time.perf_counter()
    try:
        result = func(inp)
    finally:
        _WORKDIR.reset(token)
    elapsed = time.perf_counter() - start
    if limits.timeout_s is not None and elapsed > limits.timeout_s:
        result = result.model_copy(
            update={
                "warnings": [
                    *result.warnings,
                    f"Took {elapsed:.1f} s, longer than the {limits.timeout_s:g} s "
                    "expected for a light tool.",
                ]
            }
        )
    return RunOutcome(result=result, elapsed_s=elapsed, peak_memory_mb=None)


def _child_main(func: ToolFunc, inp: BaseModel, wd: Path, cpus: int, conn) -> None:
    """Runs in the child process."""
    for var in THREAD_ENV_VARS:
        os.environ[var] = str(cpus)
    _WORKDIR.set(wd)
    try:
        result = func(inp)
        conn.send(("ok", result.model_dump_json()))
    except ToolError as e:
        conn.send(("tool_error", str(e)))
    except BaseException:
        conn.send(("crash", traceback.format_exc()))
    finally:
        conn.close()


def _rss_mb(proc: psutil.Process) -> float:
    """Resident memory of a process and all its children, in MB."""
    try:
        procs = [proc, *proc.children(recursive=True)]
    except psutil.NoSuchProcess:
        return 0.0
    total = 0
    for p in procs:
        try:
            total += p.memory_info().rss
        except psutil.NoSuchProcess:
            pass
    return total / 1e6


def _kill_tree(proc: psutil.Process) -> None:
    try:
        procs = [*proc.children(recursive=True), proc]
    except psutil.NoSuchProcess:
        return
    for p in procs:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass


def _run_in_subprocess(func: ToolFunc, inp: BaseModel, wd: Path, limits: Limits) -> RunOutcome:
    ctx = mp.get_context("spawn")
    receiver, sender = ctx.Pipe(duplex=False)
    child = ctx.Process(target=_child_main, args=(func, inp, wd, limits.cpus, sender), daemon=True)
    start = time.perf_counter()
    child.start()
    sender.close()  # only the child writes
    proc = psutil.Process(child.pid)
    peak = 0.0
    try:
        while True:
            if receiver.poll(POLL_INTERVAL_S):
                try:
                    status, payload = receiver.recv()
                except EOFError:
                    child.join(timeout=5)
                    raise ToolCrashed(
                        f"the tool process exited unexpectedly (code {child.exitcode})"
                    ) from None
                break
            if not child.is_alive():
                raise ToolCrashed(f"the tool process exited unexpectedly (code {child.exitcode})")
            peak = max(peak, _rss_mb(proc))
            if peak > limits.memory_mb:
                _kill_tree(proc)
                raise ResourceLimitExceeded(f"stopped: memory use exceeded {limits.memory_mb} MB")
            elapsed = time.perf_counter() - start
            if limits.timeout_s is not None and elapsed > limits.timeout_s:
                _kill_tree(proc)
                raise ResourceLimitExceeded(
                    f"stopped: took longer than {limits.timeout_s:g} s "
                    "(use --timeout to allow more time)"
                )
    finally:
        receiver.close()
        child.join(timeout=5)
        if child.is_alive():
            _kill_tree(proc)

    elapsed = time.perf_counter() - start
    if status == "ok":
        return RunOutcome(
            result=ToolResult.model_validate_json(payload),
            elapsed_s=elapsed,
            peak_memory_mb=round(peak, 1),
        )
    if status == "tool_error":
        raise ToolError(payload)
    raise ToolCrashed(f"the tool crashed:\n{payload}")
