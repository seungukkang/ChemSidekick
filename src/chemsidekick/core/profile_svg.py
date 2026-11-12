"""Energy diagrams as SVG: a reaction profile (A → TS → products) and a ladder
of populated states (conformers).

Drawn on the white backdrop of core/drawing.py, so they read well on light and
dark pages alike (Raycast, the web UI). Sizes are in user units; macOS's SVG
renderer (used by Raycast) does not handle percentages.
"""

from dataclasses import dataclass
from html import escape

from chemsidekick.core.drawing import with_backdrop

WIDTH, HEIGHT = 720, 400
INK = "#1f2937"  # text and the reactant
MUTED = "#6b7280"  # axis, guide lines
PALETTE = ["#2563eb", "#ea580c", "#16a34a", "#9333ea", "#db2777", "#0891b2"]
FONT = "-apple-system, 'Helvetica Neue', Helvetica, Arial, sans-serif"

_TOP, _BOTTOM, _LEFT, _RIGHT = 46, 46, 70, 40
X_REACTANT, X_TS, X_PRODUCT = 170, 380, 580
HALF_BAR = 44


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
          size: int = 13, weight: str = "normal", italic: bool = False) -> str:  # fmt: skip
    style = " font-style='italic'" if italic else ""
    # A white halo keeps labels readable where they cross a curve.
    return (
        f"<text x='{x:.1f}' y='{y:.1f}' fill='{fill}' font-size='{size}' "
        f"font-weight='{weight}' text-anchor='{anchor}'{style} stroke='#ffffff' "
        f"stroke-width='4' stroke-linejoin='round' paint-order='stroke'>{escape(s)}</text>"
    )


def _axis(unit: str) -> list[str]:
    x = _LEFT - 18
    return [
        f"<line x1='{x}' y1='{HEIGHT - _BOTTOM + 6}' x2='{x}' y2='{_TOP - 10}' "
        f"stroke='{MUTED}' stroke-width='1.5' marker-end='url(#arrow)'/>",
        f"<text transform='translate({x - 12},{(HEIGHT) / 2}) rotate(-90)' fill='{MUTED}' "
        f"font-size='13' text-anchor='middle'>G ({escape(unit)})</text>",
    ]


def _svg(body: list[str]) -> str:
    defs = (
        "<defs><marker id='arrow' viewBox='0 0 10 10' refX='5' refY='5' markerWidth='7' "
        f"markerHeight='7' orient='auto-start-reverse'><path d='M0,0 L10,5 L0,10 z' "
        f"fill='{MUTED}'/></marker></defs>"
    )
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {WIDTH} {HEIGHT}' "
        f"width='{WIDTH}' height='{HEIGHT}' font-family=\"{FONT}\">{defs}{''.join(body)}</svg>"
    )
    return with_backdrop(svg)


def reaction_profile(
    reactant: Level,
    branches: list[Branch],
    unit: str,
    *,
    decimals: int = 1,
    diffusion_limit: float | None = None,
) -> str:
    """A → TS → product for each branch, all starting from the same reactant."""
    energies = [reactant.energy]
    for b in branches:
        energies += [lv.energy for lv in (b.ts, b.product) if lv is not None]
    if diffusion_limit is not None:
        energies.append(diffusion_limit)
    sc = _Scale(energies, _TOP, HEIGHT - _BOTTOM)
    body = _axis(unit)
    y_a = sc.y(reactant.energy)

    if diffusion_limit is not None:
        yd = sc.y(diffusion_limit)
        body.append(
            f"<line x1='{X_REACTANT - HALF_BAR}' y1='{yd:.1f}' x2='{WIDTH - _RIGHT}' "
            f"y2='{yd:.1f}' stroke='{MUTED}' stroke-width='1.2' stroke-dasharray='5 4'/>"
        )
        body.append(
            _text(
                WIDTH - _RIGHT,
                yd - 6,
                f"diffusion limit {number(diffusion_limit, decimals)}",
                fill=MUTED,
                anchor="end",
                size=11,
            )  # fmt: skip
        )

    # Curves first, bars and labels on top.
    for i, b in enumerate(branches):
        c = color(i)
        start = (X_REACTANT + HALF_BAR, y_a)
        end_y = sc.y(b.product.energy) if b.product else y_a
        end = (X_PRODUCT - HALF_BAR, end_y)
        if b.ts is not None:
            yt = sc.y(b.ts.energy)
            d = (
                f"M{start[0]},{start[1]:.1f} C{start[0] + 70},{start[1]:.1f} "
                f"{X_TS - 60},{yt:.1f} {X_TS},{yt:.1f} "
                f"C{X_TS + 60},{yt:.1f} {end[0] - 70},{end[1]:.1f} {end[0]},{end[1]:.1f}"
            )
            dash = "" if b.product else " stroke-dasharray='6 5'"
            body.append(f"<path d='{d}' fill='none' stroke='{c}' stroke-width='2.4'{dash}/>")
        else:
            body.append(
                f"<line x1='{start[0]}' y1='{start[1]:.1f}' x2='{end[0]}' y2='{end[1]:.1f}' "
                f"stroke='{c}' stroke-width='1.6' stroke-dasharray='6 5'/>"
            )

    body.append(
        f"<line x1='{X_REACTANT - HALF_BAR}' y1='{y_a:.1f}' x2='{X_REACTANT + HALF_BAR}' "
        f"y2='{y_a:.1f}' stroke='{INK}' stroke-width='3.5' stroke-linecap='round'/>"
    )
    body.append(_text(X_REACTANT, y_a - 10, reactant.label, weight="600"))
    body.append(_text(X_REACTANT, y_a + 20, number(reactant.energy, decimals), fill=MUTED))

    # TS labels above the peaks, spread so close barriers stay readable.
    ts = [(i, b.ts) for i, b in enumerate(branches) if b.ts is not None]
    ys = _spread([sc.y(t.energy) - 10 for _, t in ts], 16, upward=True)
    for (i, t), y in zip(ts, ys, strict=True):
        body.append(
            _text(
                X_TS,
                y,
                f"{t.label}  {number(t.energy, decimals)}",
                fill=color(i),
                size=12,
                weight="600",
                italic=not t.entered,
            )  # fmt: skip
        )

    products = [(i, b.product) for i, b in enumerate(branches) if b.product is not None]
    ys = _spread([sc.y(p.energy) + 4 for _, p in products], 16)
    for (i, p), y in zip(products, ys, strict=True):
        yp = sc.y(p.energy)
        body.append(
            f"<line x1='{X_PRODUCT - HALF_BAR}' y1='{yp:.1f}' x2='{X_PRODUCT + HALF_BAR}' "
            f"y2='{yp:.1f}' stroke='{color(i)}' stroke-width='3.5' stroke-linecap='round'/>"
        )
        body.append(
            _text(
                X_PRODUCT + HALF_BAR + 10,
                y,
                f"{p.label}  {number(p.energy, decimals)}",
                fill=color(i),
                anchor="start",
                weight="600",
                italic=not p.entered,
            )  # fmt: skip
        )
    return _svg(body)


def population_ladder(
    states: list[tuple[str, float, float]], unit: str, *, decimals: int = 2
) -> str:
    """States (label, relative energy, population fraction) as levels; the bar
    to the right of each level is its population."""
    sc = _Scale([e for _, e, _ in states], _TOP, HEIGHT - _BOTTOM)
    body = _axis(unit)
    x0, x1 = 250, 360  # level line
    bar_x, bar_max = 440, 200
    ys = _spread([sc.y(e) + 4 for _, e, _ in states], 15, upward=True)
    for (label, e, p), y_label in zip(states, ys, strict=True):
        y = sc.y(e)
        body.append(
            f"<line x1='{x0}' y1='{y:.1f}' x2='{x1}' y2='{y:.1f}' stroke='{INK}' "
            f"stroke-width='2.6' stroke-linecap='round'/>"
        )
        # Thin leaders join each level to its labels when labels had to move apart.
        for xa, xb in ((x0 - 74, x0 - 4), (x1 + 4, bar_x - 6)):
            ya, yb = (y_label - 4, y) if xa < x0 else (y, y_label - 4)
            body.append(f"<line x1='{xa}' y1='{ya:.1f}' x2='{xb}' y2='{yb:.1f}' "
                        f"stroke='{MUTED}' stroke-width='0.7'/>")  # fmt: skip
        body.append(_text(x0 - 80, y_label, label, anchor="end", size=12, weight="600"))
        body.append(_text(x0 - 6, y_label - 6, number(e, decimals), fill=MUTED, anchor="end",
                          size=10))  # fmt: skip
        w = max(bar_max * p, 1.5)
        body.append(
            f"<rect x='{bar_x}' y='{y_label - 12:.1f}' width='{w:.1f}' height='11' rx='2' "
            f"fill='{PALETTE[0]}' opacity='0.85'/>"
        )
        body.append(_text(bar_x + w + 6, y_label - 2, f"{p * 100:.1f} %", anchor="start", size=11))
    return _svg(body)
