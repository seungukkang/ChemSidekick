"""Find and describe external programs (xtb, CREST, ORCA, ...).

Tools declare what they need with `@tool(requires=["xtb"])`. Before such a
tool runs, `require()` finds each program; if one is missing the tool does
not start and the user sees how to install it. Other tools are unaffected.

Search order, the same for every program:
  1. config file:          [programs.xtb] path = "..."
  2. environment variable: CSK_XTB_PATH
  3. PATH
  4. conda environment:    [programs.xtb] conda_env = "csk-ext"
                           -> conda run -n csk-ext xtb
"""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from chemsidekick.core.config import Config
from chemsidekick.core.schemas import ToolError

VERSION_TIMEOUT_S = 15.0


@dataclass(frozen=True)
class ExternalProgram:
    name: str  # key used in requires=[...] and in the config file
    executable: str  # file name to look for
    version_args: tuple[str, ...] = ("--version",)
    install_hint: str = ""


@dataclass(frozen=True)
class Located:
    program: ExternalProgram
    command: tuple[str, ...]  # prefix to run it, e.g. ("/usr/bin/xtb",) or ("conda", "run", ...)
    found_by: str
    version: str | None


# Programs are registered here (or by the tool modules that need them).
PROGRAMS: dict[str, ExternalProgram] = {}


def register_program(program: ExternalProgram) -> ExternalProgram:
    PROGRAMS[program.name] = program
    return program


def env_var_name(program: ExternalProgram) -> str:
    return f"CSK_{program.name.upper().replace('-', '_')}_PATH"


def _version(command: tuple[str, ...], args: tuple[str, ...]) -> tuple[bool, str | None]:
    """Run `command --version`; return (ran successfully, first output line)."""
    try:
        proc = subprocess.run(
            [*command, *args],
            capture_output=True,
            text=True,
            timeout=VERSION_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, None
    lines = [ln.strip() for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()]
    return proc.returncode == 0, (lines[0] if lines else None)


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def locate(program: ExternalProgram, config: Config) -> Located | None:
    settings = config.programs.get(program.name)

    candidates: list[tuple[Path | None, str]] = [
        (settings.path if settings else None, "config file"),
        (
            Path(os.environ[env_var_name(program)]).expanduser()
            if os.environ.get(env_var_name(program))
            else None,
            f"${env_var_name(program)}",
        ),
        (Path(p) if (p := shutil.which(program.executable)) else None, "PATH"),
    ]
    for path, found_by in candidates:
        if path is not None and _is_executable(path):
            _, version = _version((str(path),), program.version_args)
            return Located(program, (str(path),), found_by, version)

    if settings and settings.conda_env:
        conda = os.environ.get("CONDA_EXE") or shutil.which("conda")
        if conda:
            command = (conda, "run", "--no-capture-output", "-n", settings.conda_env,
                       program.executable)  # fmt: skip
            ok, version = _version(command, program.version_args)
            if ok:
                return Located(program, command, f"conda env {settings.conda_env}", version)
    return None


def require(names: tuple[str, ...] | list[str], config: Config) -> dict[str, Located]:
    """Locate every program a tool needs, or raise ToolError with install help."""
    found: dict[str, Located] = {}
    missing: list[str] = []
    for name in names:
        program = PROGRAMS.get(name)
        if program is None:
            raise ToolError(f"This tool needs {name!r}, which ChemSidekick does not know about.")
        located = locate(program, config)
        if located is None:
            hint = f" Install: {program.install_hint}" if program.install_hint else ""
            missing.append(f"{name} was not found.{hint}")
        else:
            found[name] = located
    if missing:
        raise ToolError(" ".join(missing) + " Run `csk doctor` for details.")
    return found


def doctor(config: Config) -> list[tuple[ExternalProgram, Located | None]]:
    """Status of every registered program."""
    return [(p, locate(p, config)) for p in sorted(PROGRAMS.values(), key=lambda p: p.name)]
