"""A rotating 3D view of a structure as an animated GIF "card".

A view of a tool's 3D result, like the HTML viewer (core/viewer.py), not a tool:
`csk gif` makes it for one structure frame. Launchers such as Raycast cannot run
an interactive 3D viewer, but they show animated GIFs.

The card has the same layout as the 2D drawing cards the Raycast extension
builds (apps/raycast/src/lib/cards.ts): a white card with a gray border, the
drawing area with the theme-color border, and a centered caption (title, then a
smaller gray note).

The structure turns once around the vertical axis, seen slightly from above,
with perspective (nearer atoms larger), shaded spheres, and depth fog (farther
atoms paler), so it reads as 3D. Bonds are inferred from distances only.
"""

from functools import cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from chemsidekick.core.schemas import Frame
from chemsidekick.core.theme import THEME_COLOR

# Card layout (px). Keep in sync with apps/raycast/src/lib/cards.ts.
CARD_W, CARD_H = 320, 296
PAD = 10
IMG_W, IMG_H = 300, 240
TITLE_Y, NOTE_Y = 270, 287  # text baselines
TITLE_SIZE, NOTE_SIZE = 14, 11
CARD_BORDER = (200, 200, 200)
TEXT_COLOR = (34, 34, 34)
NOTE_COLOR = (138, 138, 138)

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


@cache
def _font(size: int, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(
            "/System/Library/Fonts/Helvetica.ttc", size, index=1 if bold else 0
        )
    except OSError:  # not macOS
        return ImageFont.load_default(size)


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


def _card_background(title: str, note: str) -> Image.Image:
    """The card without the molecule, drawn at SS× size."""
    s = SS
    img = Image.new("RGB", (CARD_W * s, CARD_H * s), WHITE)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        [s * 0.75, s * 0.75, (CARD_W - 0.75) * s, (CARD_H - 0.75) * s],
        radius=12 * s, fill=WHITE, outline=CARD_BORDER, width=int(1.5 * s),
    )  # fmt: skip
    d.rounded_rectangle(
        [(PAD + 1) * s, (PAD + 1) * s, (PAD + IMG_W - 1) * s, (PAD + IMG_H - 1) * s],
        radius=10 * s, fill=WHITE, outline=_rgb(THEME_COLOR), width=2 * s,
    )  # fmt: skip
    if title:
        d.text((CARD_W / 2 * s, TITLE_Y * s), title, fill=TEXT_COLOR, anchor="ms",
               font=_font(TITLE_SIZE * s, bold=True))  # fmt: skip
    if note:
        d.text((CARD_W / 2 * s, NOTE_Y * s), note, fill=NOTE_COLOR, anchor="ms",
               font=_font(NOTE_SIZE * s, bold=False))  # fmt: skip
    return img


def spin_card(frame: Frame, path: Path, title: str = "", note: str = "") -> Path:
    """Write the rotating card for one structure as an animated GIF."""
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
    inner_w, inner_h = (IMG_W - 16) * SS, (IMG_H - 16) * SS
    px = min(inner_w / (2 * ext_x), inner_h / (2 * ext_y))
    cx, cy = (PAD + IMG_W / 2) * SS, (PAD + IMG_H / 2) * SS

    background = _card_background(title, note)
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
        frames.append(img.resize((CARD_W, CARD_H), Image.LANCZOS))
    # One palette for all frames, chosen from several viewing angles: about half the
    # file size of a palette per frame, and no flicker between frames.
    sample = Image.new("RGB", (CARD_W * 4, CARD_H))
    for n, k in enumerate(range(0, FRAMES, FRAMES // 4)):
        sample.paste(frames[k], (n * CARD_W, 0))
    palette = sample.quantize(colors=PALETTE_COLORS, method=Image.Quantize.MEDIANCUT)
    indexed = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    indexed[0].save(
        path, save_all=True, append_images=indexed[1:], duration=FRAME_MS, loop=0, optimize=True
    )
    return path
