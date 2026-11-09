from pathlib import Path

import pytest
from pydantic import BaseModel
from streamlit.testing.v1 import AppTest

import chemsidekick.ui
from chemsidekick.core.registry import Registry
from chemsidekick.core.schemas import ToolResult
from chemsidekick.ui.app import ALL, visible_tools

APP = str(Path(chemsidekick.ui.__file__).parent / "app.py")


@pytest.fixture
def app():
    return AppTest.from_file(APP, default_timeout=30).run()


def test_app_starts_with_element_selected(app):
    assert not app.exception
    assert any(b.key == "selected-tool-element" for b in app.button)
    assert any("REF-01" in m.value for m in app.markdown)


def test_lookup_shows_answer_tables_and_references(app):
    app.text_input(key="in-element-query").input("Fe")
    app.button(key="FormSubmitter:form-element-Run").click().run()
    assert not app.exception
    assert any("Fe · Iron · Z = 26" in m.value for m in app.markdown)
    assert len(app.dataframe) == 2  # properties + isotopes
    assert any("Prohaska" in c.value for c in app.caption)


def test_unknown_element_shows_error(app):
    app.text_input(key="in-element-query").input("Iorn")
    app.button(key="FormSubmitter:form-element-Run").click().run()
    assert "Did you mean" in app.error[0].value


def test_save_button_copies_result(app, isolated_user_dirs):
    app.text_input(key="in-element-query").input("H")
    app.button(key="FormSubmitter:form-element-Run").click().run()
    save = next(b for b in app.button if b.key and b.key.startswith("save-"))
    save.click().run()
    assert "Saved to" in app.success[0].value
    assert (isolated_user_dirs / "saved" / "element").exists()


def test_search_hides_non_matching_tools(app):
    app.text_input[0].input("zzzz").run()
    assert not any(b.key and "tool-element" in b.key for b in app.button)
    assert "No tool matches" in app.info[0].value


def _latex_script():
    from chemsidekick.core.schemas import Formula, ToolResult
    from chemsidekick.ui.render import render_result

    render_result(
        ToolResult(
            answer="k",
            formulas=[Formula(latex=r"k = \kappa \frac{k_B T}{h}", text="k = κ kB T / h")],
        )
    )


def test_formulas_are_rendered_as_latex():
    at = AppTest.from_function(_latex_script).run()
    assert r"k = \kappa \frac{k_B T}{h}" in at.latex[0].value


# --- New tools appear without UI changes --------------------------------------


class In(BaseModel):
    x: int = 1


def test_new_tools_show_up_in_grid_by_category_and_search():
    reg = Registry()

    @reg.tool(name="viewer", number=1, title="Viewer", summary="3D view", category="structure",
              keywords=["geometry"])  # fmt: skip
    def viewer(inp: In) -> ToolResult:
        return ToolResult(answer="")

    @reg.tool(name="lookup", number=1, title="Lookup", summary="", category="reference")
    def lookup(inp: In) -> ToolResult:
        return ToolResult(answer="")

    assert [t.name for t in visible_tools(reg, ALL, "")] == ["viewer", "lookup"]
    assert [t.name for t in visible_tools(reg, "Structure", "")] == ["viewer"]
    assert [t.name for t in visible_tools(reg, "Reference", "geometry")] == ["viewer"]
