"""Helpers for 2D drawings (SVG) made by tools.

Molecule drawings have dark lines on a transparent background, which disappear
on a dark page. `with_backdrop` puts a soft white backdrop behind the drawing:
solid white over most of the image, fading out only near the edges, so the
drawing is readable on any background and still blends into the page.
"""

import re

_SVG_OPEN = re.compile(r"<svg\b[^>]*>")

BACKDROP = (
    "<defs><radialGradient id='csk-backdrop' cx='50%' cy='50%' r='72%'>"
    "<stop offset='0' stop-color='#ffffff' stop-opacity='1'/>"
    "<stop offset='0.62' stop-color='#ffffff' stop-opacity='1'/>"
    "<stop offset='0.85' stop-color='#ffffff' stop-opacity='0.9'/>"
    "<stop offset='1' stop-color='#ffffff' stop-opacity='0.7'/>"
    "</radialGradient></defs>"
    "<rect x='0' y='0' width='100%' height='100%' rx='10' ry='10' "
    "fill='url(#csk-backdrop)'/>"
)


def with_backdrop(svg: str) -> str:
    """The same SVG with a white backdrop drawn first (behind everything else)."""
    m = _SVG_OPEN.search(svg)
    if m is None:
        raise ValueError("not an SVG document")
    return svg[: m.end()] + BACKDROP + svg[m.end() :]
