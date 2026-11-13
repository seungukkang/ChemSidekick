"""Tool `profile` (ENE-01): an energy profile A → TS → products, or the
populations of states (conformers).

Reaction mode: each path has a transition state (barrier ΔG‡, or a measured k
or t½) and a product (ΔG, or K), all relative to the reactant A. Filled values
decide what is computed: barriers give rate constants, half-lives and the
kinetic product ratio; product energies give equilibrium constants and the
equilibrium ratio. Populations mode: energies of states give Boltzmann
populations and weighted averages.

Calculations: core/energetics.py. Drawing: core/profile_svg.py.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from chemsidekick.core import energetics as E
from chemsidekick.core import units as U
from chemsidekick.core.profile_svg import Branch, Level, population_ladder, reaction_profile
from chemsidekick.core.registry import tool
from chemsidekick.core.runner import workdir
from chemsidekick.core.schemas import (
    Artifact,
    Constant,
    Formula,
    Highlight,
    Table,
    ToolError,
    ToolResult,
)
from chemsidekick.core.solvents import load as load_solvents
from chemsidekick.core.tabular import parse_table

EnergyUnit = Literal["kcal/mol", "kJ/mol", "eV"]
SolventChoice = Literal["water", "methanol", "toluene", "benzene", "custom"]

MISSING = {"-", "–", "—", "?", ""}
DECIMALS = {"kcal/mol": 1, "kJ/mol": 1, "eV": 3, "Eh": 6}
# Below this barrier (in units of RT) the Eyring rate is only qualitative: the
# reaction is no longer much slower than thermal equilibration (TST's
# quasi-equilibrium), the usual criterion being ΔG‡ ≳ 5RT.
LOW_BARRIER_RT = 5.0


class ProfileInput(BaseModel):
    mode: Literal["reaction", "populations"] = Field(
        default="reaction",
        description="reaction: A → TS → products. populations: Boltzmann populations of states.",
        json_schema_extra={"label": "Mode"},
    )
    paths: str | None = Field(
        default=None,
        description="Reaction mode: one path per line, 'product  TS  product-energy', "
        "relative to the reactant A (e.g. 'B 20.0 -3.0'). Use '-' for an unknown value.",
        json_schema_extra={"label": "Paths", "multiline": True},
    )
    states: str | None = Field(
        default=None,
        description="Populations mode: one state per line, 'label  energy  [degeneracy]  "
        "[property ...]'. Absolute energies (e.g. in hartree) are fine.",
        json_schema_extra={"label": "States", "multiline": True},
    )
    unit: Literal["kcal/mol", "kJ/mol", "eV", "Eh"] = Field(
        default="kcal/mol",
        description="Unit of the energies (Eh: populations mode only).",
        json_schema_extra={"label": "Energy unit"},
    )
    ts_values: Literal["barrier", "rate constant", "half-life"] = Field(
        default="barrier",
        description="What the TS column holds: the barrier ΔG‡, a rate constant k "
        "(s⁻¹, or M⁻¹ s⁻¹ for bimolecular), or a half-life (e.g. 30min, 2h).",
        json_schema_extra={"label": "TS values are"},
    )
    product_values: Literal["free energy", "equilibrium constant"] = Field(
        default="free energy",
        description="What the product column holds: ΔG, or the equilibrium constant K.",
        json_schema_extra={"label": "Product values are"},
    )
    temperature: str = Field(
        default="298.15",
        description="Temperature: a number in K, or with a unit (25 C, -78 °C).",
        json_schema_extra={"label": "Temperature", "short": "-T"},
    )
    molecularity: Literal["unimolecular", "bimolecular"] = Field(
        default="unimolecular",
        description="unimolecular: k in s⁻¹. "
        "bimolecular (A + B): k in M⁻¹ s⁻¹, 1 M standard state.",
        json_schema_extra={"label": "Molecularity"},
    )
    partner: float | None = Field(
        default=None,
        gt=0,
        description="Bimolecular: concentration of the other reactant in M, for "
        "pseudo-first-order half-lives (default 1 M).",
        json_schema_extra={"label": "Partner concentration (M)"},
    )
    control: Literal["activation", "diffusion"] = Field(
        default="activation",
        description="activation: k from the barrier only. diffusion: bimolecular rates "
        "limited by diffusion, 1/k = 1/k_act + 1/k_diff.",
        json_schema_extra={"label": "Control"},
    )
    solvent: SolventChoice = Field(
        default="water",
        description="Diffusion control: solvent viscosity at 25 °C (or custom).",
        json_schema_extra={"label": "Solvent"},
    )
    viscosity: float | None = Field(
        default=None,
        gt=0,
        description="Diffusion control with a custom solvent: viscosity in mPa s (= cP).",
        json_schema_extra={"label": "Viscosity (mPa s)"},
    )
    standard_state: Literal["1 M", "1 atm"] = Field(
        default="1 M",
        description="Standard state of the energies. 1 atm (gas-phase calculations) is "
        "converted to 1 M for bimolecular steps.",
        json_schema_extra={"label": "Energies are for"},
    )
    target_half_life: str | None = Field(
        default=None,
        description="Find the temperature at which each path has this half-life (e.g. 1h).",
        json_schema_extra={"label": "Target half-life"},
    )
    target_selectivity: str | None = Field(
        default=None,
        description="Find the ΔΔG‡ needed for this selectivity: a ratio (95:5), "
        "an ee (90% ee), or a dr (10:1 dr).",
        json_schema_extra={"label": "Target selectivity"},
    )


@tool(
    name="profile",
    number=1,
    title="Energy profile",
    summary="Energy profile A → TS → products: rate constants, half-lives, kinetic and "
    "equilibrium ratios; or Boltzmann populations",
    category="energetics",
    keywords=[
        "eyring",
        "kinetics",
        "thermodynamics",
        "barrier",
        "half-life",
        "selectivity",
        "boltzmann",
        "conformer",
        "equilibrium",
        "curtin-hammett",
    ],
    icon="show_chart",
)
def profile(inp: ProfileInput) -> ToolResult:
    temperature = U.parse_temperature(inp.temperature)
    if inp.mode == "populations":
        return _populations(inp, temperature)
    if inp.unit == "Eh":
        raise ToolError("Hartree energies are for populations mode; use kcal/mol, kJ/mol or eV.")
    return _reaction(inp, temperature)


# ---------------------------------------------------------------------------
# Reaction mode
# ---------------------------------------------------------------------------


@dataclass
class Path:
    label: str
    line: int
    dg_act: float | None = None  # J/mol, 1 M standard state
    dg: float | None = None  # J/mol
    ts_entered: bool = True
    product_entered: bool = True
    imaginary: float | None = None  # cm⁻¹
    kappa: float = 1.0
    k_act: float | None = None
    k_diff: float | None = None
    k: float | None = None  # the rate constant used (after diffusion, if any)
    notes: list[str] = field(default_factory=list)


def _cells(line: str) -> list[str]:
    """Columns: split at tabs, commas or semicolons if there are any, else at spaces."""
    parts = re.split(r"[\t,;]", line) if re.search(r"[\t,;]", line) else line.split()
    return [p.strip() for p in parts]


def _read_paths(inp: ProfileInput, temperature: float) -> list[Path]:
    if not inp.paths or not inp.paths.strip():
        raise ToolError("Give at least one path, e.g. 'B 20.0 -3.0' (product, TS, product energy).")
    paths: list[Path] = []
    for n, raw in enumerate(inp.paths.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cells = _cells(line)
        label = cells[0] if U.parse_number(cells[0])[0] is None and cells[0] not in MISSING else ""
        if label:
            cells = cells[1:]
        label = label or f"P{len(paths) + 1}"
        if not cells or len(cells) > 3:
            raise ToolError(f"Line {n}: expected 'product  TS  product-energy  [imaginary cm⁻¹]'.")
        p = Path(label=label, line=n)
        ts_text = cells[0]
        product_text = cells[1] if len(cells) > 1 else "-"
        if ts_text not in MISSING:
            p.dg_act, p.ts_entered = _barrier(ts_text, inp, temperature, n)
        if product_text not in MISSING:
            p.dg, p.product_entered = _product(product_text, inp, temperature, n)
        if len(cells) == 3 and cells[2] not in MISSING:
            p.imaginary = _plain_number(cells[2], n, "imaginary frequency")
        if p.dg_act is None and p.dg is None:
            raise ToolError(f"Line {n}: give a TS value, a product value, or both.")
        paths.append(p)
    if not paths:
        raise ToolError("Give at least one path, e.g. 'B 20.0 -3.0'.")
    return paths


def _plain_number(text: str, line: int, what: str) -> float:
    value, rest = U.parse_number(text)
    if value is None or rest:
        raise ToolError(f"Line {line}: cannot read the {what} {text!r}.")
    return value


def _bimolecular(inp: ProfileInput) -> bool:
    return inp.molecularity == "bimolecular"


def _std_shift(inp: ProfileInput, temperature: float) -> float:
    """J/mol to subtract from 1 atm energies of bimolecular steps to get 1 M."""
    if inp.standard_state == "1 atm" and _bimolecular(inp):
        return E.standard_state_shift(temperature, 1)
    return 0.0


def _barrier(text: str, inp: ProfileInput, temperature: float, line: int) -> tuple[float, bool]:
    if inp.ts_values == "barrier":
        value = _plain_number(text, line, "barrier")
        return U.molar_energy(value, inp.unit) - _std_shift(inp, temperature), True
    if inp.ts_values == "rate constant":
        k = _plain_number(text, line, "rate constant")
        if k <= 0:
            raise ToolError(f"Line {line}: a rate constant must be positive.")
    else:
        try:
            t_half = U.parse_duration(text)
        except U.UnitError as e:
            raise ToolError(f"Line {line}: {e}") from None
        k = E.k_from_half_life(t_half) / (_partner(inp) if _bimolecular(inp) else 1.0)
    return E.dg_act_from_k(k, temperature), False


def _product(text: str, inp: ProfileInput, temperature: float, line: int) -> tuple[float, bool]:
    value = _plain_number(text, line, "product value")
    if inp.product_values == "equilibrium constant":
        if value <= 0:
            raise ToolError(f"Line {line}: an equilibrium constant must be positive.")
        return E.dg_from_k_eq(value, temperature), False
    return U.molar_energy(value, inp.unit) - _std_shift(inp, temperature), True


def _partner(inp: ProfileInput) -> float:
    return inp.partner if inp.partner is not None else 1.0


def _viscosity(inp: ProfileInput) -> tuple[float, str]:
    """(Pa s, description) of the solvent for diffusion control."""
    if inp.solvent == "custom":
        if inp.viscosity is None:
            raise ToolError("Custom solvent: give its viscosity in mPa s.")
        return inp.viscosity * 1e-3, f"custom solvent, {inp.viscosity:g} mPa s"
    s = load_solvents().solvents[inp.solvent]
    return s.viscosity_pa_s, f"{s.name.lower()}, {s.viscosity:.4g} mPa s at 25 °C"


def _reaction(inp: ProfileInput, temperature: float) -> ToolResult:
    paths = _read_paths(inp, temperature)
    unit = inp.unit
    rt = E.rt(temperature)
    diffusion = inp.control == "diffusion"
    if diffusion and not _bimolecular(inp):
        raise ToolError(
            "Diffusion control applies to bimolecular steps: set molecularity to bimolecular."
        )
    warnings: list[str] = []
    assumptions: list[str] = []
    k_diff = None
    if diffusion:
        eta, solvent_text = _viscosity(inp)
        k_diff = E.k_diffusion(temperature, eta)
        assumptions.append(
            f"Diffusion: k_diff = 8RT/(3η) for neutral spheres of equal size ({solvent_text})."
        )
        if inp.solvent != "custom" and abs(temperature - 298.15) > 0.5:
            warnings.append(
                "The solvent viscosity is the 25 °C value; it changes with temperature."
            )

    for p in paths:
        if p.dg_act is None:
            continue
        if p.imaginary is not None:
            p.kappa = E.wigner_kappa(p.imaginary, temperature)
            if p.kappa > 2:
                warnings.append(
                    f"{p.label}: Wigner κ = {p.kappa:.2f} is large; the Wigner correction is "
                    "only reliable for small corrections."
                )
        p.k_act = E.eyring_k(p.dg_act, temperature, p.kappa)
        p.k = p.k_act
        if k_diff is not None:
            p.k_diff = k_diff
            p.k = E.k_observed(p.k_act, k_diff)
        if p.dg_act < 0:
            warnings.append(f"{p.label}: the barrier is negative.")
        if p.dg is not None and p.dg_act < p.dg:
            warnings.append(f"{p.label}: the TS lies below the product.")
        if not diffusion and _bimolecular(inp) and p.k_act > 1e8:
            warnings.append(
                f"{p.label}: k = {U.format_sig(p.k_act)} M⁻¹ s⁻¹ approaches the diffusion "
                "limit (~10⁹–10¹⁰); try diffusion control."
            )

    # Eyring/TST needs barriers well above kT: thermal equilibration must be much
    # faster than the reaction. Below about 5RT the rates are only qualitative.
    low = [p for p in paths if p.dg_act is not None and 0 <= p.dg_act < LOW_BARRIER_RT * rt]
    if low:
        limit_text = _energy_text(LOW_BARRIER_RT * rt, unit, True)
        names = ", ".join(p.label for p in low)
        warnings.append(
            f"Low barrier ({names}): ΔG‡ below 5RT = {limit_text} {unit}. The Eyring rate is "
            "only qualitative here; read it as nearly barrierless."
        )

    kinetic = [p for p in paths if p.k is not None]
    thermo = [p for p in paths if p.dg is not None]
    k_unit = "M⁻¹ s⁻¹" if _bimolecular(inp) else "s⁻¹"

    # Ratios by product (paths with the same label are summed / must agree).
    kinetic_pct = _kinetic_shares(kinetic)
    equilibrium_pct, eq_reactant = _equilibrium_shares(thermo, temperature, warnings)

    answer_parts: list[str] = []
    highlights: list[Highlight] = []
    if len(kinetic_pct) >= 2:
        answer_parts.append(f"Kinetic {_ratio_text(kinetic_pct)}")
    if len(equilibrium_pct) >= 2:
        answer_parts.append(f"Equilibrium {_ratio_text(equilibrium_pct)}")
    if len(kinetic_pct) >= 2 and len(equilibrium_pct) >= 2:
        fast = max(kinetic_pct, key=kinetic_pct.get)
        stable = max(equilibrium_pct, key=equilibrium_pct.get)
        if fast != stable:
            answer_parts.append(f"kinetic product {fast}, thermodynamic product {stable}")
    single = len(paths) == 1
    if not answer_parts and kinetic:
        p = kinetic[0]
        answer_parts.append(f"k = {U.format_sig(p.k)} {k_unit}")
        answer_parts.append(f"t½ = {U.format_duration(_t_half(p, inp))}")
        if single:
            t99 = E.time_to_conversion(_k_eff(p, inp), 99)
            answer_parts.append(f"99 % done in {U.format_duration(t99)}")
    if (not answer_parts or single) and thermo:
        p = thermo[0]
        k_eq = E.k_eq(p.dg, temperature)
        share = k_eq / (1 + k_eq) * 100
        k_text = U.format_sig(k_eq)
        answer_parts.append(f"K = {k_text} ({U.format_percent(share)} % {p.label} at equilibrium)")

    if single and kinetic:
        # One path: what a chemist asks next about it.
        p = kinetic[0]
        highlights.append(Highlight(label="t½", value=U.format_duration(_t_half(p, inp)),
                                    note=f"k = {U.format_sig(p.k)} {k_unit}"))  # fmt: skip
        highlights.append(
            Highlight(
                label="90 % / 99 % done",
                value=f"{U.format_duration(E.time_to_conversion(_k_eff(p, inp), 90))} / "
                f"{U.format_duration(E.time_to_conversion(_k_eff(p, inp), 99))}",
            )
        )
        if p.dg_act is not None:
            faster = E.eyring_k(p.dg_act, temperature + 10, p.kappa) / p.k_act
            faster_text = f"{U.format_sig(faster)}× faster"
            highlights.append(Highlight(label="10 °C warmer", value=faster_text))
    else:
        for p in kinetic[:3]:
            highlights.append(
                Highlight(
                    label=f"t½ via {p.label}",
                    value=U.format_duration(_t_half(p, inp)),
                    note=f"k = {U.format_sig(p.k)} {k_unit}",
                )
            )

    tables = []
    if kinetic:
        rows = []
        for p in kinetic:
            rows.append(
                [
                    p.label,
                    _energy_text(p.dg_act, unit, p.ts_entered),
                    f"{U.format_sig(p.k)}",
                    U.format_duration(_t_half(p, inp)),
                    U.format_duration(E.time_to_conversion(_k_eff(p, inp), 90)),
                    U.format_duration(E.time_to_conversion(_k_eff(p, inp), 99)),
                ]
            )
        tables.append(
            Table(
                title="Rates",
                columns=["Path", f"ΔG‡ ({unit})", f"k ({k_unit})", "t½", "90 %", "99 %"],
                rows=rows,
            )
        )
        practical = _practical_temperatures(inp, kinetic)
        if practical:
            tables.append(practical)
        if diffusion:
            tables.append(
                Table(
                    title="Activation and diffusion",
                    columns=["Path", "k_act", "k_diff", "Limited by"],
                    rows=[
                        [
                            p.label,
                            U.format_sig(p.k_act),
                            U.format_sig(p.k_diff),
                            _limited_by(p),
                        ]
                        for p in kinetic
                    ],
                )
            )
    if thermo:
        tables.append(
            Table(
                title="Equilibria",
                columns=["Product", f"ΔG ({unit})", "K", "% at eq.", "Reverse ΔG‡", "Reverse t½"],
                rows=[
                    [
                        p.label,
                        _energy_text(p.dg, unit, p.product_entered),
                        U.format_sig(E.k_eq(p.dg, temperature)),
                        U.format_percent(
                            E.k_eq(p.dg, temperature) / (1 + E.k_eq(p.dg, temperature)) * 100
                        ),
                        _energy_text(p.dg_act - p.dg, unit, True) if p.dg_act is not None else "—",
                        U.format_duration(
                            E.half_life(E.eyring_k(p.dg_act - p.dg, temperature, p.kappa))
                        )
                        if p.dg_act is not None
                        else "—",
                    ]
                    for p in thermo
                ],
            )
        )
    products = list(dict.fromkeys([*kinetic_pct, *equilibrium_pct]))
    if len(products) >= 2:
        tables.append(
            Table(
                title="Product ratio",
                columns=["Product", "Kinetic %", "Equilibrium %"],
                rows=[
                    [
                        name,
                        U.format_percent(kinetic_pct[name]) if name in kinetic_pct else "—",
                        U.format_percent(equilibrium_pct[name]) if name in equilibrium_pct else "—",
                    ]
                    for name in products
                ],
            )
        )

    targets = _targets(inp, kinetic, temperature, unit, warnings)
    if targets:
        tables.append(targets)

    # Assumptions follow what was filled in.
    if kinetic:
        assumptions.append("Rate control: each step is irreversible over the time scale shown.")
        assumptions.append(
            "Half-lives are first order"
            + (
                f", pseudo-first order with the partner at {_partner(inp):g} M."
                if _bimolecular(inp)
                else "."
            )
        )
    if len(kinetic_pct) >= 2:
        assumptions.append(
            "Curtin–Hammett: the kinetic ratio is the ratio of rate constants "
            "from the same reactant."
        )
    if thermo:
        assumptions.append("Equilibrium: products interconvert through the reactant.")
    assumptions.append(
        f"Standard state 1 M; T = {temperature:g} K ({temperature - 273.15:.2f} °C)."
    )
    if inp.standard_state == "1 atm" and _bimolecular(inp):
        assumptions.append(
            "Energies converted from 1 atm to 1 M: "
            f"−{_energy_text(_std_shift(inp, temperature), unit, True)} {unit} "
            "for the bimolecular TS and products."
        )
    if any(p.imaginary is not None for p in paths):
        assumptions.append("Tunneling: Wigner correction κ = 1 + (hcν/k_BT)²/24.")

    # Drawing
    dec = DECIMALS[unit]
    to_unit = lambda j: U.from_molar_energy(j, unit)  # noqa: E731
    branches = [
        Branch(
            ts=Level(f"TS→{p.label}", to_unit(p.dg_act), p.ts_entered)
            if p.dg_act is not None
            else None,
            product=Level(p.label, to_unit(p.dg), p.product_entered) if p.dg is not None else None,
        )
        for p in paths
    ]
    limit = to_unit(E.dg_act_from_k(k_diff, temperature)) if k_diff is not None else None
    formulas = _reaction_formulas(bool(kinetic), bool(thermo), diffusion)
    svg = reaction_profile(Level("A", 0.0), branches, unit, decimals=dec, diffusion_limit=limit,
                           formulas=[f.latex for f in formulas])  # fmt: skip
    path = workdir() / "profile.svg"
    path.write_text(svg, encoding="utf-8")

    used = {"kB", "h", "NA"}
    if unit != "kJ/mol":
        used |= {"cal"} if unit == "kcal/mol" else {"e"}
    if any(p.imaginary is not None for p in paths):
        used.add("c")
    if inp.standard_state == "1 atm" and _bimolecular(inp):
        used.add("atm")

    data_paths = []
    for p in paths:
        data_paths.append(
            {
                "label": p.label,
                "barrier": to_unit(p.dg_act) if p.dg_act is not None else None,
                "barrier_entered": p.ts_entered,
                "energy": to_unit(p.dg) if p.dg is not None else None,
                "energy_entered": p.product_entered,
                "kappa": p.kappa,
                "k_act": p.k_act,
                "k_diff": p.k_diff,
                "k": p.k,
                "half_life_s": _t_half(p, inp) if p.k is not None else None,
                "t90_s": E.time_to_conversion(_k_eff(p, inp), 90) if p.k is not None else None,
                "t99_s": E.time_to_conversion(_k_eff(p, inp), 99) if p.k is not None else None,
                "K": E.k_eq(p.dg, temperature) if p.dg is not None else None,
            }
        )
    return ToolResult(
        answer=" · ".join(answer_parts),
        highlights=highlights,
        formulas=formulas,
        constants=_constants(used),
        assumptions=assumptions,
        sources=_sources(used, diffusion and inp.solvent != "custom"),
        notes=[
            "Energies are relative to the reactant A. Values computed from k, t½ or K are "
            "drawn in italics.",
            f"RT = {U.format_sig(U.from_molar_energy(rt, unit))} {unit} at {temperature:g} K.",
        ],
        tables=tables,
        artifacts=[Artifact(kind="svg", path=path, title="Energy profile")],
        warnings=warnings,
        data={
            "mode": "reaction",
            "unit": unit,
            "temperature_K": temperature,
            "k_unit": k_unit,
            "paths": data_paths,
            "kinetic_percent": kinetic_pct,
            "equilibrium_percent": equilibrium_pct,
            "equilibrium_reactant_percent": eq_reactant,
            "diffusion_limit": limit,
            "k_diff": k_diff,
        },
    )


PRACTICAL_HALF_LIVES = [("1 min", 60.0), ("1 h", 3600.0), ("1 day", 86400.0)]


def _practical_temperatures(inp: ProfileInput, paths: list[Path]) -> Table | None:
    """The temperature at which each path has a half-life of 1 min, 1 h, 1 day."""
    rows = []
    factor = _partner(inp) if _bimolecular(inp) else 1.0
    for p in paths:
        if p.dg_act is None:
            continue
        row = [p.label]
        for _, seconds in PRACTICAL_HALF_LIVES:
            try:
                kelvin = E.temperature_for_half_life(p.dg_act, seconds * factor, p.kappa)
                row.append(f"{kelvin - 273.15:.0f} °C")
            except ValueError:
                row.append("—")
        rows.append(row)
    if not rows:
        return None
    return Table(
        title="Temperature for a half-life of (ΔG‡ taken as independent of temperature)",
        columns=["Path", *(f"t½ {name}" for name, _ in PRACTICAL_HALF_LIVES)],
        rows=rows,
    )


def _limited_by(p: Path) -> str:
    """Which step sets the rate: within a factor of 3, both matter."""
    assert p.k_act is not None and p.k_diff is not None
    ratio = p.k_act / p.k_diff
    if ratio > 3:
        return "diffusion"
    if ratio < 1 / 3:
        return "activation"
    return "both"


def _k_eff(p: Path, inp: ProfileInput) -> float:
    """First-order rate constant: k, or k′ = k[B] for bimolecular steps."""
    assert p.k is not None
    return p.k * (_partner(inp) if _bimolecular(inp) else 1.0)


def _t_half(p: Path, inp: ProfileInput) -> float:
    return E.half_life(_k_eff(p, inp))


def _kinetic_shares(paths: list[Path]) -> dict[str, float]:
    total = sum(p.k for p in paths if p.k is not None)
    shares: dict[str, float] = {}
    for p in paths:
        if p.k is not None:
            shares[p.label] = shares.get(p.label, 0.0) + p.k / total * 100
    return shares


def _equilibrium_shares(
    paths: list[Path], temperature: float, warnings: list[str]
) -> tuple[dict[str, float], float | None]:
    """Equilibrium percentages among products (and the reactant's share of all)."""
    energies: dict[str, float] = {}
    for p in paths:
        assert p.dg is not None
        if p.label in energies and abs(energies[p.label] - p.dg) > 1e-6:
            warnings.append(f"{p.label}: two different product energies; the first is used.")
            continue
        energies.setdefault(p.label, p.dg)
    if not energies:
        return {}, None
    pops = E.populations(list(energies.values()), temperature)
    with_reactant = E.populations([0.0, *energies.values()], temperature)
    return {name: x * 100 for name, x in zip(energies, pops, strict=True)}, with_reactant[0] * 100


def _ratio_text(shares: dict[str, float]) -> str:
    names = " : ".join(shares)
    values = " : ".join(U.format_percent(v) for v in shares.values())
    return f"{names} = {values}"


def _energy_text(j_per_mol: float, unit: str, entered: bool) -> str:
    text = f"{U.from_molar_energy(j_per_mol, unit):.{DECIMALS[unit]}f}"
    return text if entered else f"{text} (calc.)"


def _targets(
    inp: ProfileInput, paths: list[Path], temperature: float, unit: str, warnings: list[str]
) -> Table | None:
    rows: list[list[str]] = []
    if inp.target_half_life:
        try:
            t_half = U.parse_duration(inp.target_half_life)
        except U.UnitError as e:
            raise ToolError(str(e)) from None
        for p in paths:
            if p.dg_act is None:
                continue
            factor = _partner(inp) if _bimolecular(inp) else 1.0
            try:
                kelvin = E.temperature_for_half_life(p.dg_act, t_half * factor, p.kappa)
            except ValueError:
                rows.append([f"t½ = {inp.target_half_life} via {p.label}", "out of range"])
                continue
            rows.append(
                [
                    f"t½ = {inp.target_half_life} via {p.label}",
                    f"{kelvin:.1f} K ({kelvin - 273.15:.1f} °C)",
                ]
            )
            if not 273.15 <= kelvin <= 473.15:
                warnings.append(f"{p.label}: the target half-life needs {kelvin - 273.15:.0f} °C.")
    if inp.target_selectivity:
        ratio = _read_selectivity(inp.target_selectivity)
        ddg = E.ddg_from_ratio(ratio, temperature)
        rows.append(
            [
                f"Selectivity {inp.target_selectivity.strip()}",
                f"ΔΔG‡ = {U.from_molar_energy(ddg, unit):.{DECIMALS[unit] + 1}f} {unit}",
            ]
        )
    if not rows:
        return None
    return Table(
        title="Targets (ΔG‡ taken as independent of temperature)",
        columns=["Target", "Needs"],
        rows=rows,
    )


def _read_selectivity(text: str) -> float:
    """'95:5' -> 19, '90% ee' / '90 ee' -> 19, '10:1 dr' -> 10, '19' -> 19."""
    t = text.strip().lower().replace("％", "%")
    try:
        if "ee" in t:
            value, _ = U.parse_number(t.replace("ee", "").replace("%", ""))
            if value is None:
                raise ValueError
            return E.ee_to_ratio(value)
        t = t.replace("dr", "").replace("%", "").strip()
        if ":" in t:
            a, b = (U.parse_number(x)[0] for x in t.split(":", 1))
            if a is None or b is None or a <= 0 or b <= 0:
                raise ValueError
            return a / b
        value, rest = U.parse_number(t)
        if value is None or rest or value <= 0:
            raise ValueError
        return value
    except ValueError:
        raise ToolError(
            f"Cannot read the selectivity {text!r}. Examples: 95:5, 90% ee, 10:1 dr."
        ) from None


# ---------------------------------------------------------------------------
# Populations mode
# ---------------------------------------------------------------------------


def _populations(inp: ProfileInput, temperature: float) -> ToolResult:
    if not inp.states or not inp.states.strip():
        raise ToolError("Give the states, one per line: 'label  energy  [degeneracy]'.")
    table = parse_table(inp.states, min_values=1)
    unit = inp.unit
    labels = [r.label or f"S{i + 1}" for i, r in enumerate(table.rows)]
    if len(set(labels)) != len(labels):
        raise ToolError("State labels must be different.")
    energies = [U.molar_energy(r.values[0], unit) for r in table.rows]
    has_g = (
        table.header and len(table.header) > 2 and table.header[2].lower().startswith(("g", "deg"))
    )
    degeneracy = [r.values[1] if has_g and len(r.values) > 1 else 1.0 for r in table.rows]
    first_prop = 2 if has_g else 1
    prop_names = list(table.header[first_prop + 1 :]) if table.header else []
    pops = E.populations(energies, temperature, degeneracy)
    low = min(energies)
    rel = [U.from_molar_energy(e - low, unit) for e in energies]
    display_unit = "kcal/mol" if unit == "Eh" else unit
    rel_display = [U.from_molar_energy(e - low, display_unit) for e in energies]
    warnings = []
    if U.from_molar_energy(max(energies) - low, "Eh") > 1:
        warnings.append("Energies span more than 1 hartree: check the unit.")

    # The most populated states, in order, until they add up to 95 %.
    order = sorted(range(len(labels)), key=lambda i: -pops[i])
    cumulative, top_95 = 0.0, set()
    for i in order:
        if cumulative < 95:
            top_95.add(i)
        cumulative += pops[i] * 100
    covered = len(top_95)

    rows = [
        [
            labels[i],
            f"{rel_display[i]:.2f}",
            U.format_percent(pops[i] * 100),
            U.format_percent(sum(pops[j] for j in order[: k + 1]) * 100),
        ]
        for k, i in enumerate(order)
    ]
    tables = [
        Table(
            title="Populations",
            columns=["State", f"ΔG ({display_unit})", "%", "Cumulative %"],
            rows=rows,
        )
    ]
    averages = {}
    n_props = max(len(r.values) - first_prop for r in table.rows)
    if n_props > 0:
        avg_rows = []
        for j in range(n_props):
            values = [
                r.values[first_prop + j] if len(r.values) > first_prop + j else None
                for r in table.rows
            ]
            if any(v is None for v in values):
                raise ToolError(f"Property column {j + 1}: every state needs a value.")
            avg = sum(p * v for p, v in zip(pops, values, strict=True))  # type: ignore[misc]
            name = prop_names[j] if j < len(prop_names) else f"Property {j + 1}"
            averages[name] = avg
            avg_rows.append([name, U.format_sig(avg)])
        tables.append(
            Table(
                title="Boltzmann-weighted averages", columns=["Property", "Average"], rows=avg_rows
            )
        )

    states = [(labels[i], rel_display[i], pops[i]) for i in range(len(labels))]
    svg = population_ladder(states, display_unit,
                            formulas=[f.latex for f in POPULATION_FORMULAS])  # fmt: skip
    path = workdir() / "populations.svg"
    path.write_text(svg, encoding="utf-8")

    top = labels[order[0]]
    answer = f"{top} {U.format_percent(pops[order[0]] * 100)} %"
    if len(labels) > 1:
        answer += f" · {covered} of {len(labels)} states cover 95 %"
    used = (
        {"kB", "NA"}
        | ({"cal"} if display_unit == "kcal/mol" else set())
        | ({"Eh"} if unit == "Eh" else set())
    )
    return ToolResult(
        answer=answer,
        highlights=[
            Highlight(
                label=labels[i],
                value=f"{U.format_percent(pops[i] * 100)} %",
                note=f"ΔG = {rel_display[i]:.2f} {display_unit}",
            )
            for i in order[:3]
        ],
        formulas=POPULATION_FORMULAS,
        constants=_constants(used),
        assumptions=[
            "Boltzmann distribution at equilibrium among the states.",
            f"T = {temperature:g} K ({temperature - 273.15:.2f} °C).",
        ],
        sources=_sources(used, False),
        notes=["Energies are relative to the lowest state."],
        tables=tables,
        artifacts=[Artifact(kind="svg", path=path, title="Populations")],
        warnings=warnings,
        data={
            "mode": "populations",
            "unit": display_unit,
            "temperature_K": temperature,
            "states": [
                {
                    "label": labels[i],
                    "energy": rel_display[i],
                    "degeneracy": degeneracy[i],
                    "percent": pops[i] * 100,
                    "percent_text": U.format_percent(pops[i] * 100),
                    "in_top_95": i in top_95,  # among the states that make up 95 %
                }
                for i in range(len(labels))
            ],
            "top_95_count": covered,
            "averages": averages,
            "relative_input_unit": rel,
        },
    )


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


POPULATION_FORMULAS = [
    Formula(
        latex=r"p_i = \frac{g_i\,e^{-\Delta G_i/RT}}{\sum_j g_j\,e^{-\Delta G_j/RT}}",
        text="p_i = g_i exp(−ΔG_i/RT) / Σ g_j exp(−ΔG_j/RT)",
        in_drawing=True,
    )
]


def _reaction_formulas(kinetic: bool, thermo: bool, diffusion: bool) -> list[Formula]:
    """The formulas used, in the order they are drawn under the profile (all
    marked in_drawing: they are typeset at the bottom of the drawing)."""
    out = []
    if kinetic:
        out.append(
            Formula(
                latex=r"k = \kappa\,\frac{k_\mathrm{B}T}{h}\,e^{-\Delta G^\ddagger/RT}",
                text="k = κ (k_B T / h) exp(−ΔG‡/RT)",
            )
        )
        out.append(Formula(latex=r"t_{1/2} = \frac{\ln 2}{k}", text="t½ = ln 2 / k"))
    if diffusion:
        out.append(
            Formula(
                latex=r"\frac{1}{k} = \frac{1}{k_\mathrm{act}} + \frac{1}{k_\mathrm{diff}}",
                text="1/k = 1/k_act + 1/k_diff",
            )
        )
        out.append(Formula(latex=r"k_\mathrm{diff} = \frac{8RT}{3\eta}", text="k_diff = 8RT/(3η)"))
    if thermo:
        out.append(Formula(latex=r"K = e^{-\Delta G/RT}", text="K = exp(−ΔG/RT)"))
    return [f.model_copy(update={"in_drawing": True}) for f in out]


def _constants(keys: set[str]) -> list[Constant]:
    data = U.load()
    return [
        Constant(
            name=data.constants[k].name,
            symbol=k,
            value=data.constants[k].value,
            unit=data.constants[k].unit,
            source=data.constants[k].source.split(":")[0],
        )
        for k in data.constants
        if k in keys
    ]


def _sources(keys: set[str], solvent: bool) -> list[str]:
    data = U.load()
    lines = dict.fromkeys(
        data.constants[k].source.split(":")[0]
        if data.constants[k].exact
        else data.references["codata2022"]
        for k in data.constants
        if k in keys
    )
    if solvent:
        lines[
            "Solvent viscosity: NIST Chemistry WebBook (SRD 69), checked against HSDB "
            "and the CRC Handbook (data/verification/solvents.md)"
        ] = None
    return list(lines)
