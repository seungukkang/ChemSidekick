from chemsidekick.core.theme import THEME_COLOR
from chemsidekick.ui import app


def test_selected_tool_border_uses_the_theme_color():
    assert f"border: 2px solid {THEME_COLOR}" in app._CSS
    assert "__THEME__" not in app._CSS
