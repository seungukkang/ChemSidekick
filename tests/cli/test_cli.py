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
    assert data["data"]["element"]["config"] == "[Ar] 3d6 4s2"


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

    @reg.tool(name="fake", title="Fake", summary="A fake tool", category="structure")
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
