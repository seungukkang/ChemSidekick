import time

import pytest
from fake_tools import REG, Empty, Megabytes, Seconds

from chemsidekick.core.external import PROGRAMS, ExternalProgram
from chemsidekick.core.runner import (
    ConfirmationRequired,
    Limits,
    ResourceLimitExceeded,
    ToolCrashed,
    effective_limits,
    run_tool,
)
from chemsidekick.core.schemas import ToolError


def run(name, inp, tmp_path, **kwargs):
    return run_tool(REG.get(name), inp, workdir=tmp_path, **kwargs)


def test_light_runs_in_process(tmp_path):
    outcome = run("quick", Seconds(), tmp_path)
    assert outcome.result.answer == "done"
    assert outcome.peak_memory_mb is None


def test_light_too_slow_only_warns(tmp_path):
    outcome = run("quick", Seconds(seconds=0.3), tmp_path, timeout_s=0.1)
    assert outcome.result.answer == "done"
    assert "longer than the 0.1 s" in outcome.result.warnings[0]


def test_medium_runs_in_subprocess(tmp_path):
    outcome = run("sleeper", Seconds(seconds=0.1), tmp_path)
    assert outcome.result.answer == "slept 0.1"
    assert outcome.peak_memory_mb is not None and outcome.peak_memory_mb > 0


def test_medium_sets_thread_limit(tmp_path):
    assert run("env", Empty(), tmp_path).result.answer == "2"


def test_timeout_kills_the_tool(tmp_path):
    start = time.perf_counter()
    with pytest.raises(ResourceLimitExceeded, match="longer than 0.5 s"):
        run("sleeper", Seconds(seconds=30), tmp_path, timeout_s=0.5)
    assert time.perf_counter() - start < 5


def test_tool_can_extend_its_own_timeout():
    spec = REG.get("sleeper")
    assert effective_limits(spec, Seconds(seconds=9), None).timeout_s == 10.0
    assert effective_limits(spec, Seconds(seconds=9), 3.0).timeout_s == 3.0  # user wins


def test_memory_limit_kills_the_tool(tmp_path):
    limits = Limits(cpus=1, memory_mb=150, timeout_s=30)
    start = time.perf_counter()
    with pytest.raises(ResourceLimitExceeded, match="memory use exceeded 150 MB"):
        run("hog", Megabytes(mb=400), tmp_path, limits=limits)
    assert time.perf_counter() - start < 10


def test_files_go_to_the_workdir(tmp_path):
    outcome = run("writer", Empty(), tmp_path)
    assert outcome.result.artifacts[0].path == tmp_path / "out.xyz"
    assert (tmp_path / "out.xyz").exists()


def test_tool_error_passes_through(tmp_path):
    with pytest.raises(ToolError, match="bad input, explained"):
        run("refuser", Empty(), tmp_path)


def test_unexpected_exception_is_reported_with_traceback(tmp_path):
    with pytest.raises(ToolCrashed, match="RuntimeError: boom"):
        run("crasher", Empty(), tmp_path)


def test_process_that_dies_is_reported(tmp_path):
    with pytest.raises(ToolCrashed, match="code 3"):
        run("dier", Empty(), tmp_path)


def test_heavy_needs_confirmation_and_timeout(tmp_path):
    with pytest.raises(ConfirmationRequired):
        run("big", Empty(), tmp_path)
    with pytest.raises(ToolError, match="needs a time limit"):
        run("big", Empty(), tmp_path, confirmed=True)
    outcome = run("big", Empty(), tmp_path, confirmed=True, timeout_s=30)
    assert outcome.result.answer == "heavy done"


def test_missing_program_stops_before_running(tmp_path, monkeypatch):
    monkeypatch.setitem(
        PROGRAMS,
        "fake-xtb",
        ExternalProgram("fake-xtb", "definitely-not-installed-xtb", install_hint="brew install x"),
    )
    with pytest.raises(ToolError, match="fake-xtb was not found. Install: brew install x"):
        run("needs-xtb", Empty(), tmp_path)
