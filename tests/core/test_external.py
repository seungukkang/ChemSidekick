import pytest

from chemsidekick.core.config import Config, ProgramConfig
from chemsidekick.core.external import (
    PROGRAMS,
    ExternalProgram,
    doctor,
    env_var_name,
    locate,
    require,
)
from chemsidekick.core.schemas import ToolError

PROG = ExternalProgram("fakeprog", "fakeprog", install_hint="install fakeprog")


def make_exe(folder, name, version):
    folder.mkdir(parents=True, exist_ok=True)
    exe = folder / name
    exe.write_text(f"#!/bin/sh\necho '{version}'\n")
    exe.chmod(0o755)
    return exe


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.delenv(env_var_name(PROG), raising=False)
    monkeypatch.delenv("CONDA_EXE", raising=False)
    return tmp_path


def test_not_found(clean_env):
    assert locate(PROG, Config()) is None


def test_found_on_path(clean_env, monkeypatch):
    make_exe(clean_env / "bin", "fakeprog", "fakeprog 1.0 (path)")
    monkeypatch.setenv("PATH", f"{clean_env / 'bin'}:/usr/bin:/bin")
    found = locate(PROG, Config())
    assert found.found_by == "PATH"
    assert found.version == "fakeprog 1.0 (path)"


def test_search_order_config_then_env_then_path(clean_env, monkeypatch):
    on_path = make_exe(clean_env / "bin", "fakeprog", "path")
    in_env = make_exe(clean_env / "env", "fakeprog", "env")
    in_cfg = make_exe(clean_env / "cfg", "fakeprog", "cfg")
    monkeypatch.setenv("PATH", f"{on_path.parent}:/usr/bin:/bin")
    monkeypatch.setenv("CSK_FAKEPROG_PATH", str(in_env))
    cfg = Config(programs={"fakeprog": ProgramConfig(path=in_cfg)})

    assert locate(PROG, cfg).version == "cfg"
    assert locate(PROG, Config()).version == "env"
    monkeypatch.delenv("CSK_FAKEPROG_PATH")
    assert locate(PROG, Config()).version == "path"


def test_conda_env(clean_env, monkeypatch):
    # A fake `conda` that just runs the command after "run --no-capture-output -n <env>".
    conda = clean_env / "conda"
    conda.write_text('#!/bin/sh\nshift 4\necho "fakeprog via conda"\n')
    conda.chmod(0o755)
    monkeypatch.setenv("CONDA_EXE", str(conda))
    cfg = Config(programs={"fakeprog": ProgramConfig(conda_env="csk-ext")})
    found = locate(PROG, cfg)
    assert found.found_by == "conda env csk-ext"
    assert found.command[-3:] == ("-n", "csk-ext", "fakeprog")
    assert found.version == "fakeprog via conda"


def test_require_reports_install_hint(clean_env, monkeypatch):
    monkeypatch.setitem(PROGRAMS, "fakeprog", PROG)
    with pytest.raises(ToolError, match="fakeprog was not found. Install: install fakeprog"):
        require(["fakeprog"], Config())
    with pytest.raises(ToolError, match="does not know about"):
        require(["unknown-program"], Config())


def test_doctor_lists_registered_programs(clean_env, monkeypatch):
    monkeypatch.setattr("chemsidekick.core.external.PROGRAMS", {"fakeprog": PROG})
    assert doctor(Config()) == [(PROG, None)]
