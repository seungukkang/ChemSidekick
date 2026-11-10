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
