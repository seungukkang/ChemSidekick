"""The JSON contract (core/contract.py): what interfaces such as Raycast rely on."""

import json
import os
from pathlib import Path

import pytest
from contract_fakes import REG
from typer.testing import CliRunner

from chemsidekick.cli.main import app, build_app
from chemsidekick.core.contract import (
    CONTRACT_VERSION,
    ErrorResponse,
    GifResponse,
    RunResponse,
    SaveResponse,
    ToolListResponse,
)
from chemsidekick.core.results import RecentStore

runner = CliRunner()
fake_app = build_app(REG)

WATER = "3\nwater\nO 0 0 0.1173\nH 0 0.7572 -0.4692\nH 0 -0.7572 -0.4692\n"


def only_json(result) -> dict:
    """stdout must be exactly one JSON object (nothing else printed)."""
    data = json.loads(result.stdout)
    assert isinstance(data, dict)
    assert data["contract"] == CONTRACT_VERSION
    return data


def ok_run(result) -> RunResponse:
    assert result.exit_code == 0, result.output
    return RunResponse.model_validate(only_json(result))


def failed(result, error_type: str, code: int) -> ErrorResponse:
    assert result.exit_code == code, result.output
    response = ErrorResponse.model_validate(only_json(result))
    assert response.error.type == error_type
    return response


# --- Success ------------------------------------------------------------------


def test_tool_command_json_is_a_run_response():
    r = ok_run(runner.invoke(app, ["element", "Fe", "--json"]))
    assert r.result.answer == "Fe · Iron · Z = 26"
    assert r.run.tool == "element" and r.run.tool_id == "REF-01"
    assert r.run.recorded and r.run.number is not None
    assert Path(r.run.folder).is_dir()


def test_artifact_paths_are_absolute():
    r = ok_run(runner.invoke(app, ["stereo", "CC(Br)C(Br)C", "--no-open", "--json"]))
    assert r.result.artifacts
    for a in r.result.artifacts:
        assert a.path.is_absolute() and a.path.exists()
    assert any(a.kind == "html" for a in r.result.artifacts)  # the 3D viewer page


# --- csk run: input as JSON on standard input ---------------------------------


def test_run_reads_json_input():
    r = ok_run(runner.invoke(app, ["run", "element", "--json"], input='{"query": "Fe"}'))
    assert r.result.answer == "Fe · Iron · Z = 26"


def test_run_accepts_a_tool_id():
    r = ok_run(runner.invoke(app, ["run", "REF-01", "--json"], input='{"query": "26"}'))
    assert r.run.tool == "element"


def test_run_with_empty_input_uses_defaults():
    r = ok_run(runner.invoke(app, ["run", "element", "--json"], input=""))
    assert r.result.tables[0].action_field == "query"  # the periodic table


def test_run_takes_long_text_inside_the_json():
    payload = json.dumps({"text": WATER, "style": "stick"})
    r = ok_run(runner.invoke(app, ["run", "xyz", "--no-open", "--json"], input=payload))
    assert r.result.answer == "H2O · 3 atoms · 1 frame"


def test_run_with_stereo_options_by_field_name():
    payload = json.dumps({"smiles": "CC(O)C(O)C(O)C", "max_isomers": 2, "skip_3d": True})
    r = ok_run(runner.invoke(app, ["run", "stereo", "--json"], input=payload))
    assert "first 2 of up to" in " ".join(r.result.warnings)


def test_run_without_json_prints_text():
    result = runner.invoke(app, ["run", "element"], input='{"query": "Fe"}')
    assert result.exit_code == 0
    assert "Fe · Iron · Z = 26" in result.stdout


# --- Errors: always JSON on stdout, with the contract's exit code -------------


def test_tool_error_is_input_error():
    r = failed(runner.invoke(app, ["element", "Iorn", "--json"]), "input", 1)
    assert "Did you mean" in r.error.message


def test_invalid_smiles_is_input_error():
    r = failed(runner.invoke(app, ["stereo", "C1CC", "--no-open", "--json"]), "input", 1)
    assert "ring is opened but never closed" in r.error.message


def test_validation_error_names_the_field():
    payload = json.dumps({"smiles": "CC", "max_isomers": 0})
    r = failed(runner.invoke(app, ["run", "stereo", "--json"], input=payload), "input", 1)
    assert r.error.details[0].field == "max_isomers"


def test_unknown_field_is_input_error():
    r = failed(runner.invoke(app, ["run", "element", "--json"], input='{"qery": "Fe"}'), "input", 1)
    assert r.error.details[0].field == "qery"


@pytest.mark.parametrize(
    "stdin, message",
    [("{not json", "not valid JSON"), ('["Fe"]', "must be a JSON object")],
)
def test_bad_json_input(stdin, message):
    r = failed(runner.invoke(app, ["run", "element", "--json"], input=stdin), "input", 1)
    assert message in r.error.message


def test_unknown_tool():
    r = failed(runner.invoke(app, ["run", "nope", "--json"], input="{}"), "input", 1)
    assert "csk list" in r.error.message


def test_crash_has_a_traceback():
    r = failed(runner.invoke(fake_app, ["boom", "--json"]), "crash", 4)
    assert "RuntimeError" in r.error.message
    assert "a bug in the tool" in r.error.traceback


def test_time_limit():
    result = runner.invoke(fake_app, ["slow", "--seconds", "30", "--timeout", "0.5", "--json"])
    r = failed(result, "limit", 3)
    assert "longer than 0.5 s" in r.error.message


def test_heavy_tool_needs_confirmation_in_json_mode():
    failed(runner.invoke(fake_app, ["big", "--json"]), "confirm", 5)
    confirmed = runner.invoke(fake_app, ["big", "--yes", "--timeout", "10", "--json"])
    assert ok_run(confirmed).result.answer == "heavy done"


def test_missing_program():
    r = failed(runner.invoke(fake_app, ["needs-xtb", "--json"]), "missing_program", 6)
    assert "not-a-real-program" in r.error.message


def test_bad_config_file(isolated_user_dirs):
    Path(os.environ["CSK_CONFIG"]).write_text("this is = = not toml")
    r = failed(runner.invoke(app, ["element", "Fe", "--json"]), "config", 7)
    assert "invalid TOML" in r.error.message


def test_errors_without_json_are_text_with_the_same_exit_code():
    result = runner.invoke(fake_app, ["needs-xtb"])
    assert result.exit_code == 6
    assert "Error:" in result.stderr and result.stdout == ""


def test_usage_errors_stay_typer_text():
    result = runner.invoke(app, ["element", "--no-such-option", "--json"])
    assert result.exit_code == 2


# --- --no-record --------------------------------------------------------------


def test_no_record_keeps_recent_results_unchanged():
    store = RecentStore()
    before = len(store.entries())
    r1 = ok_run(runner.invoke(app, ["element", "--no-record", "--json"]))
    r2 = ok_run(runner.invoke(app, ["element", "--no-record", "--json"]))
    assert len(store.entries()) == before
    assert r1.run.number is None and not r1.run.recorded
    assert Path(r1.run.folder).parent == store.scratch_root
    assert r1.run.folder != r2.run.folder  # Raycast caches images by path


def test_no_record_files_still_exist():
    r = ok_run(runner.invoke(app, ["stereo", "CCC(Br)C", "--no-record", "--no-open", "--json"]))
    assert all(a.path.exists() for a in r.result.artifacts)


def test_old_scratch_folders_are_deleted():
    store = RecentStore()
    old = store.scratch_folder("element")
    os.utime(old, (0, 0))
    store.scratch_folder("element")
    assert not old.exists()


def test_no_record_cannot_be_saved():
    result = runner.invoke(app, ["element", "Fe", "--no-record", "--save", "--json"])
    failed(result, "input", 1)


# --- Tool list ----------------------------------------------------------------


def test_list_json():
    result = runner.invoke(app, ["list", "--json"])
    assert result.exit_code == 0
    r = ToolListResponse.model_validate(only_json(result))
    assert [t.id for t in r.tools] == ["REF-01", "REF-02", "STR-01", "STR-02", "ENE-01"]
    assert {c.code for c in r.categories} >= {"STR", "REF"}
    stereo = next(t for t in r.tools if t.name == "stereo")
    props = stereo.input_schema["properties"]
    assert props["smiles"]["positional"] is True and props["smiles"]["label"] == "SMILES"
    assert props["max_isomers"]["maximum"] == 1024
    element = next(t for t in r.tools if t.name == "element")
    assert element.start_view == "Periodic table" and element.available


def test_list_json_marks_tools_with_missing_programs():
    r = ToolListResponse.model_validate(only_json(runner.invoke(fake_app, ["list", "--json"])))
    needs = next(t for t in r.tools if t.name == "needs-xtb")
    assert not needs.available and "not-a-real-program" in needs.unavailable_reason


def test_search_json_ranks_and_allows_no_match():
    r = ToolListResponse.model_validate(only_json(runner.invoke(app, ["search", "xyz", "--json"])))
    assert r.tools[0].name == "xyz"
    empty = runner.invoke(app, ["search", "zzzz", "--json"])
    assert empty.exit_code == 0
    assert ToolListResponse.model_validate(only_json(empty)).tools == []


# --- Save ---------------------------------------------------------------------


def test_save_json(isolated_user_dirs):
    run = ok_run(runner.invoke(app, ["element", "Fe", "--json"]))
    result = runner.invoke(app, ["save", "--json"])
    assert result.exit_code == 0
    r = SaveResponse.model_validate(only_json(result))
    assert r.number == run.run.number
    assert Path(r.saved_to).is_dir() and Path(r.saved_to).is_relative_to(isolated_user_dirs)


def test_save_without_results_is_input_error():
    failed(runner.invoke(app, ["save", "--json"]), "input", 1)


# --- gif: rotating 3D view of a result's structure ----------------------------


def test_gif_from_a_stereo_frame():
    stereo = ok_run(runner.invoke(app, ["stereo", "CC(Br)C(Br)C", "--no-open", "--json"]))
    frame = stereo.result.structures[0].frames[0]
    payload = json.dumps({"frame": frame.model_dump(mode="json")})
    result = runner.invoke(app, ["gif", "--json"], input=payload)
    assert result.exit_code == 0, result.output
    r = GifResponse.model_validate(only_json(result))
    assert Path(r.path).exists() and r.path.endswith(".gif")
    assert Path(r.path).parent.parent == RecentStore().scratch_root  # not a recent result
    again = GifResponse.model_validate(
        only_json(runner.invoke(app, ["gif", "--json"], input=payload))
    )
    assert again.path != r.path  # a fresh file each time (Raycast caches images by path)


def test_gif_rejects_bad_frames():
    bad = json.dumps({"frame": {"symbols": ["O", "H"], "coords": [[0, 0, 0]]}})
    r = failed(runner.invoke(app, ["gif", "--json"], input=bad), "input", 1)
    assert "frame" in r.error.message
    failed(runner.invoke(app, ["gif", "--json"], input='{"frame": {}, "colour": 1}'), "input", 1)
