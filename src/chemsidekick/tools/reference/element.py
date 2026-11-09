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
from chemsidekick.core.schemas import ElementQuery, Table, ToolError, ToolResult

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


class _Refs:
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


def _check(f: dict[str, Any], refs: _Refs) -> str:
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


def _element_card(el: Element) -> ToolResult:
    refs = _Refs()
    iupac = refs.cite(["iupac-definition"])
    identity = refs.cite(el["identity_refs"])
    group = el["group"] if el["group"] is not None else "—"

    w = el["atomic_weight"]
    weight_text = "— (no standard atomic weight)" if w["text"] == "none" else w["text"]
    conf = el["config"]
    ox = el["oxidation_states"]
    rows: list[list[Any]] = [
        ["Atomic number", el["z"], f"def {iupac}"],
        ["Symbol", el["symbol"], f"✓ {identity}"],
        ["Name (IUPAC)", el["name"], f"✓ {identity}"],
        ["Standard atomic weight", weight_text, _check(w, refs)],
        [
            "Group / Period / Block",
            f"{group} / {el['period']} / {el['block']}",
            f"def {iupac}",
        ],
        ["Electron configuration", superscript_config(conf["value"]), _check(conf, refs)],
        ["Full configuration", superscript_config(conf["full"]), _check(conf, refs)],
        [
            "Electronegativity (Pauling)",
            _or_dash(el["en_pauling"]["value"]),
            _check(el["en_pauling"], refs),
        ],
        [
            "Covalent radius",
            _or_dash(el["covalent_radius_pm"]["value"], " pm"),
            _check(el["covalent_radius_pm"], refs),
        ],
        ["Oxidation states (main)", _states(ox["value"]["main"]), _check(ox, refs)],
        ["Oxidation states (other known)", _states(ox["value"]["other"]), _check(ox, refs)],
    ]
    tables = [
        Table(
            title="Properties", columns=["Property", "Value", "Check"], rows=rows, minor_columns=[2]
        )
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
                        _check(i["mass"], refs),
                        i["abundance"]["text"],
                        _check(i["abundance"], refs),
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
                        f"{v['half_life']:g} {v['unit']}",
                        _check(ll, refs),
                    ]
                ],
            )
        )

    meta = _dataset()["meta"]
    return ToolResult(
        answer=f"{el['symbol']} · {el['name']} · Z = {el['z']}",
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
    refs = _dataset()["meta"]["references"]
    return ToolResult(
        answer=f"Periodic table · {len(elements)} elements",
        tables=[
            Table(
                title="",
                columns=columns,
                rows=rows,
                action_field="query",
                action_columns=list(range(1, len(columns))),
            )
        ],
        assumptions=["18-column layout with La and Ac in group 3."],
        sources=[f"[1] {refs['iupac-definition']['citation']}"],
        data={"symbols": [el["symbol"] for el in elements]},
    )
