import pytest

from chemsidekick.core.drawing import BACKDROP, with_backdrop

SVG = "<?xml version='1.0'?>\n<svg width='10px' viewBox='0 0 10 10'>\n<path d='M0 0'/></svg>"


def test_backdrop_is_drawn_first_inside_the_svg():
    out = with_backdrop(SVG)
    head, rest = out.split("viewBox='0 0 10 10'>", 1)
    assert rest.startswith(BACKDROP)
    assert rest.index("csk-backdrop") < rest.index("<path")
    assert "stop-color='#ffffff' stop-opacity='1'" in BACKDROP


def test_not_an_svg():
    with pytest.raises(ValueError):
        with_backdrop("<html></html>")
