"""Tool `element`: look up one element, or show the periodic table.

Data comes from data/elements.json, built by scripts/build_elements.py by
cross-checking reference sources. Every shown value carries a status:

    verified    one primary source and two secondary compilations agree
    partial     the primary source and one compilation agree; the other
                compilation reproduces an older edition (shown with evidence)
    definition  a definition (IUPAC periodic table, CIAAW), not a measurement
    unverified  could not be confirmed by three sources; shown from mendeleev
"""

import difflib
import json
from functools import cache
from importlib.resources import files
from typing import Any

from pydantic import BaseModel, Field

from chemsidekick.core.registry import tool
from chemsidekick.core.schemas import (
    CellInfo,
    ElementQuery,
    Highlight,
    Table,
    ToolError,
    ToolResult,
)

Element = dict[str, Any]


class ElementInput(BaseModel):
    query: ElementQuery | None = Field(
        default=None,
        description="Symbol, English name, or atomic number (e.g. Fe, iron, 26). "
        "Leave empty for the full periodic table.",
        json_schema_extra={"positional": True, "label": "Element"},
    )


@tool(
    name="element",
    number=1,
    title="Element",
    summary="Element properties, electron configuration, isotopes; or the periodic table",
    category="reference",
    keywords=["periodic table", "atomic weight", "electron configuration", "isotope"],
    icon="science",
    start_view="Periodic table",
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


def by_symbol(symbol: str) -> Element | None:
    """Exact element symbol (e.g. "Cl") -> element data, or None."""
    el = _index().get(symbol.lower())
    return el if el is not None and el["symbol"] == symbol else None


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
        names = ", ".join(f"{e['symbol']} ({e['name']})" for e in unique.values())
        hint = f" Did you mean: {names}?"
    raise ToolError(f"Unknown element {query!r}.{hint}")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def superscript_config(config: str) -> str:
    """'[Ar] 3d6 4s2' -> '[Ar] 3d⁶ 4s²' (only the electron counts are raised)."""
    return " ".join(
        tok if tok.startswith("[") else tok[:2] + tok[2:].translate(_SUPERSCRIPT)
        for tok in config.split()
    )


def _signed(n: int) -> str:
    return f"+{n}" if n > 0 else ("−" + str(-n) if n < 0 else "0")


def _states(values: list[int]) -> str:
    return ", ".join(_signed(v) for v in values) if values else "—"


def _or_dash(value: Any, unit: str = "") -> str:
    if value is None:
        return "—"
    return f"{value:g}{unit}" if isinstance(value, float) else f"{value}{unit}"


class Refs:
    """Numbers references in the order they are first used on one card: [1], [2], ..."""

    def __init__(self) -> None:
        self.order: list[str] = []

    def cite(self, keys: list[str]) -> str:
        nums = []
        for k in keys:
            if k == "mendeleev":
                continue  # mendeleev is software, not a reference; listed separately
            if k not in self.order:
                self.order.append(k)
            nums.append(self.order.index(k) + 1)
        return ",".join(str(n) for n in nums)

    def lines(self) -> list[str]:
        refs = _dataset()["meta"]["references"]
        return [f"[{i}] {refs[k]['citation']}" for i, k in enumerate(self.order, start=1)]


def check_mark(f: dict[str, Any], refs: Refs) -> str:
    """Short check mark with reference numbers: '✓ 2,3,4', '≈ 2,4', 'def 1', '? 5'."""
    if f["status"] == "verified":
        return f"✓ {refs.cite(f['refs'])}"
    if f["status"] == "definition":
        return f"def {refs.cite(f['refs'])}"
    if f["status"] == "partial":
        agree = refs.cite(f["refs"])
        refs.cite([f["older"]["source"], f["older"]["edition"]])  # listed in References
        return f"≈ {agree}"
    cited = refs.cite(f["refs"] + f.get("agree", []))
    return f"? {cited}" if cited else "?"


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

CHECK_LEGEND = (
    "Check: ✓ confirmed by 3 references (1 primary + 2 compilations) · "
    "≈ 2 references agree, the third reproduces an older edition · "
    "def a definition · ? not confirmed by 3 references, value from mendeleev. "
    "Numbers refer to References."
)


# Half-life units as written by NUBASE2020 and by mendeleev -> shown units.
HALF_LIFE_UNITS = {
    "m": "min", "minute": "min", "hour": "h", "day": "d", "sec": "s", "msec": "ms",
    "usec": "µs", "us": "µs", "nsec": "ns", "year": "y", "kyear": "ky", "Myear": "My",
    "Gyear": "Gy",
}  # fmt: skip


def _weight_text(el: Element, key: str = "atomic_weight") -> str:
    w = el[key]
    return "none (no stable isotopes)" if w["text"] == "none" else w["text"]


def _check_note(f: dict[str, Any], refs: Refs) -> str:
    """Hover text for a highlight, e.g. 'Check ✓ 2,3,4 (see References)'."""
    return f"Check {check_mark(f, refs)} (see References)"


def _element_card(el: Element) -> ToolResult:
    refs = Refs()
    iupac = refs.cite(["iupac-definition"])
    identity = refs.cite(el["identity_refs"])
    group = el["group"] if el["group"] is not None else "—"
    w, conf, ox = el["atomic_weight"], el["config"], el["oxidation_states"]
    en, radius = el["en_pauling"], el["covalent_radius_pm"]
    position = f"{group} · {el['period']} · {el['block']}"

    highlights = [
        Highlight(
            label="Standard atomic weight", value=_weight_text(el), note=_check_note(w, refs)
        ),
        Highlight(
            label="Electron configuration",
            value=superscript_config(conf["value"]),
            note=_check_note(conf, refs),
        ),
        Highlight(label="Group · Period · Block", value=position, note=f"Definition [{iupac}]"),
        Highlight(
            label="Electronegativity (Pauling)",
            value=_or_dash(en["value"]),
            note=_check_note(en, refs),
        ),
    ]

    columns = ["Property", "Value", "Check"]
    tables = [
        Table(
            title="Identity",
            columns=columns,
            minor_columns=[2],
            rows=[
                ["Atomic number", el["z"], f"def {iupac}"],
                ["Symbol", el["symbol"], f"✓ {identity}"],
                ["Name (IUPAC)", el["name"], f"✓ {identity}"],
                ["Standard atomic weight", _weight_text(el), check_mark(w, refs)],
                [
                    "Abridged atomic weight",
                    _weight_text(el, "abridged_weight"),
                    check_mark(el["abridged_weight"], refs),
                ],
                ["Group · Period · Block", position, f"def {iupac}"],
            ],
        ),
        Table(
            title="Chemical properties",
            columns=columns,
            minor_columns=[2],
            rows=[
                ["Electronegativity (Pauling)", _or_dash(en["value"]), check_mark(en, refs)],
                [
                    "Covalent radius (single bond)",
                    _or_dash(radius["value"], " pm"),
                    check_mark(radius, refs),
                ],
                ["Oxidation states (main)", _states(ox["value"]["main"]), check_mark(ox, refs)],
                [
                    "Oxidation states (other known)",
                    _states(ox["value"]["other"]),
                    check_mark(ox, refs),
                ],
            ],
        ),  # fmt: skip
        Table(
            title="Electronic structure",
            columns=columns,
            minor_columns=[2],
            rows=[
                [
                    "Ground-state configuration",
                    superscript_config(conf["value"]),
                    check_mark(conf, refs),
                ],
                ["Full configuration", superscript_config(conf["full"]), check_mark(conf, refs)],
            ],
        ),
    ]

    if el["isotopes"]:
        tables.append(
            Table(
                title="Natural isotopes",
                columns=["Isotope", "Mass (u)", "Check", "Abundance (%)", "Check"],
                minor_columns=[2, 4],
                rows=[
                    [
                        f"{i['mass_number']}{el['symbol']}",
                        i["mass"]["text"],
                        check_mark(i["mass"], refs),
                        i["abundance"]["text"],
                        check_mark(i["abundance"], refs),
                    ]
                    for i in el["isotopes"]
                ],
            )
        )
    elif el["longest_lived_isotope"]:
        ll = el["longest_lived_isotope"]
        v = ll["value"]
        tables.append(
            Table(
                title="Longest-lived isotope (no natural abundance)",
                columns=["Isotope", "Half-life", "Check"],
                minor_columns=[2],
                rows=[
                    [
                        f"{v['mass_number']}{el['symbol']}",
                        f"{v['half_life']:g} {HALF_LIFE_UNITS.get(v['unit'], v['unit'])}",
                        check_mark(ll, refs),
                    ]
                ],
            )
        )

    meta = _dataset()["meta"]
    return ToolResult(
        answer=f"{el['symbol']} · {el['name']} · Z = {el['z']}",
        highlights=highlights,
        tables=tables,
        assumptions=["Ground state of the neutral, isolated atom."],
        notes=[CHECK_LEGEND],
        sources=[
            *refs.lines(),
            f"Data built {meta['built']} from sources retrieved {min(meta['retrieved'].values())}; "
            f"unverified values from mendeleev {meta['mendeleev']}.",
        ],
        data={"element": el},
    )


def _cell(el: Element) -> CellInfo:
    """Periodic-table tile: number, symbol, name, and the abridged atomic weight, or
    [mass number] of the longest-lived isotope for elements without stable isotopes."""
    w = el["abridged_weight"]
    ll = el["longest_lived_isotope"]
    if w["value"] is not None:
        mass, unconfirmed = w["text"].split(" ± ")[0], w["status"] == "unverified"
    elif ll is not None:
        mass, unconfirmed = f"[{ll['value']['mass_number']}]", ll["status"] == "unverified"
    else:
        mass, unconfirmed = "", False
    return CellInfo(
        top=str(el["z"]),
        tag=el["block"],
        lines=[el["name"], mass],
        unconfirmed=unconfirmed,
    )


BLOCKS = {"s": "s-block", "p": "p-block", "d": "d-block", "f": "f-block"}


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
        # The f-block row sits under groups 4-17, below La/Ac in group 3.
        return [label, "", "", "", *symbols, ""][: len(columns)]

    rows: list[list[Any]] = [[str(p), *grid[p]] for p in range(1, 8)]
    rows.append([""] * len(columns))
    rows.append(f_row("Ln", lanthanides))
    rows.append(f_row("An", actinides))
    cells = {el["symbol"]: _cell(el) for el in elements}
    refs = _dataset()["meta"]["references"]
    cited = ["iupac-definition", "ciaaw-abridged", "nubase2020"]
    return ToolResult(
        answer=f"Periodic table · {len(elements)} elements",
        tables=[
            Table(
                title="",
                columns=columns,
                rows=rows,
                action_field="query",
                action_columns=list(range(1, len(columns))),
                cells=cells,
                tags=BLOCKS,
                column_gaps=[3, 13],  # s | d | p blocks (groups 1-2, 3-12, 13-18)
            )
        ],
        assumptions=[
            "18-column layout with La and Ac in group 3; Ln = lanthanoids Ce–Lu, "
            "An = actinoids Th–Lr."
        ],
        notes=[
            "Click an element to open its card. Border colors show the block (s, p, d, f). "
            "Below each name: the abridged atomic weight (CIAAW 2024); for elements without "
            "stable isotopes, the mass number of the longest-lived isotope in brackets "
            "(NUBASE2020). Italic: not confirmed by 3 references."
        ],
        sources=[f"[{i}] {refs[k]['citation']}" for i, k in enumerate(cited, start=1)],
        data={"symbols": [el["symbol"] for el in elements]},
    )
