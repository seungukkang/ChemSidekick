"""Tool `units`: chemistry unit conversions that a plain calculator does not do.

Energies (per molecule and per mole), energy equivalents (cm⁻¹, nm, Hz, K),
molar entropy, atomic-scale length, dipole moment, polarizability, 2nd-order
rate constants, concentration ↔ number density, pressure, and charge.
Units and constants come from core/data/units.toml (see core/units.py).
"""

from pydantic import BaseModel, Field

from chemsidekick.core import units as U
from chemsidekick.core.registry import tool
from chemsidekick.core.schemas import Constant, Formula, Highlight, Table, ToolResult

EXACT_LEGEND = (
    "exact: the conversion uses only defined constants. "
    "≈: it uses a measured constant (CODATA 2022), so the last digits carry its uncertainty."
)
DIGITS_NOTE = "Values are shown to 6 significant figures; the JSON output keeps full precision."
TORR_NOTE = (
    "Torr (= 1/760 atm) and the conventional mmHg (13.5951 g/cm³ mercury column) "
    "differ by 1.4 × 10⁻⁷ (relative)."
)
CAL_NOTE = "cal is the thermochemical calorie, 4.184 J."
POLARIZABILITY_NOTE = (
    "Å³, bohr³ and cm³ are polarizability volumes α′ = α / (4πε₀); "
    "C m²/V is the SI polarizability α."
)


class UnitsInput(BaseModel):
    query: str | None = Field(
        default=None,
        description="A value and unit, optionally with a target unit "
        "(e.g. 1 eV to kcal/mol, 300 nm, 760 Torr to bar). "
        "A group name (e.g. pressure) lists its units; leave empty to list all units.",
        json_schema_extra={"positional": True, "words": True, "label": "Conversion"},
    )
    temperature: str = Field(
        default="298.15",
        description="Temperature for the RT and kT values shown with energies: "
        "a number in K, or with a unit (25 C, 77 F).",
        json_schema_extra={"label": "Temperature (for RT, kT)", "short": "-T"},
    )
    show_all: bool = Field(
        default=False,
        description="Also show less common units of each group.",
        json_schema_extra={"label": "Show all units", "flag": "--all"},
    )


@tool(
    name="units",
    number=2,
    title="Units",
    summary="Chemistry unit conversions: energy, cm⁻¹/nm/K, dipole, polarizability, "
    "rate constants, pressure, charge",
    category="reference",
    keywords=[
        "unit",
        "convert",
        "conversion",
        "kcal/mol",
        "hartree",
        "eV",
        "wavenumber",
        "debye",
        "pressure",
        "torr",
    ],
    icon="swap_horiz",
    start_view="All units",
)
def units(inp: UnitsInput) -> ToolResult:
    text = (inp.query or "").strip()
    data = U.load()
    if not text:
        return _unit_list(list(data.groups))
    groups = _groups_named(text)
    if groups:
        return _unit_list(groups, title=text.strip().capitalize() if len(groups) > 1 else "")
    query = U.parse_query(text)
    temperature = U.parse_temperature(inp.temperature)
    if query.target is None:
        return _overview(query, temperature, inp.show_all)
    return _conversion(query, temperature, inp.show_all)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


def _conversion(query: U.Query, temperature: float, show_all: bool) -> ToolResult:
    assert query.target is not None
    source, target = U.pair(query.source, query.target)
    value = U.convert(query.value, source, target)
    exact = source.exact and target.exact
    sign = "=" if exact else "≈"
    answer = (
        f"{U.format_number(query.value)} {source.symbol} {sign} "
        f"{U.format_number(value)} {target.symbol}"
    )
    shown = _table_units(source, show_all, extra=(target,))
    result = _result(
        answer=answer,
        query=query,
        source=source,
        shown=shown,
        temperature=temperature,
        formula_units=[source, target],
    )
    result.highlights.insert(
        0,
        Highlight(
            label=target.display,
            value=U.format_number(value),
            note=f"Full precision: {value!r}" + ("" if exact else " (uses a measured constant)"),
        ),
    )
    result.data["result"] = {
        "value": value,
        "text": U.format_number(value),
        "unit": U.describe(target),
        "exact": exact,
    }
    return result


def _overview(query: U.Query, temperature: float, show_all: bool) -> ToolResult:
    source = query.source.units[0]
    shown = _table_units(source, show_all)
    groups = U.load().groups
    headline = [
        u
        for symbol in groups[source.group].headline
        if (u := _by_symbol(source.group, symbol)) is not None and u != source
    ][:3]
    parts = [f"{U.format_number(query.value)} {source.symbol}"]
    for u in headline:
        sign = "=" if source.exact and u.exact else "≈"
        parts.append(f"{sign} {U.format_number(U.convert(query.value, source, u))} {u.symbol}")
    result = _result(
        answer=" ".join(parts),
        query=query,
        source=source,
        shown=shown,
        temperature=temperature,
        formula_units=[source],
    )
    # A spelling with two meanings (nm: wavelength and length): show the other one too.
    for other in query.source.units[1:]:
        for group_units in _table_units(other, show_all).values():
            result.tables.append(_group_table(query.value, other, group_units))
    return result


def _result(
    *,
    answer: str,
    query: U.Query,
    source: U.Unit,
    shown: dict[str, list[U.Unit]],
    temperature: float,
    formula_units: list[U.Unit],
) -> ToolResult:
    data = U.load()
    tables = [_group_table(query.value, source, units) for units in shown.values()]
    # Evidence covers the conversion itself; every row still shows exact / ≈.
    used = {k for u in formula_units for k in u.constants}
    warnings = [
        f"Read {lk.typed!r} as {lk.corrected!r} (upper/lower case differs)."
        for lk in (query.source, query.target)
        if lk is not None and lk.corrected
    ]
    notes = [EXACT_LEGEND, DIGITS_NOTE]
    symbols = {u.symbol for units in shown.values() for u in units}
    if symbols & {"Torr", "mmHg"}:
        notes.append(TORR_NOTE)
    if symbols & {"cal/mol", "kcal/mol", "cal", "kcal", "cal/(mol K)"}:
        notes.append(CAL_NOTE)
    if "polarizability" in shown:
        notes.append(POLARIZABILITY_NOTE)
    highlights: list[Highlight] = []
    thermal: list[dict] = []
    if U.family(source) == "energy":
        tables.append(_thermal_table(temperature))
        thermal = _thermal_data(temperature)
        used |= {"kB", "NA", "cal"}
        rt = U.convert(data.constants["kB"].value * temperature, data.unit("energy", "J"), _kcal())
        highlights.append(
            Highlight(
                label=f"RT at {temperature:g} K",
                value=f"{U.format_number(rt)} kcal/mol",
                note=f"{temperature - 273.15:.2f} °C",
            )
        )
    return ToolResult(
        answer=answer,
        highlights=highlights,
        formulas=_formulas(formula_units),
        constants=_constants(used),
        assumptions=_assumptions(shown),
        sources=_sources(used),
        notes=notes,
        tables=tables,
        warnings=warnings,
        data={
            "query": {
                "value": query.value,
                "unit": U.describe(source),
                "target": U.describe(query.target.units[0]) if query.target else None,
                "temperature_K": temperature,
            },
            "conversions": [
                {
                    **U.describe(u),
                    "value": (v := U.convert(query.value, source, u)),
                    "text": U.format_number(v),
                    "exact": source.exact and u.exact,
                }
                for units in shown.values()
                for u in units
                if U.family(u) == U.family(source)
            ],
            "thermal": thermal,
            # Every constant behind any value above, for interfaces that show the
            # evidence of one row at a time (e.g. Raycast's detail panel).
            "constants": {
                k: U.describe_constant(k)
                for k in sorted(
                    used | {k for units in shown.values() for u in units for k in u.constants},
                    key=list(data.constants).index,
                )
            },
        },
    )


def _table_units(
    source: U.Unit, show_all: bool, extra: tuple[U.Unit, ...] = ()
) -> dict[str, list[U.Unit]]:
    """Units to tabulate, by group: the source's group, plus energy equivalents
    for an energy (and energies for an equivalent). Uncommon units are hidden
    unless asked for, or typed."""
    data = U.load()
    typed = {source, *extra}
    groups = [source.group]
    if source.group == "energy":
        groups.append("equivalents")
    elif source.group == "equivalents":
        groups.append("energy")
    for u in extra:
        if u.group not in groups:
            groups.append(u.group)
    return {
        g: [u for u in data.in_group(g) if show_all or not u.more or u in typed] for g in groups
    }


def _group_table(value: float, source: U.Unit, units: list[U.Unit]) -> Table:
    group = U.load().groups[units[0].group]
    rows = [
        [
            u.display,
            U.format_number(U.convert(value, source, u)),
            "exact" if source.exact and u.exact else "≈",
        ]
        for u in units
    ]
    return Table(
        title=group.title, columns=["Unit", "Value", "Exact"], rows=rows, minor_columns=[2]
    )


def _thermal_table(temperature: float) -> Table:
    data = U.load()
    kt = data.constants["kB"].value * temperature  # J
    joule = data.unit("energy", "J")
    rows = [
        ["RT", U.format_number(U.convert(kt, joule, _kcal())), "kcal/mol"],
        ["RT", U.format_number(U.convert(kt, joule, data.unit("energy", "kJ/mol"))), "kJ/mol"],
        ["kT", U.format_number(U.convert(kt, joule, data.unit("energy", "meV"))), "meV"],
        ["kT", U.format_number(U.convert(kt, joule, data.unit("equivalents", "cm⁻¹"))), "cm⁻¹"],
    ]
    return Table(
        title=f"Thermal energy at {temperature:g} K ({temperature - 273.15:.2f} °C)",
        columns=["Quantity", "Value", "Unit"],
        rows=rows,
    )


def _thermal_data(temperature: float) -> list[dict]:
    """RT and kT at `temperature`, with how they are computed."""
    data = U.load()
    kt = data.constants["kB"].value * temperature  # J
    joule = data.unit("energy", "J")
    out = []
    for quantity, group, symbol in [
        ("RT", "energy", "kcal/mol"),
        ("RT", "energy", "kJ/mol"),
        ("kT", "energy", "meV"),
        ("kT", "equivalents", "cm⁻¹"),
    ]:
        value = U.convert(kt, joule, data.unit(group, symbol))
        out.append(
            {
                "quantity": quantity,
                "value": value,
                "text": U.format_number(value),
                "unit": symbol,
                "temperature_K": temperature,
                "definition": "RT = N_A·k_B·T" if quantity == "RT" else "kT = k_B·T",
                "constants": ["kB", "NA"] if quantity == "RT" else ["kB"],
            }
        )
    return out


def _unit_list(group_ids: list[str], title: str = "") -> ToolResult:
    data = U.load()
    tables = []
    for gid in group_ids:
        group = data.groups[gid]
        rows = [
            [
                u.display,
                ", ".join(a for a in u.aliases if U.normalize(a) != U.normalize(u.symbol)) or "—",
                "exact" if u.exact else "≈",
            ]
            for u in data.in_group(gid)
        ]
        tables.append(
            Table(
                title=f"{group.title} (base: {group.base})",
                columns=["Unit", "Also accepted", "Exact"],
                rows=rows,
                minor_columns=[2],
            )
        )
    n = sum(len(t.rows) for t in tables)
    if not title:
        title = "All units" if len(group_ids) > 1 else data.groups[group_ids[0]].title
    used = {k for gid in group_ids for u in data.in_group(gid) for k in u.constants}
    return ToolResult(
        answer=f"{title} · {n} units",
        tables=tables,
        constants=_constants(used),
        sources=_sources(used),
        notes=[
            "Type a value and a unit, e.g. 1 eV to kcal/mol, 300 nm, 1.85 D, 760 Torr to bar. "
            "Spaces, ^, · and superscripts in units are optional (M-1 s-1 = M⁻¹s⁻¹).",
            EXACT_LEGEND,
        ],
        data={
            "groups": [
                {
                    "id": gid,
                    "title": data.groups[gid].title,
                    "base": data.groups[gid].base,
                    "example": data.groups[gid].example,
                    "units": [
                        {**U.describe(u), "aliases": list(u.aliases), "more": u.more}
                        for u in data.in_group(gid)
                    ],
                }
                for gid in group_ids
            ]
        },
    )


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

_WAVELENGTH = Formula(latex=r"E = \frac{hc}{\lambda}", text="E = hc / λ")
_EQUIVALENCE = {
    "cm⁻¹": Formula(latex=r"E = hc\,\tilde{\nu}", text="E = hc·ν̃"),
    "K": Formula(latex=r"E = k_\mathrm{B} T", text="E = k_B·T"),
}


def _formulas(units: list[U.Unit]) -> list[Formula]:
    formulas: list[Formula] = []
    for u in dict.fromkeys(units):
        group = U.load().groups[u.group]
        if u.kind == "wavelength":
            f = _WAVELENGTH
        elif u.symbol in _EQUIVALENCE:
            f = _EQUIVALENCE[u.symbol]
        elif u.group == "equivalents":
            f = Formula(latex=r"E = h\nu", text="E = h·ν")
        elif u.factor == 1:
            continue  # the base unit itself
        else:
            factor = U.format_number(u.factor, 10)
            sign = "=" if u.exact else "≈"
            number = _latex_number(factor)
            f = Formula(
                latex=rf"1\ \text{{{u.symbol}}} {sign} {number}\ \text{{{group.base}}}",
                text=f"1 {u.symbol} {sign} {factor} {group.base}   ({u.factor_expr})",
            )
        if f not in formulas:
            formulas.append(f)
    return formulas


def _latex_number(text: str) -> str:
    """'4.359744722 × 10⁻¹⁸' -> '4.359744722 \\times 10^{-18}'."""
    if " × 10" not in text:
        return text
    mantissa, exp = text.split(" × 10")
    digits = exp.translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-"))
    return rf"{mantissa} \times 10^{{{digits}}}"


def _constants(keys: set[str]) -> list[Constant]:
    data = U.load()
    order = list(data.constants)
    return [
        Constant(
            name=data.constants[k].name,
            symbol=k,
            value=data.constants[k].value,
            unit=data.constants[k].unit,
            source=data.constants[k].source,
        )
        for k in sorted(keys, key=order.index)
    ]


def _sources(keys: set[str]) -> list[str]:
    """One line per document: definitions by their document, measured constants
    by the full CODATA 2022 citation."""
    data = U.load()
    lines: dict[str, None] = {}
    for k in sorted(keys, key=list(data.constants).index):
        c = data.constants[k]
        lines[c.source.split(":")[0] if c.exact else data.references["codata2022"]] = None
    return list(lines)


def _assumptions(shown: dict[str, list[U.Unit]]) -> list[str]:
    out = []
    if "energy" in shown:
        out.append("Molar energies are per mole of particles (× N_A).")
    if "equivalents" in shown:
        out.append(
            "Energy equivalents are photon/thermal relations (E = hν = hc·ν̃ = hc/λ = k_B·T); "
            "K here is a temperature equivalent, not a temperature."
        )
    if "density" in shown:
        out.append("molecule/cm³ counts particles: 1 M = N_A × 10⁻³ molecules/cm³.")
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _kcal() -> U.Unit:
    return U.load().unit("energy", "kcal/mol")


def _by_symbol(group: str, symbol: str) -> U.Unit | None:
    """The unit spelled `symbol` that converts with `group` (e.g. eV for cm⁻¹)."""
    family = U.load().groups[group].family
    matches = [u for u in U.find_unit(symbol).units if U.family(u) == family]
    return matches[0] if matches else None


_GROUP_ALIASES = {
    "atomic units": ["length", "dipole", "polarizability"],
    "atomic unit": ["length", "dipole", "polarizability"],
    "au": ["length", "dipole", "polarizability"],
    "rate": ["rate2"],
    "rate constant": ["rate2"],
    "concentration": ["density"],
    "wavenumber": ["equivalents"],
    "spectroscopy": ["equivalents"],
    "heat capacity": ["entropy"],
}


def _groups_named(text: str) -> list[str]:
    """Group ids for a group name typed alone (e.g. "pressure"), or []."""
    t = text.strip().lower()
    for gid, g in U.load().groups.items():
        if t in (gid, g.title.lower(), g.title.lower().split(" (")[0]):
            return [gid]
    return _GROUP_ALIASES.get(t, [])
