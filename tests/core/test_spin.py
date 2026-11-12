from PIL import Image

from chemsidekick.core.schemas import Frame
from chemsidekick.core.spin import CARD_H, CARD_W, FRAMES, bonds, spin_card

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


def test_spin_card_is_an_endless_animated_gif(tmp_path):
    path = spin_card(BENZENE, tmp_path / "b.gif", "#1 · benzene", "D6h")
    with Image.open(path) as im:
        assert im.format == "GIF"
        assert im.size == (CARD_W, CARD_H)
        assert im.n_frames == FRAMES
        assert im.info.get("loop") == 0


def test_frames_differ_as_it_turns(tmp_path):
    with Image.open(spin_card(WATER, tmp_path / "w.gif")) as im:
        first = im.convert("RGB").tobytes()
        im.seek(FRAMES // 4)
        assert im.convert("RGB").tobytes() != first


def test_caption_is_drawn_only_when_given(tmp_path):
    def caption_ink(path) -> int:
        with Image.open(path) as im:
            strip = im.convert("L").crop((40, 256, CARD_W - 40, CARD_H - 4))
            return sum(1 for v in strip.tobytes() if v < 200)

    assert caption_ink(spin_card(WATER, tmp_path / "plain.gif")) == 0
    assert caption_ink(spin_card(WATER, tmp_path / "titled.gif", "#1 · water", "(x)")) > 50
