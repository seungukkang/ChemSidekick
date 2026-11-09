import math

import pytest
from pydantic import ValidationError

from chemsidekick.core.schemas import Frame, Structure3D, Table, ToolResult

WATER = Frame(
    symbols=["O", "H", "H"],
    coords=[(0.0, 0.0, 0.117), (0.0, 0.757, -0.469), (0.0, -0.757, -0.469)],
    comment="water",
)


def test_frame_valid():
    assert WATER.n_atoms == 3


def test_frame_length_mismatch():
    with pytest.raises(ValidationError, match="3 symbols but 2 coordinate rows"):
        Frame(symbols=["O", "H", "H"], coords=[(0, 0, 0), (1, 0, 0)])


def test_frame_rejects_nan():
    with pytest.raises(ValidationError, match="atom 2"):
        Frame(symbols=["H", "H"], coords=[(0, 0, 0), (math.nan, 0, 0)])


def test_structure_needs_a_frame():
    with pytest.raises(ValidationError):
        Structure3D(frames=[])


def test_table_row_width_checked():
    with pytest.raises(ValidationError, match="row 2 has 1 cells"):
        Table(columns=["a", "b"], rows=[[1, 2], [3]])


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        ToolResult(answer="x", answr="typo")


def test_result_json_round_trip():
    result = ToolResult(
        answer="H2O · 3 atoms",
        structures=[Structure3D(frames=[WATER])],
        warnings=["test"],
    )
    again = ToolResult.model_validate_json(result.model_dump_json())
    assert again == result
