from typing import Literal

import pytest
from pydantic import BaseModel, Field

from chemsidekick.core.schemas import ElementQuery
from chemsidekick.ui.forms import widget_specs


class Everything(BaseModel):
    smiles: str = Field(description="A molecule")
    xyz: str = Field(default="", json_schema_extra={"multiline": True, "label": "XYZ"})
    count: int = Field(default=8, ge=1, le=512)
    temperature: float = 298.15
    style: Literal["stick", "sphere"] = "sphere"
    labels: bool = False
    element: ElementQuery | None = None


def test_each_field_type_gets_a_widget():
    specs = {s.name: s for s in widget_specs(Everything)}
    assert specs["smiles"].kind == "text" and specs["smiles"].help == "A molecule"
    assert specs["smiles"].default is None  # required
    assert specs["xyz"].kind == "textarea" and specs["xyz"].label == "XYZ"
    assert specs["count"].kind == "int"
    assert (specs["count"].min_value, specs["count"].max_value) == (1, 512)
    assert specs["temperature"].kind == "float" and specs["temperature"].default == 298.15
    assert specs["style"].kind == "select" and specs["style"].choices == ("stick", "sphere")
    assert specs["labels"].kind == "checkbox"
    assert specs["element"].kind == "text" and specs["element"].optional


def test_unsupported_type_is_reported():
    class Bad(BaseModel):
        values: list[int] = []

    with pytest.raises(TypeError, match="unsupported field type"):
        widget_specs(Bad)
