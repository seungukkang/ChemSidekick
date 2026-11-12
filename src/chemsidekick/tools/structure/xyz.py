"""Tool `xyz`: read pasted XYZ coordinates and show them in 3D.

Accepted input (detected automatically):
    1. standard XYZ: atom count, comment line, then "element x y z" lines
    2. coordinate lines only (e.g. copied from a Gaussian/ORCA input or an SI),
       optionally after a "charge multiplicity" line such as "0 1"
    3. several standard XYZ blocks one after another (conformers, optimization,
       IRC) -> frames
    4. atomic numbers instead of symbols ("6  0.0  0.0  0.0")
Extra columns after x y z (charges, forces) are ignored with a warning.
Coordinates are taken to be in Å.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from typing import Literal

from pydantic import BaseModel, Field

from chemsidekick.chem.xyz_bonds import infer
from chemsidekick.core.registry import tool
from chemsidekick.core.runner import workdir
from chemsidekick.core.schemas import (
    Artifact,
    Frame,
    Highlight,
    Structure3D,
    Table,
    ToolError,
    ToolResult,
)
from chemsidekick.tools.reference.element import CHECK_LEGEND, Refs, by_symbol, check_mark, find

OVERLAP_A = 0.5  # closer than this (Å): atoms probably overlap

DRAWING_NOTE = (
    "The 2D drawing uses bonds inferred from the coordinates (RDKit DetermineBonds, "
    "xyz2mol method, assuming a neutral molecule); it shows no stereochemistry. "
    "Check it against what you expect, especially for metals, ions, radicals, and "
    "transition states."
)

BOND_NOTE = (
    "Bonds in the 3D view are drawn by 3Dmol.js from interatomic distances only. "
    "They are not bond orders or chemical bond assignments; in transition states, "
    "forming and breaking bonds may look different from reality."
)


class XyzInput(BaseModel):
    text: str = Field(
        default="",
        description="XYZ coordinates: standard XYZ (one or more frames), or just "
        "'element x y z' lines. In the terminal: a file path, or pipe the text in.",
        json_schema_extra={
            "positional": True,
            "multiline": True,
            "file_input": True,
            "label": "XYZ coordinates",
        },
    )
    frame: int | None = Field(
        default=None, ge=1, description="Frame to show first (1 = first). Default: 1."
    )
    style: Literal["ball-and-stick", "stick", "sphere"] = Field(
        default="ball-and-stick", description="How atoms and bonds are drawn."
    )
    labels: bool = Field(default=False, description="Show atom numbers (counted from 1).")


@tool(
    name="xyz",
    number=1,
    title="XYZ viewer",
    summary="Paste XYZ coordinates: formula, molecular weight, closest atoms, and a 3D view",
    category="structure",
    keywords=["xyz", "3d", "geometry", "coordinates", "viewer", "molecular weight"],
    icon="view_in_ar",
)
def xyz(inp: XyzInput) -> ToolResult:
    parsed = parse_xyz(inp.text)
    frames = parsed.frames
    start = (inp.frame or 1) - 1
    if start >= len(frames):
        raise ToolError(f"Frame {inp.frame} does not exist: the input has {len(frames)} frame(s).")
    return _result(parsed, start, inp)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


@dataclass
class Parsed:
    frames: list[Frame]
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


_LABEL = re.compile(r"^([A-Za-z]{1,3})(\d*)$")


@dataclass
class _LineState:
    """What was noticed while reading atom lines (reported once, not per line)."""

    extra_columns: list[int] = field(default_factory=list)
    numbered_labels: list[int] = field(default_factory=list)


def _symbol(token: str, lineno: int, state: _LineState) -> str:
    if token.isdigit():
        z = int(token)
        el = _by_z(z)
        if el is None:
            raise ToolError(f"Line {lineno}: atomic number {z} is not between 1 and 118.")
        return el
    m = _LABEL.match(token)
    if m:
        letters, digits = m.groups()
        symbol = letters.capitalize()  # "CL" -> "Cl", "c" -> "C"
        if by_symbol(symbol):
            if digits:
                state.numbered_labels.append(lineno)
            return symbol
    raise ToolError(f"Line {lineno}: unknown element {token!r}.")


def _by_z(z: int) -> str | None:
    return find(str(z))["symbol"] if 1 <= z <= 118 else None


def _number(token: str, lineno: int) -> float:
    try:
        value = float(token.replace("D", "E").replace("d", "e"))  # Fortran 1.0D-03
    except ValueError:
        raise ToolError(f"Line {lineno}: coordinate {token!r} is not a number.") from None
    if not math.isfinite(value):
        raise ToolError(f"Line {lineno}: coordinate {token!r} is not a finite number.")
    return value


def _atom(line: str, lineno: int, state: _LineState) -> tuple[str, tuple[float, float, float]]:
    tokens = line.split()
    if len(tokens) < 4:
        raise ToolError(f"Line {lineno}: expected 'element x y z', found {line.strip()!r}.")
    symbol = _symbol(tokens[0], lineno, state)
    coords = tuple(_number(t, lineno) for t in tokens[1:4])
    if len(tokens) > 4:
        state.extra_columns.append(lineno)
    return symbol, coords  # type: ignore[return-value]


def _is_count(line: str) -> bool:
    tokens = line.split()
    return len(tokens) == 1 and tokens[0].isdigit()


def _line_ranges(numbers: list[int]) -> str:
    """[3, 4, 5, 9] -> '3–5, 9'."""
    parts, start = [], None
    for i, n in enumerate(numbers):
        if start is None:
            start = n
        if i + 1 == len(numbers) or numbers[i + 1] != n + 1:
            parts.append(str(start) if start == n else f"{start}–{n}")
            start = None
    return ", ".join(parts)


def parse_xyz(text: str) -> Parsed:
    lines = text.splitlines()
    first = next((i for i, ln in enumerate(lines) if ln.strip()), None)
    if first is None:
        raise ToolError("No coordinates given. Paste XYZ text or 'element x y z' lines.")
    state = _LineState()
    if _is_count(lines[first]):
        parsed = _parse_standard(lines, first, state)
    else:
        parsed = _parse_bare(lines, first, state)
    if state.extra_columns:
        parsed.warnings.append(
            f"Columns after x y z were ignored on line(s) {_line_ranges(state.extra_columns)}."
        )
    if state.numbered_labels:
        parsed.warnings.append(
            "Atom labels with numbers (e.g. C1) were read as element symbols on line(s) "
            f"{_line_ranges(state.numbered_labels)}."
        )
    return parsed


def _parse_standard(lines: list[str], i: int, state: _LineState) -> Parsed:
    frames: list[Frame] = []
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        k = len(frames) + 1
        if not _is_count(lines[i]):
            prev = frames[-1].n_atoms
            raise ToolError(
                f"Line {i + 1}: expected the atom count of frame {k}, found "
                f"{lines[i].strip()!r}. Frame {k - 1} says {prev} atoms; "
                "check that this matches its number of atom lines."
            )
        n = int(lines[i].split()[0])
        if n == 0:
            raise ToolError(f"Line {i + 1}: the atom count is 0.")
        comment = lines[i + 1].strip() if i + 1 < len(lines) else ""
        block = lines[i + 2 : i + 2 + n]
        found = next((j for j, ln in enumerate(block) if not ln.strip() or _is_count(ln)), None)
        if len(block) < n or found is not None:
            m = found if found is not None else len(block)
            raise ToolError(
                f"Line {i + 1}: frame {k} says {n} atoms, but {m} atom line(s) follow. "
                "Check the atom count."
            )
        atoms = [_atom(ln, i + 3 + j, state) for j, ln in enumerate(block)]
        frames.append(
            Frame(symbols=[a[0] for a in atoms], coords=[a[1] for a in atoms], comment=comment)
        )
        i += 2 + n
    return Parsed(frames)


def _parse_bare(lines: list[str], first: int, state: _LineState) -> Parsed:
    notes = []
    tokens = lines[first].split()
    if len(tokens) == 2 and all(re.fullmatch(r"[+-]?\d+", t) for t in tokens):
        notes.append(f"Line {first + 1} was read as charge and multiplicity: {' '.join(tokens)}.")
        first += 1
    last = max(i for i, ln in enumerate(lines) if ln.strip())
    atoms = []
    for i in range(first, last + 1):
        if not lines[i].strip():
            raise ToolError(
                f"Line {i + 1}: empty line inside the coordinates. For several structures, "
                "use standard XYZ (atom count, comment line, atoms) for each."
            )
        atoms.append(_atom(lines[i], i + 1, state))
    if not atoms:
        raise ToolError("No coordinate lines found after the charge and multiplicity line.")
    frame = Frame(symbols=[a[0] for a in atoms], coords=[a[1] for a in atoms])
    return Parsed([frame], notes=notes)


# ---------------------------------------------------------------------------
# Chemistry
# ---------------------------------------------------------------------------

_SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def hill_order(counts: Counter) -> list[str]:
    """Hill order: C, then H, then the rest alphabetically; without C, all alphabetically."""
    order = sorted(counts)
    if "C" in counts:
        rest = [s for s in order if s not in ("C", "H")]
        order = ["C"] + (["H"] if "H" in counts else []) + rest
    return order


def hill_formula(symbols: list[str]) -> str:
    counts = Counter(symbols)
    return "".join(s + (str(counts[s]) if counts[s] > 1 else "") for s in hill_order(counts))


def _round_uncertainty(u: float) -> tuple[float, int]:
    """Round to one significant figure; return (value, decimals)."""
    if u <= 0:
        return 0.0, 3
    decimals = max(0, -math.floor(math.log10(u)))
    return round(u, decimals), decimals


def _closest(frame: Frame) -> tuple[float, int, int] | None:
    """Shortest interatomic distance and the atom numbers (from 1)."""
    if frame.n_atoms < 2:
        return None
    best = None
    for (i, a), (j, b) in combinations(enumerate(frame.coords), 2):
        d = math.dist(a, b)
        if best is None or d < best[0]:
            best = (d, i + 1, j + 1)
    return best


def _overlaps(frame: Frame) -> list[tuple[float, int, int]]:
    return [
        (math.dist(a, b), i + 1, j + 1)
        for (i, a), (j, b) in combinations(enumerate(frame.coords), 2)
        if math.dist(a, b) < OVERLAP_A
    ]


def _pair(frame: Frame, d: tuple[float, int, int]) -> str:
    return f"{d[0]:.3f} Å ({frame.symbols[d[1] - 1]}{d[1]}–{frame.symbols[d[2] - 1]}{d[2]})"


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


def _write_xyz(frames: list[Frame]) -> str:
    out = []
    for f in frames:
        out += [str(f.n_atoms), f.comment]
        out += [
            f"{s:<2} {x:14.8f} {y:14.8f} {z:14.8f}"
            for s, (x, y, z) in zip(f.symbols, f.coords, strict=True)
        ]
    return "\n".join(out) + "\n"


def _result(parsed: Parsed, start: int, inp: XyzInput) -> ToolResult:
    frames = parsed.frames
    shown = frames[start]
    formula = hill_formula(shown.symbols)
    n_frames = len(frames)
    warnings = list(parsed.warnings)

    formulas = {hill_formula(f.symbols) for f in frames}
    if len(formulas) > 1:
        warnings.append(
            f"The frames have different compositions ({', '.join(sorted(formulas))}); "
            f"formula and molecular weight are for frame {start + 1}."
        )

    # Molecular weight from CIAAW abridged atomic weights.
    refs = Refs()
    counts = Counter(shown.symbols)
    composition, mw, unc, missing = [], 0.0, 0.0, []
    for symbol in hill_order(counts):
        w = by_symbol(symbol)["abridged_weight"]
        composition.append([symbol, counts[symbol], w["text"], check_mark(w, refs)])
        if w["value"] is None:
            missing.append(symbol)
        else:
            mw += counts[symbol] * w["value"]
            unc += counts[symbol] * w.get("uncertainty", 0.0)
    if missing:
        mw_text = "not defined"
        mw_value = None
        warnings.append(
            f"No molecular weight: {', '.join(missing)} has no standard atomic weight "
            "(no stable isotopes)."
        )
    else:
        u, decimals = _round_uncertainty(unc)
        mw_value = round(mw, decimals)
        mw_text = f"{mw:.{decimals}f} ± {u:.{decimals}f} g/mol"

    # Closest atoms and overlaps, per frame.
    closest = [_closest(f) for f in frames]
    overlaps = [(k, d) for k, f in enumerate(frames) for d in _overlaps(f)]
    if overlaps:
        listed = "; ".join(
            f"atoms {d[1]} and {d[2]} at {d[0]:.2f} Å (frame {k + 1})" for k, d in overlaps[:5]
        )
        more = f"; and {len(overlaps) - 5} more" if len(overlaps) > 5 else ""
        warnings.append(f"Atoms may overlap (closer than {OVERLAP_A} Å): {listed}{more}.")

    # 2D drawing from bonds inferred from the coordinates (frame shown first).
    inferred = infer(shown)
    if not inferred.orders:
        warnings.append(
            "Bond orders could not be determined from the coordinates "
            f"({inferred.reason}); the 2D drawing shows connectivity only."
        )

    summary = [
        ["Formula", formula],
        ["Atoms", shown.n_atoms],
        ["Molecular weight", mw_text],
        ["Frames", n_frames],
    ]
    if closest[start]:
        summary.append(["Closest atoms", _pair(shown, closest[start])])
    if n_frames == 1 and shown.comment:
        summary.append(["Comment line", shown.comment])
    if inferred.smiles:
        summary.append(["SMILES (inferred, no stereo)", inferred.smiles])
    tables = [
        Table(title="Summary", columns=["Property", "Value"], rows=summary),
        Table(
            title=f"Composition (frame {start + 1})" if n_frames > 1 else "Composition",
            columns=["Element", "Count", "Abridged atomic weight", "Check"],
            minor_columns=[3],
            rows=composition,
        ),
    ]
    if n_frames > 1:
        tables.append(
            Table(
                title="Frames",
                columns=["Frame", "Formula", "Comment line", "Closest atoms"],
                rows=[
                    [k + 1, hill_formula(f.symbols), f.comment, _pair(f, c) if c else "—"]
                    for k, (f, c) in enumerate(zip(frames, closest, strict=True))
                ],
            )
        )

    path = workdir() / "structure.xyz"
    path.write_text(_write_xyz(frames), encoding="utf-8")
    drawing = workdir() / "structure.svg"
    drawing.write_text(inferred.svg, encoding="utf-8")
    drawing_title = formula.translate(_SUBSCRIPT) + (
        f" · frame {start + 1}" if n_frames > 1 else ""
    )

    frame_word = "frame" if n_frames == 1 else "frames"
    return ToolResult(
        answer=f"{formula} · {shown.n_atoms} atoms · {n_frames} {frame_word}",
        highlights=[
            Highlight(label="Formula", value=formula.translate(_SUBSCRIPT)),
            Highlight(
                label="Molecular weight",
                value=mw_text,
                note="Sum of CIAAW 2024 abridged atomic weights (see Composition)",
            ),
            Highlight(label="Atoms", value=str(shown.n_atoms)),
            Highlight(label="Frames", value=str(n_frames)),
        ],
        tables=tables,
        structures=[
            Structure3D(
                frames=frames,
                title=formula.translate(_SUBSCRIPT),
                style=inp.style,
                labels=inp.labels,
                start_frame=start,
            )
        ],
        artifacts=[
            Artifact(
                kind="svg",
                path=drawing,
                title=drawing_title,
                note="bonds inferred from coordinates"
                if inferred.orders
                else "connectivity only (bond orders not determined)",
            ),
            Artifact(kind="xyz", path=path, title="Standard XYZ"),
        ],
        warnings=warnings,
        assumptions=[
            "Coordinates are in Å.",
            "Molecular weight: abridged atomic weights × atom counts; their uncertainties "
            "are added linearly (a conservative estimate).",
        ],
        notes=[*parsed.notes, DRAWING_NOTE, BOND_NOTE, CHECK_LEGEND],
        sources=refs.lines(),
        data={
            "formula": formula,
            "n_atoms": shown.n_atoms,
            "n_frames": n_frames,
            "molecular_weight": mw_value,
            "smiles_inferred": inferred.smiles,
            "bond_orders_inferred": inferred.orders,
            "closest_atoms_A": [round(c[0], 4) if c else None for c in closest],
        },
    )
