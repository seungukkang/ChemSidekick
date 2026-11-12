import re
from pathlib import Path

from chemsidekick.core.theme import THEME_COLOR

RAYCAST_THEME = Path(__file__).resolve().parents[2] / "apps" / "raycast" / "src" / "theme.ts"


def test_raycast_uses_the_same_theme_color():
    m = re.search(r'THEME_COLOR\s*=\s*"(#[0-9a-fA-F]{6})"', RAYCAST_THEME.read_text())
    assert m is not None, f"THEME_COLOR not found in {RAYCAST_THEME}"
    assert m.group(1).lower() == THEME_COLOR.lower()
