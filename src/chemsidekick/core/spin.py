"""A rotating 3D view of a structure as an animated GIF.

A view of a tool's 3D result, like the HTML viewer (core/viewer.py), not a tool:
`csk gif` makes it for one structure frame. Launchers such as Raycast cannot run
an interactive 3D viewer, but they show animated GIFs.

It looks like the 2D drawings (core/drawing.py): the same size, a white backdrop
with rounded corners and a border in the theme color, so an interface can swap
a drawing for its 3D view in place. The structure turns once around the vertical
axis, seen slightly from above, with perspective (nearer atoms larger), shaded
spheres, and depth fog (farther atoms paler), so it reads as 3D. Bonds are
inferred from distances only.
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from chemsidekick.core.drawing import BORDER_COLOR, BORDER_WIDTH, CORNER_RADIUS
from chemsidekick.core.schemas import Frame

# Same size as the RDKit drawings of the stereo tool.
WIDTH, HEIGHT = 300, 240
MARGIN = 8  # between the border and the structure

FRAMES = 36  # 10° per frame
FRAME_MS = 80  # one turn in about 3 s
SS = 3  # draw this many times larger, then shrink: smooth edges
TILT = 0.35  # rad, looking slightly from above
CAMERA = 3.0  # camera distance in units of the structure's radius (smaller = stronger perspective)
FOG = 0.45  # the farthest atoms fade this far toward white
PALETTE_COLORS = 96

# Jmol colors, the same scheme as the 3D viewer (3Dmol.js). Display colors only.
JMOL = {
    "H": "FFFFFF", "He": "D9FFFF", "Li": "CC80FF", "Be": "C2FF00", "B": "FFB5B5", "C": "909090",
    "N": "3050F8", "O": "FF0D0D", "F": "90E050", "Ne": "B3E3F5", "Na": "AB5CF2", "Mg": "8AFF00",
    "Al": "BFA6A6", "Si": "F0C8A0", "P": "FF8000", "S": "FFFF30", "Cl": "1FF01F", "Ar": "80D1E3",
    "K": "8F40D4", "Ca": "3DFF00", "Ti": "BFC2C7", "Cr": "8A99C7", "Mn": "9C7AC7", "Fe": "E06633",
    "Co": "F090A0", "Ni": "50D050", "Cu": "C88033", "Zn": "7D80B0", "Ga": "C28F8F", "Ge": "668F8F",
    "As": "BD80E3", "Se": "FFA100", "Br": "A62929", "Kr": "5CB8D1", "Rb": "702EB0", "Sr": "00FF00",
    "Pd": "006985", "Ag": "C0C0C0", "Sn": "668080", "Sb": "9E63B5", "Te": "D47A00", "I": "940094",
    "Xe": "429EB0", "Cs": "57178F", "Ba": "00C900", "Pt": "D0D0E0", "Au": "FFD123", "Hg": "B8B8D0",
}  # fmt: skip
DEFAULT_COLOR = "FF1493"
DEFAULT_RADIUS_A = 1.5  # covalent radius (Å) for elements without data
BOND_TOLERANCE = 1.15  # bonded if distance < tolerance × (sum of covalent radii)

RGB = tuple[int, int, int]
WHITE: RGB = (255, 255, 255)


def _rgb(hex6: str) -> RGB:
    hex6 = hex6.lstrip("#")
    return int(hex6[0:2], 16), int(hex6[2:4], 16), int(hex6[4:6], 16)


def _mix(c: RGB, other: RGB, t: float) -> RGB:
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c, other, strict=True))  # type: ignore[return-value]


def _covalent_radius(symbol: str) -> float:
    from chemsidekick.tools.reference.element import by_symbol  # element data (pm)

    el = by_symbol(symbol)
    value = el["covalent_radius_pm"]["value"] if el else None
    return value / 100 if value else DEFAULT_RADIUS_A


def bonds(frame: Frame) -> list[tuple[int, int]]:
    """Pairs of atoms closer than BOND_TOLERANCE × the sum of their covalent radii."""
    xyz = np.array(frame.coords)
    radii = np.array([_covalent_radius(s) for s in frame.symbols])
    dist = np.linalg.norm(xyz[:, None, :] - xyz[None, :, :], axis=2)
    limit = BOND_TOLERANCE * (radii[:, None] + radii[None, :])
    i, j = np.where(np.triu((dist < limit) & (dist > 0.1), k=1))
    return list(zip(i.tolist(), j.tolist(), strict=True))


def _sphere(d: ImageDraw.ImageDraw, x: float, y: float, r: float, color: RGB, fog: float) -> None:
    """A sphere lit from the upper left: dark rim, then the base color, then a highlight."""
    base = _mix(color, WHITE, fog)
    rim = _mix(base, (0, 0, 0), 0.45)
    steps = 14
    for s in range(steps):
        t = s / (steps - 1)  # 0 = rim, 1 = highlight
        rr = r * (1 - 0.82 * t)
        off = -0.35 * r * t
        if t < 0.75:
            c = _mix(rim, base, min(1.0, t * 1.6))
        else:
            c = _mix(base, WHITE, (t - 0.75) / 0.25 * 0.7)
        d.ellipse([x + off - rr, y + off - rr, x + off + rr, y + off + rr], fill=c)


def _stick(d: ImageDraw.ImageDraw, a, b, wa: float, wb: float, ca: RGB, cb: RGB) -> None:
    """A stick from a to b, thicker at the nearer end, colored half by each atom."""
    a, b = np.array(a), np.array(b)
    v = b - a
    n = np.array([-v[1], v[0]]) / (np.linalg.norm(v) + 1e-9)
    m, wm = (a + b) / 2, (wa + wb) / 2
    for p, q, w1, w2, c in ((a, m, wa, wm, ca), (m, b, wm, wb, cb)):
        d.polygon(
            [
                tuple(p + n * w1 / 2),
                tuple(q + n * w2 / 2),
                tuple(q - n * w2 / 2),
                tuple(p - n * w1 / 2),
            ],
            fill=c,
        )


def _background() -> Image.Image:
    """White, with the drawings' rounded border, drawn at SS× size."""
    s, h = SS, BORDER_WIDTH / 2
    img = Image.new("RGB", (WIDTH * s, HEIGHT * s), WHITE)
    ImageDraw.Draw(img).rounded_rectangle(
        [h * s, h * s, (WIDTH - h) * s, (HEIGHT - h) * s],
        radius=CORNER_RADIUS * s,
        fill=WHITE,
        outline=_rgb(BORDER_COLOR),
        width=int(BORDER_WIDTH * s),
    )
    return img


def spin_gif(frame: Frame, path: Path) -> Path:
    """Write the rotating view of one structure as an animated GIF."""
    xyz = np.array(frame.coords, dtype=float)
    xyz -= xyz.mean(axis=0)
    symbols = frame.symbols
    pairs = bonds(frame)
    colors = [_rgb(JMOL.get(sym, DEFAULT_COLOR)) for sym in symbols]
    rad = np.array([0.18 + 0.25 * _covalent_radius(sym) for sym in symbols])  # display radii (Å)

    radius = float(np.linalg.norm(xyz, axis=1).max()) + 0.5
    camera = CAMERA * radius
    tilt = np.array([[1, 0, 0], [0, np.cos(TILT), -np.sin(TILT)], [0, np.sin(TILT), np.cos(TILT)]])

    def view(k: int) -> tuple[np.ndarray, np.ndarray]:
        t = 2 * np.pi * k / FRAMES
        turn = np.array([[np.cos(t), 0, np.sin(t)], [0, 1, 0], [-np.sin(t), 0, np.cos(t)]])
        p = xyz @ turn.T @ tilt.T  # z > 0: toward the viewer
        return p, camera / (camera - p[:, 2])  # positions, perspective factor per atom

    # Scale so the whole turn fits inside the drawing area.
    views = [view(k) for k in range(FRAMES)]
    ext_x = max(float(np.max((np.abs(p[:, 0]) + rad) * f)) for p, f in views)
    ext_y = max(float(np.max((np.abs(p[:, 1]) + rad) * f)) for p, f in views)
    inner_w, inner_h = (WIDTH - 2 * MARGIN) * SS, (HEIGHT - 2 * MARGIN) * SS
    px = min(inner_w / (2 * ext_x), inner_h / (2 * ext_y))
    cx, cy = WIDTH / 2 * SS, HEIGHT / 2 * SS

    background = _background()
    frames = []
    for p, f in views:
        img = background.copy()
        d = ImageDraw.Draw(img)
        sx, sy = cx + p[:, 0] * px * f, cy - p[:, 1] * px * f
        fog = np.clip((radius - p[:, 2]) / (2 * radius), 0, 1) * FOG
        items = [(p[i, 2], -1, i) for i in range(len(p))]
        items += [((p[i, 2] + p[j, 2]) / 2 - 0.05, i, j) for i, j in pairs]
        for _, i, j in sorted(items, key=lambda item: item[0]):  # far to near
            if i < 0:
                _sphere(d, sx[j], sy[j], rad[j] * px * f[j], colors[j], fog[j])
            else:
                ci = _mix(_mix(colors[i], (0, 0, 0), 0.25), WHITE, fog[i])
                cj = _mix(_mix(colors[j], (0, 0, 0), 0.25), WHITE, fog[j])
                _stick(
                    d, (sx[i], sy[i]), (sx[j], sy[j]), 0.16 * px * f[i], 0.16 * px * f[j], ci, cj
                )
        frames.append(img.resize((WIDTH, HEIGHT), Image.LANCZOS))
    # One palette for all frames, chosen from several viewing angles: about half the
    # file size of a palette per frame, and no flicker between frames.
    sample = Image.new("RGB", (WIDTH * 4, HEIGHT))
    for n, k in enumerate(range(0, FRAMES, FRAMES // 4)):
        sample.paste(frames[k], (n * WIDTH, 0))
    palette = sample.quantize(colors=PALETTE_COLORS, method=Image.Quantize.MEDIANCUT)
    # Averaging in the palette turns the white background slightly gray: snap
    # near-white entries back to white so it matches the 2D drawings.
    colors = palette.getpalette()[: 3 * PALETTE_COLORS]
    colors = [255 if min(colors[k : k + 3]) >= 245 else v for k in range(0, len(colors), 3)
              for v in colors[k : k + 3]]  # fmt: skip
    # One extra entry, used only for the transparent corners outside the rounded border.
    palette.putpalette([*colors, 255, 0, 255])
    outside = _outside_mask()
    indexed = []
    for f in frames:
        q = f.quantize(palette=palette, dither=Image.Dither.NONE)
        q.paste(TRANSPARENT, mask=outside)
        indexed.append(q)
    indexed[0].save(
        path, save_all=True, append_images=indexed[1:], duration=FRAME_MS, loop=0,
        transparency=TRANSPARENT, disposal=2, optimize=False,
    )  # fmt: skip
    return path


TRANSPARENT = PALETTE_COLORS  # palette index of the transparent corners


def _outside_mask() -> Image.Image:
    """255 outside the rounded border (the corners), 0 inside, at the final size."""
    s = SS
    big = Image.new("L", (WIDTH * s, HEIGHT * s), 255)
    ImageDraw.Draw(big).rounded_rectangle(
        [0, 0, WIDTH * s - 1, HEIGHT * s - 1], radius=CORNER_RADIUS * s, fill=0
    )
    # Only clearly outside pixels become transparent; the antialiased edge stays.
    return big.resize((WIDTH, HEIGHT), Image.LANCZOS).point(lambda v: 255 if v > 200 else 0)
