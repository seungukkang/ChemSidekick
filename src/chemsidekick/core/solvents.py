"""Solvent viscosities at 25 °C, checked against three references.

Data: core/data/solvents.toml. Only solvents whose references agree are listed;
for any other solvent the user types the viscosity.
"""

import tomllib
from dataclasses import dataclass
from functools import cache
from importlib.resources import files


@dataclass(frozen=True)
class Solvent:
    id: str
    name: str
    viscosity: float  # mPa s at 25 °C
    source: str  # reference key of the adopted value
    checks: tuple[tuple[str, float], ...]

    @property
    def viscosity_pa_s(self) -> float:
        return self.viscosity * 1e-3


@dataclass(frozen=True)
class SolventData:
    solvents: dict[str, Solvent]
    references: dict[str, str]
    tolerance: float
    temperature: float  # K at which the viscosities apply

    def agreeing(self, s: Solvent) -> int:
        return sum(abs(v - s.viscosity) <= self.tolerance * s.viscosity for _, v in s.checks)


@cache
def load() -> SolventData:
    text = files("chemsidekick.core").joinpath("data/solvents.toml").read_text(encoding="utf-8")
    raw = tomllib.loads(text)
    solvents = {
        s["id"]: Solvent(
            s["id"],
            s["name"],
            float(s["viscosity"]),
            s["source"],
            tuple((c["ref"], float(c["value"])) for c in s["checks"]),
        )
        for s in raw["solvent"]
    }
    return SolventData(solvents, raw["references"], raw["tolerance"], raw["temperature_K"])
