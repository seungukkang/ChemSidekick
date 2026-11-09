"""User settings from ~/.config/chemsidekick/config.toml.

The file is optional: every setting has a default. Example:

    save_dir = "~/Documents/ChemSidekick"
    recent_limit = 50

    [programs.xtb]
    path = "/opt/homebrew/bin/xtb"
    # or: conda_env = "csk-ext"
"""

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

CONFIG_PATH = Path("~/.config/chemsidekick/config.toml").expanduser()


class ConfigError(Exception):
    """The config file exists but cannot be used."""


class ProgramConfig(BaseModel):
    """Where to find one external program (see core/external.py)."""

    model_config = ConfigDict(extra="forbid")

    path: Path | None = None
    conda_env: str | None = None

    @field_validator("path")
    @classmethod
    def _expand(cls, v: Path | None) -> Path | None:
        return v.expanduser() if v is not None else None


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    save_dir: Path = Path("~/Documents/ChemSidekick").expanduser()
    recent_limit: int = Field(default=50, ge=1)
    programs: dict[str, ProgramConfig] = {}

    @field_validator("save_dir")
    @classmethod
    def _expand(cls, v: Path) -> Path:
        return v.expanduser()


def load_config(path: Path | None = None) -> Config:
    """Read the config file, or return defaults if it does not exist."""
    path = path or CONFIG_PATH
    if not path.exists():
        return Config()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from e
    try:
        return Config.model_validate(raw)
    except ValidationError as e:
        raise ConfigError(f"{path}: {e}") from e
