"""Tool `element`: look up one element, or show the periodic table."""

import difflib
import json
from functools import cache
from importlib.resources import files
from typing import Any

from pydantic import BaseModel, Field

from chemsidekick.core.registry import tool
from chemsidekick.core.schemas import ElementQuery, Table, ToolError, ToolResult

Element = dict[str, Any]


class ElementInput(BaseModel):
    query: ElementQuery | None = Field(
        default=None,
        description="Symbol, English name, or atomic number (e.g. Fe, iron, 26). "
        "Leave empty for the full periodic table.",
        json_schema_extra={"positional": True},
    )


@tool(
    name="element",
    title="Element",
    summary="Element properties, electron configuration, isotopes; or the periodic table",
    category="reference",
    keywords=["periodic table", "atomic weight", "electron configuration", "isotope"],
)
def element(inp: ElementInput) -> ToolResult:
    if inp.query is None:
        return _periodic_table()
    return _element_card(find(inp.query))


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@cache
def _dataset() -> dict[str, Any]:
    path = files("chemsidekick.tools.reference").joinpath("data/elements.json")
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def _index() -> dict[str, Element]:
    """Lowercase symbol / name / alias -> element."""
    index: dict[str, Element] = {}
    for el in _dataset()["elements"]:
        for key in [el["symbol"], el["name"], *el["aliases"]]:
            index[key.lower()] = el
    return index


def find(query: str) -> Element:
    """Find an element by symbol, English name, or atomic number."""
    q = query.strip()
    elements = _dataset()["elements"]
    if q.isdigit():
        z = int(q)
        if not 1 <= z <= len(elements):
            raise ToolError(f"Atomic number must be between 1 and {len(elements)}, got {z}.")
        return elements[z - 1]
    el = _index().get(q.lower())
    if el is not None:
        return el
    close = difflib.get_close_matches(q.lower(), list(_index()), n=3, cutoff=0.6)
    hint = ""
    if close:
        unique = {_index()[c]["symbol"]: _index()[c] for c in close}
        hint = (
            " Did you mean: "
            + ", ".join(f"{e['symbol']} ({e['name']})" for e in unique.values())
            + "?"
        )
    raise ToolError(f"Unknown element {query!r}.{hint}")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def superscript_config(config: str) -> str:
    """'[Ar] 3d6 4s2' -> '[Ar] 3d⁶ 4s²' (only the electron counts are raised)."""
    out = []
    for tok in config.split():
        if tok.startswith("["):
            out.append(tok)
        else:
            out.append(tok[:2] + tok[2:].translate(_SUPERSCRIPT))
    return " ".join(out)


def _signed(n: int) -> str:
    return f"+{n}" if n > 0 else ("−" + str(-n) if n < 0 else "0")


def _states(values: list[int]) -> str:
    return ", ".join(_signed(v) for v in values) if values else "—"


def _weight(el: Element) -> str:
    if not el["standard_weight"]:
        stable = el["most_stable_isotope"]
        if stable:
            return f"[{stable['mass_number']}] (no standard atomic weight)"
        return "— (no standard atomic weight)"
    unc = el["atomic_weight_uncertainty"]
    return f"{el['atomic_weight']:g} ± {unc:g}" if unc else f"{el['atomic_weight']:g}"


def _or_dash(value: Any, unit: str = "") -> str:
    if value is None:
        return "—"
    return f"{value:g}{unit}" if isinstance(value, float) else f"{value}{unit}"


def _sources() -> list[str]:
    meta = _dataset()["meta"]
    return [
        f"Element data: {meta['source']} (snapshot {meta['generated']})",
        f"Covalent radius: {meta['covalent_radius']}",
        f"Oxidation states: {meta['oxidation_states']}",
        "Electron configurations: experimental ground states (not Aufbau)",
    ]


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


def _element_card(el: Element) -> ToolResult:
    group = el["group"] if el["group"] is not None else "—"
    props = Table(
        title="Properties",
        columns=["Property", "Value"],
        rows=[
            ["Atomic number", el["z"]],
            ["Symbol", el["symbol"]],
            ["Name", el["name"]],
            ["Standard atomic weight", _weight(el)],
            ["Group / Period / Block", f"{group} / {el['period']} / {el['block']}"],
            ["Electron configuration", superscript_config(el["config"])],
            ["Full configuration", superscript_config(el["config_full"])],
            ["Electronegativity (Pauling)", _or_dash(el["en_pauling"])],
            ["Covalent radius", _or_dash(el["covalent_radius_pm"], " pm")],
            ["Oxidation states (main)", _states(el["oxidation_states_main"])],
            ["Oxidation states (other known)", _states(el["oxidation_states_other"])],
            ["Radioactive", "yes" if el["radioactive"] else "no"],
        ],
    )
    tables = [props]
    if el["isotopes"]:
        tables.append(
            Table(
                title="Natural isotopes",
                columns=["Isotope", "Mass (u)", "Abundance (%)"],
                rows=[
                    [f"{i['mass_number']}{el['symbol']}", f"{i['mass']:.6f}", f"{i['abundance']:g}"]
                    for i in el["isotopes"]
                ],
            )
        )
    elif el["most_stable_isotope"]:
        s = el["most_stable_isotope"]
        tables.append(
            Table(
                title="Longest-lived isotope (no natural abundance)",
                columns=["Isotope", "Half-life"],
                rows=[
                    [
                        f"{s['mass_number']}{el['symbol']}",
                        f"{s['half_life']:g} {s['half_life_unit']}",
                    ]
                ],
            )
        )
    return ToolResult(
        answer=f"{el['symbol']} · {el['name']} · Z = {el['z']}",
        tables=tables,
        sources=_sources(),
        data={"element": el},
    )


def _periodic_table() -> ToolResult:
    elements = _dataset()["elements"]
    columns = [""] + [str(g) for g in range(1, 19)]
    grid: dict[int, list[str]] = {p: [""] * 18 for p in range(1, 8)}
    lanthanides: list[str] = []
    actinides: list[str] = []
    for el in elements:
        if el["group"] is not None:
            grid[el["period"]][el["group"] - 1] = el["symbol"]
        elif el["period"] == 6:
            lanthanides.append(el["symbol"])
        else:
            actinides.append(el["symbol"])

    def f_row(label: str, symbols: list[str]) -> list[str]:
        # Place the f-block row under groups 4-17, below La/Ac in group 3.
        return [label, "", "", "", *symbols, ""][: len(columns)]

    rows: list[list[Any]] = [[str(p), *grid[p]] for p in range(1, 8)]
    rows.append([""] * len(columns))
    rows.append(f_row("Ln", lanthanides))
    rows.append(f_row("An", actinides))
    return ToolResult(
        answer=f"Periodic table · {len(elements)} elements",
        tables=[Table(title="", columns=columns, rows=rows)],
        sources=_sources()[:1],
        data={"symbols": [el["symbol"] for el in elements]},
    )
