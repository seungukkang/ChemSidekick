"""Helpers for 2D drawings (SVG) made by tools.

Molecule drawings have dark lines on a transparent background, which disappear
on a dark page. `with_backdrop` puts a white card behind the drawing: solid
white with rounded corners and a thin border in the theme color
(core/theme.py), so the drawing is readable on any background.
"""

import re

from chemsidekick.core.theme import THEME_COLOR

_SVG_OPEN = re.compile(r"<svg\b[^>]*>")

_VIEWBOX = re.compile(
    r"""viewBox=['"]\s*([-\d.eE+]+)[\s,]+([-\d.eE+]+)[\s,]+([\d.eE+]+)[\s,]+([\d.eE+]+)\s*['"]"""
)

BORDER_COLOR = THEME_COLOR
BORDER_WIDTH = 2.0
CORNER_RADIUS = 10


def _rect(x: str, y: str, width: str, height: str) -> str:
    return (
        f"<rect id='csk-backdrop' x='{x}' y='{y}' width='{width}' height='{height}' "
        f"rx='{CORNER_RADIUS}' ry='{CORNER_RADIUS}' fill='#ffffff' "
        f"stroke='{BORDER_COLOR}' stroke-width='{BORDER_WIDTH:g}'/>"
    )


def backdrop(x: float, y: float, width: float, height: float) -> str:
    """The backdrop for a drawing whose viewBox is (x, y, width, height).

    The rectangle is inset by half the border width so the border is not cut
    off at the drawing's edge. Sizes are given in user units, not percentages:
    macOS's own SVG renderer (used by Raycast) draws width='100%' as a ~100 px
    square in the corner instead of the whole drawing. Browsers handle both.
    """
    h = BORDER_WIDTH / 2
    return _rect(f"{x + h:g}", f"{y + h:g}", f"{width - 2 * h:g}", f"{height - 2 * h:g}")


# For drawings without a viewBox: percentages work in browsers only (see
# backdrop()), and half of the border falls outside the drawing.
BACKDROP = _rect("0", "0", "100%", "100%")


def with_backdrop(svg: str) -> str:
    """The same SVG with a white backdrop drawn first (behind everything else)."""
    m = _SVG_OPEN.search(svg)
    if m is None:
        raise ValueError("not an SVG document")
    box = _VIEWBOX.search(m.group(0))
    layer = backdrop(*(float(v) for v in box.groups())) if box else BACKDROP
    return svg[: m.end()] + layer + svg[m.end() :]
