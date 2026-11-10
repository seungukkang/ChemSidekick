import pytest
from pydantic import ValidationError

from chemsidekick.core.schemas import Frame, Structure3D
from chemsidekick.core.viewer import THREEDMOL_URL, viewer_html


def structure(comment: str = "") -> Structure3D:
    return Structure3D(
        frames=[Frame(symbols=["H", "H"], coords=[(0, 0, 0), (0, 0, 0.74)], comment=comment)],
        title="H2",
    )


def test_page_loads_3dmol_and_contains_atoms():
    page = viewer_html(structure())
    assert THREEDMOL_URL in page
    assert '"symbols":["H","H"]' in page


def test_comment_cannot_close_the_script_block():
    page = viewer_html(structure("</script><script>alert(1)</script>"))
    assert "</script><script>alert" not in page


def test_start_frame_must_exist():
    with pytest.raises(ValidationError):
        Structure3D(frames=structure().frames, start_frame=1)


def test_pages_numbers_and_marks_reach_the_page():
    import json
    import re

    frame = Frame(
        symbols=["C", "O", "H"],
        coords=[(0, 0, 0), (1.4, 0, 0), (-0.5, 0.9, 0)],
        numbers=["1", "", ""],
        marks=[{"atoms": [0], "label": "R"}, {"atoms": [0, 1], "label": "E"}],
    )
    s = Structure3D(frames=[frame, frame], navigation="pages", page_name="Isomer",
                    numbers_name="Locants")  # fmt: skip
    page = viewer_html(s)
    data = json.loads(re.search(r"const DATA = (.*);\n", page).group(1))
    assert (data["navigation"], data["page_name"], data["numbers_name"]) == (
        "pages",
        "Isomer",
        "Locants",
    )
    assert data["frames"][0]["numbers"] == ["1", "", ""]
    assert data["frames"][0]["marks"][1] == {"atoms": [0, 1], "label": "E"}
    assert 'id="marks"' in page and "Stereocenters" in page


@pytest.mark.parametrize(
    "bad",
    [{"numbers": ["1"]}, {"marks": [{"atoms": [5], "label": "R"}]}],
)
def test_numbers_and_marks_must_match_the_atoms(bad):
    with pytest.raises(ValidationError):
        Frame(symbols=["H", "H"], coords=[(0, 0, 0), (0, 0, 0.74)], **bad)
