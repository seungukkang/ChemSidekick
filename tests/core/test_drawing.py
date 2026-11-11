import pytest

from chemsidekick.core.drawing import BACKDROP, BORDER_COLOR, with_backdrop

SVG = "<?xml version='1.0'?>\n<svg width='300px' viewBox='0 0 300 240'>\n<path d='M0 0'/></svg>"


def test_backdrop_is_drawn_first_inside_the_svg():
    out = with_backdrop(SVG)
    head, rest = out.split("viewBox='0 0 300 240'>", 1)
    assert rest.startswith("<rect id='csk-backdrop'")
    assert rest.index("csk-backdrop") < rest.index("<path")


def test_backdrop_is_solid_white_with_a_colored_border():
    rect = with_backdrop(SVG).split("viewBox='0 0 300 240'>", 1)[1].split("/>", 1)[0]
    assert "fill='#ffffff'" in rect
    assert f"stroke='{BORDER_COLOR}'" in rect
    assert "opacity" not in rect


def test_backdrop_uses_the_viewbox_size_inset_by_half_the_border():
    # Percent sizes break in macOS's SVG renderer (Raycast): width='100%' -> small square.
    out = with_backdrop(SVG)
    assert "x='1' y='1' width='298' height='238'" in out
    assert "%" not in out.split("<path", 1)[0].split("viewBox='0 0 300 240'>", 1)[1]


def test_viewbox_with_offset_and_double_quotes():
    out = with_backdrop('<svg viewBox="-5 -5 50.5 20"><path d="M0 0"/></svg>')
    assert "x='-4' y='-4' width='48.5' height='18'" in out


def test_without_a_viewbox_the_backdrop_falls_back_to_percentages():
    out = with_backdrop("<svg width='10px'><path d='M0 0'/></svg>")
    assert BACKDROP in out


def test_not_an_svg():
    with pytest.raises(ValueError):
        with_backdrop("<html></html>")


def test_border_is_the_theme_color():
    from chemsidekick.core.theme import THEME_COLOR

    assert BORDER_COLOR == THEME_COLOR == "#ff4b4b"
