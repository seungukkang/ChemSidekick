import json
from typing import Literal

from pydantic import BaseModel, Field
from typer.testing import CliRunner

from chemsidekick.cli.main import app, build_app
from chemsidekick.core.registry import Registry
from chemsidekick.core.schemas import ToolError, ToolResult

runner = CliRunner()


def test_list_shows_tools_by_category():
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "Reference" in result.stdout
    assert "csk element" in result.stdout
    assert "REF-01" in result.stdout


def test_search():
    result = runner.invoke(app, ["search", "isotope"])
    assert result.exit_code == 0
    assert "csk element" in result.stdout


def test_search_without_match_fails():
    result = runner.invoke(app, ["search", "zzzz"])
    assert result.exit_code == 1


def test_element_card():
    result = runner.invoke(app, ["element", "Fe"])
    assert result.exit_code == 0
    assert "Fe · Iron · Z = 26" in result.stdout
    assert "[Ar] 3d⁶ 4s²" in result.stdout


def test_element_json_output():
    result = runner.invoke(app, ["element", "26", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["answer"] == "Fe · Iron · Z = 26"
    assert data["data"]["element"]["config"]["value"] == "[Ar] 3d6 4s2"


def test_element_unknown_is_a_clean_error():
    result = runner.invoke(app, ["element", "Iorn"])
    assert result.exit_code == 1
    assert "Did you mean" in result.stderr
    assert "Traceback" not in result.stderr


# --- New tools appear in the CLI without touching interface code ------------


class FakeInput(BaseModel):
    smiles: str = Field(description="A molecule", json_schema_extra={"positional": True})
    count: int = Field(default=2, ge=1, description="How many", json_schema_extra={"short": "-n"})
    style: Literal["stick", "sphere"] = "stick"
    verbose: bool = False


def fake_app():
    reg = Registry()

    @reg.tool(name="fake", number=1, title="Fake", summary="A fake tool", category="structure")
    def fake(inp: FakeInput) -> ToolResult:
        if inp.smiles == "bad":
            raise ToolError("bad molecule")
        return ToolResult(answer=f"{inp.smiles} x{inp.count} {inp.style} {inp.verbose}")

    return build_app(reg)


def test_registered_tool_becomes_a_command_with_generated_options():
    app_ = fake_app()
    result = runner.invoke(app_, ["fake", "CCO", "-n", "3", "--style", "sphere", "--verbose"])
    assert result.exit_code == 0, result.output
    assert "CCO x3 sphere True" in result.stdout

    assert "CCO x2 stick False" in runner.invoke(app_, ["fake", "CCO"]).stdout
    assert "csk fake" in runner.invoke(app_, ["list"]).stdout


def test_generated_options_are_validated():
    app_ = fake_app()
    assert runner.invoke(app_, ["fake", "CCO", "--style", "cartoon"]).exit_code != 0
    bad_count = runner.invoke(app_, ["fake", "CCO", "-n", "0"])
    assert bad_count.exit_code == 1
    assert "count" in bad_count.stderr
    assert "bad molecule" in runner.invoke(app_, ["fake", "bad"]).stderr


# --- Recent results, save, doctor ------------------------------------------


def test_each_run_is_kept_and_can_be_saved(isolated_user_dirs):
    out = runner.invoke(app, ["element", "Fe"])
    assert "Result #1" in out.stdout
    runner.invoke(app, ["element", "Cu"])

    recent = runner.invoke(app, ["recent"])
    assert "Cu · Copper" in recent.stdout and "Fe · Iron" in recent.stdout

    saved = runner.invoke(app, ["save", "1"])
    assert saved.exit_code == 0
    assert list((isolated_user_dirs / "saved" / "element").iterdir())


def test_save_flag_and_missing_result(isolated_user_dirs):
    out = runner.invoke(app, ["element", "H", "--save-to", str(isolated_user_dirs / "here")])
    assert "Saved to" in out.stdout
    assert (isolated_user_dirs / "here" / "element").exists()
    assert runner.invoke(app, ["save", "42"]).exit_code == 1


def test_failed_run_is_not_kept():
    runner.invoke(app, ["element", "Iorn"])
    assert "No recent results" in runner.invoke(app, ["recent"]).stdout


def test_doctor_runs():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0


# --- xyz: file or standard input, and the HTML 3D viewer --------------------

WATER = "3\nwater\nO 0 0 0.1173\nH 0 0.7572 -0.4692\nH 0 -0.7572 -0.4692\n"


def test_xyz_from_standard_input_writes_viewer():
    result = runner.invoke(app, ["xyz", "--no-open", "--json"], input=WATER)
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["answer"] == "H2O · 3 atoms · 1 frame"
    viewer = next(a for a in data["artifacts"] if a["kind"] == "html")
    page = open(viewer["path"], encoding="utf-8").read()
    assert "3Dmol" in page and '"symbols":["O","H","H"]' in page


def test_xyz_from_file(tmp_path):
    path = tmp_path / "water.xyz"
    path.write_text(WATER)
    result = runner.invoke(app, ["xyz", str(path), "--no-open"])
    assert result.exit_code == 0, result.output
    assert "H2O · 3 atoms · 1 frame" in result.stdout
    assert "viewer.html" in result.stdout


def test_xyz_missing_file_is_a_clean_error():
    result = runner.invoke(app, ["xyz", "nope.xyz", "--no-open"])
    assert result.exit_code == 1
    assert "File not found: nope.xyz" in result.stderr


def test_xyz_opens_browser_unless_no_open(monkeypatch):
    opened = []
    monkeypatch.setattr("chemsidekick.cli.main.webbrowser.open", opened.append)
    runner.invoke(app, ["xyz"], input=WATER)
    runner.invoke(app, ["xyz", "--no-open"], input=WATER)
    assert len(opened) == 1 and opened[0].endswith("viewer.html")


def test_stereo_runs_in_a_subprocess_and_writes_files():
    result = runner.invoke(app, ["stereo", "CC(Br)C(Br)C", "--no-open", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["answer"] == "3 stereoisomers (1 pair of enantiomers, 1 meso)"
    assert {a["kind"] for a in data["artifacts"]} == {"svg", "sdf", "html"}


def test_stereo_max_flag_and_bad_smiles():
    ok = runner.invoke(app, ["stereo", "CC(O)C(O)C(O)C", "--max", "2", "--no-3d", "--no-open"])
    assert ok.exit_code == 0, ok.output
    assert "first 2 of up to" in ok.stdout
    bad = runner.invoke(app, ["stereo", "C1CC", "--no-open"])
    assert bad.exit_code == 1
    assert "ring is opened but never closed" in bad.stderr


def test_formulas_are_shown_as_text_in_the_terminal():
    """CLI shows the text form of a formula; the LaTeX form is for Streamlit (001 §6)."""
    import io

    from rich.console import Console

    from chemsidekick.cli.render import render_result
    from chemsidekick.core.schemas import Formula

    out = io.StringIO()
    render_result(
        ToolResult(
            answer="rate",
            formulas=[Formula(latex=r"k = \kappa \frac{k_B T}{h}", text="k = κ kB T / h")],
        ),
        Console(file=out, width=100),
    )
    text = out.getvalue()
    assert "k = κ kB T / h" in text
    assert r"\frac" not in text
