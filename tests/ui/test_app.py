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
    tables = [m.value for m in app.markdown if 'class="csk-table' in m.value]
    assert len(tables) == 4  # identity, electronic structure, chemical properties, isotopes
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


def test_xyz_shows_3d_viewer(app):
    app.button(key="tool-xyz").click().run()
    app.text_area(key="in-xyz-text").input("O 0 0 0\nH 0 0.76 0.59\nH 0 -0.76 0.59\n")
    app.button(key="FormSubmitter:form-xyz-Run").click().run()
    assert not app.exception
    assert any("H2O · 3 atoms · 1 frame" in m.value for m in app.markdown)
    viewers = app.get("iframe")
    assert len(viewers) == 1
    assert "3Dmol" in viewers[0].proto.srcdoc


def test_stereo_shows_drawing_and_3d(app):
    app.button(key="tool-stereo").click().run()
    app.text_input(key="in-stereo-smiles").input("CCC(Br)C")
    app.button(key="FormSubmitter:form-stereo-Run").click().run()
    assert not app.exception
    assert any("2 stereoisomers" in m.value for m in app.markdown)
    assert len(app.get("image")) == 2  # one drawing per isomer
    assert len(app.get("iframe")) == 1  # the 3D viewer


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

    assert [t.name for t in visible_tools(reg, ALL, "")] == ["lookup", "viewer"]
    assert [t.name for t in visible_tools(reg, "Structure", "")] == ["viewer"]
    assert [t.name for t in visible_tools(reg, "Reference", "geometry")] == ["viewer"]


# --- Start view: periodic table with clickable elements ------------------------


def _cell(app, symbol):
    return next(
        b
        for b in app.button
        if b.key and b.key.startswith("act-") and b.label.split("\n\n")[1] == symbol
    )


def test_periodic_table_is_shown_on_open(app):
    assert any("Periodic table · 118 elements" in m.value for m in app.markdown)
    assert sum(1 for b in app.button if b.key and b.key.startswith("act-")) == 118


def test_clicking_an_element_opens_its_card_and_back_returns(app):
    _cell(app, "Fe").click().run()
    assert not app.exception
    assert any("Fe · Iron · Z = 26" in m.value for m in app.markdown)
    assert app.text_input(key="in-element-query").value == "Fe"

    next(b for b in app.button if b.key == "back").click().run()
    assert any("Periodic table · 118 elements" in m.value for m in app.markdown)
    assert app.text_input(key="in-element-query").value == ""


def test_units_opens_on_the_unit_list_and_converts(app):
    app.button(key="tool-units").click().run()
    assert not app.exception
    assert any("All units" in m.value for m in app.markdown)
    app.text_input(key="in-units-query").input("1 eV to kcal/mol")
    app.button(key="FormSubmitter:form-units-Run").click().run()
    assert not app.exception and not app.error
    assert any("1 eV = 23\\.0605 kcal/mol" in m.value for m in app.markdown)  # markdown-escaped


def test_profile_view_redraws_as_values_change(app):
    app.button(key="tool-profile").click().run()
    assert not app.exception and not app.error
    assert any("Kinetic B : C = 96\\.7 : 3\\.3" in m.value for m in app.markdown)
    assert app.image  # the profile drawing
    app.text_input(key="pf-T").input("100 C").run()  # hotter: less selective
    assert not app.exception and not app.error
    assert any("Kinetic B : C = 93\\." in m.value for m in app.markdown)
    app.text_input(key="pf-T").input("298.15").run()
    app.segmented_control(key="pf-mode").set_value("populations").run()
    assert not app.exception
    assert any("conf1 61\\.9 %" in m.value for m in app.markdown)


def test_profile_table_rows_become_paths():
    from chemsidekick.ui.profile_view import paths_text

    rows = [
        {"name": "", "ts": "20", "product": None},
        {"name": "C", "ts": "", "product": ""},
        {"name": "two words", "ts": " 1 h ", "product": "-2"},
    ]
    assert paths_text(rows) == "P1\t20\t-\ntwo_words\t1h\t-2"
