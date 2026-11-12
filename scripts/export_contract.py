"""Write the JSON contract's schemas and example responses.

    uv run python scripts/export_contract.py             # write schemas + fixtures
    uv run python scripts/export_contract.py --check     # exit 1 if schemas are out of date

Schemas go to schemas/contract-v<N>/ (generated from core/contract.py; a test
compares them). Fixtures go to tests/contract/fixtures/: real csk responses with
machine-specific parts (temporary paths, timings) replaced, for interface tests
(Raycast) that must not run csk.
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path

from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chemsidekick.core.contract import (  # noqa: E402
    CONTRACT_VERSION,
    ErrorResponse,
    GifRequest,
    GifResponse,
    RunResponse,
    SaveResponse,
    ToolListResponse,
)

SCHEMA_DIR = ROOT / "schemas" / f"contract-v{CONTRACT_VERSION}"
FIXTURE_DIR = ROOT / "tests" / "contract" / "fixtures"

MODELS = {
    "run-response": RunResponse,
    "error-response": ErrorResponse,
    "tool-list": ToolListResponse,
    "save-response": SaveResponse,
    "gif-request": GifRequest,
    "gif-response": GifResponse,
}

WATER = "3\nwater\nO 0 0 0.1173\nH 0 0.7572 -0.4692\nH 0 -0.7572 -0.4692\n"

# name -> (csk arguments, standard input)
FIXTURES: dict[str, tuple[list[str], str | None]] = {
    "list": (["list", "--json"], None),
    "element-periodic-table": (["run", "element", "--no-record", "--json"], "{}"),
    "element-card": (["run", "element", "--json"], '{"query": "Fe"}'),
    "element-error": (["run", "element", "--json"], '{"query": "Iorn"}'),
    "xyz-water": (["run", "xyz", "--no-open", "--json"], json.dumps({"text": WATER})),
    "stereo-dibromobutane": (
        ["run", "stereo", "--no-open", "--json"],
        '{"smiles": "CC(Br)C(Br)C"}',
    ),
    "stereo-error": (["run", "stereo", "--no-open", "--json"], '{"smiles": "C1CC"}'),
    "validation-error": (["run", "stereo", "--json"], '{"smiles": "CC", "max_isomers": 0}'),
    "save": (["save", "--json"], None),
    "gif": (
        ["gif", "--json"],
        json.dumps(
            {
                "frame": {
                    "symbols": ["O", "H", "H"],
                    "coords": [[0, 0, 0.1173], [0, 0.7572, -0.4692], [0, -0.7572, -0.4692]],
                    "comment": "water",
                },
                "title": "water",
                "note": "H2O",
            }
        ),
    ),
}

FIXTURE_ROOT = "/fixture"  # stands in for the temporary folder in every path


def schemas() -> dict[str, str]:
    return {
        name: json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n"
        for name, model in MODELS.items()
    }


def write_schemas() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in schemas().items():
        (SCHEMA_DIR / f"{name}.schema.json").write_text(text, encoding="utf-8")
    print(f"wrote {len(MODELS)} schemas to {SCHEMA_DIR.relative_to(ROOT)}")


def check_schemas() -> bool:
    ok = True
    for name, text in schemas().items():
        path = SCHEMA_DIR / f"{name}.schema.json"
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            print(f"out of date: {path.relative_to(ROOT)}")
            ok = False
    return ok


def _normalize(value, tmp: str):
    if isinstance(value, dict):
        out = {k: _normalize(v, tmp) for k, v in value.items()}
        if "elapsed_s" in out:
            out["elapsed_s"] = 0.1
        if out.get("peak_memory_mb") is not None:
            out["peak_memory_mb"] = 50.0
        return out
    if isinstance(value, list):
        return [_normalize(v, tmp) for v in value]
    if isinstance(value, str) and tmp in value:
        value = value.replace(tmp, FIXTURE_ROOT)
        # Random scratch-folder suffixes and save timestamps change on every run.
        value = re.sub(r"(/scratch/[a-z0-9-]+?-)[a-z0-9_]{8}\b", r"\1xxxxxxxx", value)
        value = re.sub(r"/\d{8}-\d{6}\b", "/20260101-000000", value)
    return value


def write_fixtures() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        os.environ["CSK_CACHE_DIR"] = f"{tmp}/cache/recent"
        config = Path(tmp) / "config.toml"
        config.write_text(f'save_dir = "{tmp}/saved"\n')
        os.environ["CSK_CONFIG"] = str(config)
        from chemsidekick.cli.main import app

        runner = CliRunner()
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        for name, (args, stdin) in FIXTURES.items():
            result = runner.invoke(app, args, input=stdin)
            data = _normalize(json.loads(result.stdout), tmp)
            data["csk_version"] = "0.0.0"  # fixtures do not change with every release
            text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            (FIXTURE_DIR / f"{name}.json").write_text(text, encoding="utf-8")
    print(f"wrote {len(FIXTURES)} fixtures to {FIXTURE_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if check_schemas() else 1)
    write_schemas()
    write_fixtures()
