from PIL import Image

from chemsidekick.core.schemas import Frame, Mark
from chemsidekick.core.spin import FRAMES, HEIGHT, WIDTH, bonds, mark_color, spin_gif

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


def _count(path, color, tol=40) -> int:
    """Pixels of the first frame close to `color`."""
    with Image.open(path) as im:
        data = im.convert("RGB").tobytes()
    px = [data[k : k + 3] for k in range(0, len(data), 3)]
    return sum(
        1 for r, g, b in px if abs(r - color[0]) + abs(g - color[1]) + abs(b - color[2]) < tol
    )


def test_mark_colors_match_the_viewer():
    assert mark_color("R") == mark_color("S") == (0x7C, 0x3A, 0xED)
    assert mark_color("r") == (0x0D, 0x94, 0x88)
    assert mark_color("E") == mark_color("Z") == (0xEA, 0x58, 0x0C)
    assert mark_color("?") == (0x4B, 0x55, 0x63)


def test_stereo_marks_are_drawn_as_badges(tmp_path):
    marked = BENZENE.model_copy(update={"marks": [Mark(atoms=[0], label="R")]})
    purple = (0x7C, 0x3A, 0xED)
    with_marks = spin_gif(marked, tmp_path / "m.gif")
    without = spin_gif(marked, tmp_path / "n.gif", marks=False)
    assert _count(with_marks, purple) > 30  # the badge behind the white "R"
    assert _count(without, purple) == 0
    assert _count(spin_gif(BENZENE, tmp_path / "plain.gif"), purple) == 0  # no marks, no badge


def test_double_bond_marks_sit_between_two_atoms(tmp_path):
    marked = BENZENE.model_copy(update={"marks": [Mark(atoms=[0, 1], label="E")]})
    assert _count(spin_gif(marked, tmp_path / "e.gif"), (0xEA, 0x58, 0x0C)) > 30
