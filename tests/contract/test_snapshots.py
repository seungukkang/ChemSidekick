"""Contract schemas and fixtures stay in sync with core/contract.py.

If a test here fails after an intended change, run
`uv run python scripts/export_contract.py` and review the diff. Removing or
renaming a field, or changing its meaning, also needs CONTRACT_VERSION + 1.
"""

import importlib.util
import json
from pathlib import Path

import pytest

from chemsidekick.core.contract import (
    ErrorResponse,
    GifResponse,
    RunResponse,
    SaveResponse,
    ToolListResponse,
)

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "export_contract", ROOT / "scripts/export_contract.py"
)
export = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export)


def test_schemas_match_the_models():
    assert export.check_schemas(), "run: uv run python scripts/export_contract.py"


def test_every_fixture_exists():
    for name in export.FIXTURES:
        assert (export.FIXTURE_DIR / f"{name}.json").exists(), name


@pytest.mark.parametrize("name", sorted(export.FIXTURES))
def test_fixture_matches_the_models(name):
    data = json.loads((export.FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    if not data["ok"]:
        ErrorResponse.model_validate(data)
    elif "tools" in data:
        ToolListResponse.model_validate(data)
    elif "saved_to" in data:
        SaveResponse.model_validate(data)
    elif "frames" in data and "path" in data:
        GifResponse.model_validate(data)
    else:
        RunResponse.model_validate(data)
