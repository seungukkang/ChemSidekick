"""Formulas (LaTeX) typeset as SVG, laid out side by side in centred rows, for
the bottom of a drawing card.

ziamath typesets the LaTeX with the STIX Two Math font and writes the glyphs as
plain paths, so the formulas look the same everywhere (Raycast uses macOS's SVG
renderer, which handles neither web fonts nor <symbol>/<use>).
"""

import re
from dataclasses import dataclass

import ziamath as zm

zm.config.svg2 = False  # glyphs as inline paths, no <symbol>/<use>

SIZE = 19  # font size of the formulas (px)
COLUMN_GAP = 44  # between formulas on one row
ROW_GAP = 14

_OPEN = re.compile(r"<svg\b[^>]*>")
_VIEWBOX = re.compile(r"viewBox=['\"]([-\d.e]+)\s+([-\d.e]+)\s+([-\d.e]+)\s+([-\d.e]+)['\"]")


@dataclass(frozen=True)
class _Typeset:
    body: str  # the formula's SVG elements
    x: float  # its viewBox
    y: float
    width: float
    height: float


def _typeset(latex: str) -> _Typeset:
    svg = zm.Latex(latex, size=SIZE).svg()
    box, m = _VIEWBOX.search(svg), _OPEN.search(svg)
    if box is None or m is None:
        raise ValueError(f"could not typeset: {latex}")
    x, y, w, h = (float(v) for v in box.groups())
    return _Typeset(svg[m.end() : svg.rindex("</svg>")], x, y, w, h)


def _rows(items: list[_Typeset], room: float) -> list[list[_Typeset]]:
    """Formulas in their order, as many per row as fit in `room`."""
    rows: list[list[_Typeset]] = []
    for f in items:
        row = rows[-1] if rows else None
        if row and sum(g.width for g in row) + COLUMN_GAP * len(row) + f.width <= room:
            row.append(f)
        else:
            rows.append([f])
    return rows


def formula_block(latex: list[str], width: float, top: float) -> tuple[str, float]:
    """The formulas laid out for a card `width` wide, starting at y = `top`:
    rows centred, formulas on a row side by side and centred on a common line.
    Returns the SVG elements and the height used."""
    rows = _rows([_typeset(t) for t in latex], width - 48)
    body, y = [], top
    for row in rows:
        ascent = max(-f.y for f in row)  # baseline at y = 0 in each formula's viewBox
        descent = max(f.height + f.y for f in row)
        x = (width - sum(f.width for f in row) - COLUMN_GAP * (len(row) - 1)) / 2
        for f in row:
            dx, dy = x - f.x, y + ascent
            body.append(f"<g transform='translate({dx:.2f},{dy:.2f})'>{f.body}</g>")
            x += f.width + COLUMN_GAP
        y += ascent + descent + ROW_GAP
    return "".join(body), max(y - ROW_GAP - top, 0.0)
