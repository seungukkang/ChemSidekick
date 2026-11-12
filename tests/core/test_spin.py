from PIL import Image

from chemsidekick.core.schemas import Frame
from chemsidekick.core.spin import FRAMES, HEIGHT, WIDTH, bonds, spin_gif

WATER = Frame(
    symbols=["O", "H", "H"],
    coords=[(0, 0, 0.1173), (0, 0.7572, -0.4692), (0, -0.7572, -0.4692)],
)
_BENZENE = """\
C 0.00000 1.39700 0.00000
C 1.20984 0.69850 0.00000
C 1.20984 -0.69850 0.00000
C 0.00000 -1.39700 0.00000
C -1.20984 -0.69850 0.00000
C -1.20984 0.69850 0.00000
H 0.00000 2.48100 0.00000
H 2.14862 1.24050 0.00000
H 2.14862 -1.24050 0.00000
H 0.00000 -2.48100 0.00000
H -2.14862 -1.24050 0.00000
H -2.14862 1.24050 0.00000"""
BENZENE = Frame(
    symbols=[line.split()[0] for line in _BENZENE.splitlines()],
    coords=[tuple(float(v) for v in line.split()[1:]) for line in _BENZENE.splitlines()],
)


def test_bonds_from_distances():
    assert len(bonds(WATER)) == 2
    pairs = bonds(BENZENE)
    assert len(pairs) == 12  # 6 C-C + 6 C-H, no H-H or across the ring
    assert (0, 3) not in pairs


def test_spin_gif_is_an_endless_animated_gif(tmp_path):
    path = spin_gif(BENZENE, tmp_path / "b.gif")
    with Image.open(path) as im:
        assert im.format == "GIF"
        assert im.size == (WIDTH, HEIGHT) == (300, 240)  # same as the 2D drawings
        assert im.n_frames == FRAMES
        assert im.info.get("loop") == 0


def test_frames_differ_as_it_turns(tmp_path):
    with Image.open(spin_gif(WATER, tmp_path / "w.gif")) as im:
        first = im.convert("RGB").tobytes()
        im.seek(FRAMES // 4)
        assert im.convert("RGB").tobytes() != first


def test_looks_like_the_drawings_white_with_a_theme_border(tmp_path):
    with Image.open(spin_gif(WATER, tmp_path / "w.gif")) as im:
        rgb = im.convert("RGB")
        r, g, b = rgb.getpixel((WIDTH // 2, 1))  # top edge: the border
        assert r > 200 and g < 120 and b < 120  # red theme color
        assert min(rgb.getpixel((12, HEIGHT // 2))) >= 245  # inside: white (after the palette)


def test_corners_outside_the_rounded_border_are_transparent(tmp_path):
    with Image.open(spin_gif(WATER, tmp_path / "w.gif")) as im:
        rgba = im.convert("RGBA")
        assert rgba.getpixel((0, 0))[3] == 0  # corner: see-through on a dark page
        assert rgba.getpixel((WIDTH // 2, HEIGHT // 2))[3] == 255
