"""Energy diagrams as SVG: a reaction profile (A → TS → products) and a ladder
of populated states (conformers).

Drawn on the white backdrop of core/drawing.py, so they read well on light and
dark pages alike (Raycast, the web UI). Sizes are in user units; macOS's SVG
renderer (used by Raycast) does not handle percentages.
"""

from dataclasses import dataclass
from html import escape

from chemsidekick.core.drawing import with_backdrop
from chemsidekick.core.formula_svg import formula_block
from chemsidekick.core.theme import THEME_COLOR
from chemsidekick.core.units import format_percent

WIDTH, HEIGHT = 640, 360
INK = "#1f2937"  # text and the reactant
MUTED = "#6b7280"  # axis, values
TRACK = "#fde8e8"  # a light tint of the theme colour, behind population bars
PALETTE = ["#2563eb", "#ea580c", "#16a34a", "#9333ea", "#db2777", "#0891b2"]
FONT = "-apple-system, 'Helvetica Neue', Helvetica, Arial, sans-serif"

# Text is sized for the drawing shown about 460 px wide (Raycast's side panel).
LABEL, VALUE = 16, 14  # font sizes: names, numbers
_TOP, _BOTTOM = 44, 40
AXIS_X = 34
X_REACTANT, X_TS, X_PRODUCT = 105, 315, 500
HALF_BAR = 34  # a level is a short thick bar, as in papers
TS_BAND = 190  # several TS bars sit side by side within this width
CHAR = 0.6  # average character width / font size, for the room labels need


@dataclass(frozen=True)
class Level:
    label: str
    energy: float  # in the display unit
    entered: bool = True  # False: computed from another value (drawn in italics)


@dataclass(frozen=True)
class Branch:
    ts: Level | None
    product: Level | None


def color(i: int) -> str:
    return PALETTE[i % len(PALETTE)]


def number(x: float, decimals: int) -> str:
    """'-3.0' -> '−3.0' (typographic minus); '-0.0' -> '0.0'."""
    text = f"{x:.{decimals}f}"
    if float(text) == 0:
        text = text.lstrip("-")
    return text.replace("-", "−")


def _spread(ys: list[float], gap: float, *, upward: bool = False) -> list[float]:
    """Move label positions apart (keeping their order) so none are closer than
    `gap`: down from the top one, or with `upward`, up from the bottom one."""
    order = sorted(range(len(ys)), key=lambda i: ys[i], reverse=upward)
    out = list(ys)
    step = -gap if upward else gap
    for a, b in zip(order, order[1:], strict=False):
        if (out[b] - out[a]) * (1 if not upward else -1) < gap:
            out[b] = out[a] + step
    return out


class _Scale:
    def __init__(self, energies: list[float], top: float, bottom: float) -> None:
        low, high = min(energies), max(energies)
        span = high - low or 1.0
        self.low, self.high = low - 0.12 * span, high + 0.12 * span
        self.top, self.bottom = top, bottom

    def y(self, e: float) -> float:
        return self.top + (self.high - e) / (self.high - self.low) * (self.bottom - self.top)


def _text(x: float, y: float, s: str, *, fill: str = INK, anchor: str = "middle",
          size: int = 13, weight: str = "normal", italic: bool = False,
          halo: bool = True) -> str:  # fmt: skip
    attrs = (
        f"x='{x:.1f}' y='{y:.1f}' font-size='{size}' font-weight='{weight}' "
        f"text-anchor='{anchor}'" + (" font-style='italic'" if italic else "")
    )
    text = f"<text {attrs} fill='{fill}'>{escape(s)}</text>"
    if not halo:
        return text
    # A white halo keeps labels readable where they cross a line. It is a separate
    # white copy underneath: macOS's renderer (Raycast) ignores paint-order, so a
    # stroke on the text itself would be painted over the letters and thin them.
    under = (
        f"<text {attrs} fill='#ffffff' stroke='#ffffff' stroke-width='4' "
        f"stroke-linejoin='round'>{escape(s)}</text>"
    )
    return under + text


def _axis(unit: str) -> list[str]:
    """The energy axis: a line with an arrowhead drawn as a triangle (macOS's SVG
    renderer, used by Raycast, ignores markers)."""
    x, top = AXIS_X, _TOP - 18
    return [
        f"<line x1='{x}' y1='{HEIGHT - _BOTTOM + 8}' x2='{x}' y2='{top + 8}' "
        f"stroke='{MUTED}' stroke-width='1.6'/>",
        f"<path d='M{x - 6},{top + 11} L{x},{top} L{x + 6},{top + 11} z' fill='{MUTED}'/>",
        f"<text transform='translate({x - 12},{HEIGHT / 2}) rotate(-90)' fill='{MUTED}' "
        f"font-size='{VALUE}' text-anchor='middle'>G ({escape(unit)})</text>",
    ]


DIVIDER = "#e5e7eb"  # the thin line between the diagram and its formulas


def _svg(body: list[str], width: float = WIDTH, formulas: list[str] | None = None) -> str:
    """The card: the diagram, then (optionally) a thin divider and the formulas."""
    w, height = round(width), float(HEIGHT)
    if formulas:
        body = [*body, f"<line x1='40' y1='{HEIGHT:.1f}' x2='{w - 40}' y2='{HEIGHT:.1f}' "
                       f"stroke='{DIVIDER}' stroke-width='1'/>"]  # fmt: skip
        block, used = formula_block(formulas, w, HEIGHT + 18)
        body.append(block)
        height = HEIGHT + 18 + used + 20
    h = round(height)
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {w} {h}' "
        f"width='{w}' height='{h}' font-family=\"{FONT}\">{''.join(body)}</svg>"
    )
    return with_backdrop(svg)


def _bar(x: float, y: float, c: str) -> str:
    return (
        f"<line x1='{x - HALF_BAR:.1f}' y1='{y:.1f}' x2='{x + HALF_BAR:.1f}' y2='{y:.1f}' "
        f"stroke='{c}' stroke-width='4' stroke-linecap='round'/>"
    )


def _link(x1: float, y1: float, x2: float, y2: float, c: str) -> str:
    return (
        f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' stroke='{c}' "
        f"stroke-width='1.6' stroke-dasharray='5 4' opacity='0.8'/>"
    )


def _ts_positions(n: int) -> list[float]:
    """TS bars side by side (one per path), centred on X_TS."""
    if n <= 1:
        return [X_TS] * n
    step = min(TS_BAND / (n - 1), 2 * HALF_BAR + 22)
    return [X_TS + (i - (n - 1) / 2) * step for i in range(n)]


def reaction_profile(
    reactant: Level,
    branches: list[Branch],
    unit: str,
    *,
    decimals: int = 1,
    diffusion_limit: float | None = None,
    formulas: list[str] | None = None,
) -> str:
    """A → TS → product for each branch, all starting from the same reactant.

    Each state is a short bar with its name above and its energy below (products:
    both to the right), joined by dashed lines in the path's colour."""
    energies = [reactant.energy]
    for b in branches:
        energies += [lv.energy for lv in (b.ts, b.product) if lv is not None]
    if diffusion_limit is not None:
        energies.append(diffusion_limit)
    sc = _Scale(energies, _TOP + 22, HEIGHT - _BOTTOM - 18)
    labels = [f"{b.product.label}  {number(b.product.energy, decimals)}"
              for b in branches if b.product is not None]  # fmt: skip
    room = max((len(t) for t in labels), default=0) * LABEL * CHAR
    width = max(WIDTH, X_PRODUCT + HALF_BAR + 12 + room + 16)
    body = _axis(unit)
    y_a = sc.y(reactant.energy)
    xs = _ts_positions(len(branches))

    if diffusion_limit is not None:
        yd = sc.y(diffusion_limit)
        body.append(
            f"<line x1='{AXIS_X + 8}' y1='{yd:.1f}' x2='{width - 16:.1f}' y2='{yd:.1f}' "
            f"stroke='{MUTED}' stroke-width='1.2' stroke-dasharray='2 4'/>"
        )
        note = f"diffusion limit  {number(diffusion_limit, decimals)}"
        body.append(_text(width - 16, yd - 7, note, fill=MUTED, anchor="end", size=VALUE - 1))

    # Dashed links first, bars and labels on top.
    for i, b in enumerate(branches):
        c = color(i)
        y_end = sc.y(b.product.energy) if b.product else None
        if b.ts is not None:
            yt = sc.y(b.ts.energy)
            body.append(_link(X_REACTANT + HALF_BAR, y_a, xs[i] - HALF_BAR, yt, c))
            if y_end is not None:
                body.append(_link(xs[i] + HALF_BAR, yt, X_PRODUCT - HALF_BAR, y_end, c))
        elif y_end is not None:
            body.append(_link(X_REACTANT + HALF_BAR, y_a, X_PRODUCT - HALF_BAR, y_end, c))

    body.append(_bar(X_REACTANT, y_a, INK))
    body.append(_text(X_REACTANT, y_a - 10, reactant.label, size=LABEL, weight="600"))
    body.append(_text(X_REACTANT, y_a + 21, number(reactant.energy, decimals), fill=MUTED,
                      size=VALUE))  # fmt: skip

    for i, b in enumerate(branches):
        if b.ts is None:
            continue
        yt, c = sc.y(b.ts.energy), color(i)
        body.append(_bar(xs[i], yt, c))
        body.append(_text(xs[i], yt - 10, b.ts.label, fill=c, size=LABEL - 1, weight="600"))
        body.append(_text(xs[i], yt + 21, number(b.ts.energy, decimals), fill=c, size=VALUE,
                          italic=not b.ts.entered))  # fmt: skip

    products = [(i, b.product) for i, b in enumerate(branches) if b.product is not None]
    ys = _spread([sc.y(p.energy) + 5 for _, p in products], LABEL + 4)
    for (i, p), y in zip(products, ys, strict=True):
        yp, c = sc.y(p.energy), color(i)
        body.append(_bar(X_PRODUCT, yp, c))
        body.append(
            _text(X_PRODUCT + HALF_BAR + 12, y, f"{p.label}  {number(p.energy, decimals)}",
                  fill=c, anchor="start", size=LABEL, weight="600", italic=not p.entered)
        )  # fmt: skip
    return _svg(body, width, formulas)


def population_ladder(
    states: list[tuple[str, float, float]],
    unit: str,
    *,
    decimals: int = 2,
    formulas: list[str] | None = None,
) -> str:
    """States (label, relative energy, population fraction) as levels; the bar
    to the right of each level is its population."""
    sc = _Scale([e for _, e, _ in states], _TOP, HEIGHT - _BOTTOM)
    body = _axis(unit)
    # Room on the left for the longest name, so it never reaches the axis.
    room = max(len(label) for label, _, _ in states) * (LABEL - 1) * CHAR
    x0 = max(210.0, AXIS_X + 16 + room + 64)
    x1 = x0 + 100  # level line from x0 to x1
    bar_x, bar_max = x1 + 30, 190
    width = max(WIDTH, bar_x + bar_max + 76)
    top = max(p for _, _, p in states)
    ys = _spread([sc.y(e) for _, e, _ in states], LABEL + 6, upward=True)
    for (label, e, p), yl in zip(states, ys, strict=True):
        y = sc.y(e)
        body.append(
            f"<line x1='{x0}' y1='{y:.1f}' x2='{x1}' y2='{y:.1f}' stroke='{INK}' "
            f"stroke-width='3' stroke-linecap='round'/>"
        )
        # Labels that had to move apart are joined to their level by a thin line.
        if abs(yl - y) > 0.5:
            for xa, ya, xb, yb in ((x0 - 12, yl, x0 - 3, y), (x1 + 3, y, bar_x - 4, yl)):
                body.append(f"<line x1='{xa}' y1='{ya:.1f}' x2='{xb}' y2='{yb:.1f}' "
                            f"stroke='{MUTED}' stroke-width='0.8'/>")  # fmt: skip
        # Name and energy on the left, one after the other (no mixed-size runs).
        body.append(_text(x0 - 64, yl + 5, label, anchor="end", size=LABEL - 1, weight="600",
                          halo=False))  # fmt: skip
        body.append(_text(x0 - 16, yl + 5, number(e, decimals), fill=MUTED, anchor="end",
                          size=VALUE - 1, halo=False))  # fmt: skip
        # The population: a theme-coloured bar on a light track, darkest for the largest.
        body.append(
            f"<rect x='{bar_x}' y='{yl - 7:.1f}' width='{bar_max}' height='14' rx='7' "
            f"fill='{TRACK}'/>"
        )
        w = max(bar_max * p, 3)
        shade = 0.45 + 0.55 * (p / top if top else 1)
        body.append(
            f"<rect x='{bar_x}' y='{yl - 7:.1f}' width='{w:.1f}' height='14' rx='7' "
            f"fill='{THEME_COLOR}' fill-opacity='{shade:.2f}'/>"
        )
        share = f"{format_percent(p * 100)} %"
        body.append(_text(bar_x + bar_max + 10, yl + 5, share, anchor="start", size=VALUE,
                          weight="700", halo=False))  # fmt: skip
    return _svg(body, width, formulas)
