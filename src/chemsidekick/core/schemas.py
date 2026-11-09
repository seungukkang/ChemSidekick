"""Shared input/output types used by every tool.

Every tool returns a ToolResult, so the CLI and the UI can render any tool
with the same code, in the same order: answer -> evidence -> details.
"""

import math
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# ---------------------------------------------------------------------------
# Common value types
# Tools build their inputs and outputs from these, so that later one tool's
# output can be passed to another tool's input (backlog F09).
# ---------------------------------------------------------------------------

Smiles = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
"""A SMILES string. Chemical validity is checked by the tool (RDKit)."""

ElementQuery = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
"""An element symbol, English name, or atomic number, e.g. "Fe", "iron", "26"."""


class ToolError(Exception):
    """An error caused by the user's input, with a message meant for the user.

    Tools raise this (e.g. "Unknown element 'Iorn'. Did you mean: Fe (Iron)?").
    Interfaces show the message as-is, without a traceback.
    """


class _Model(BaseModel):
    # Reject unknown fields so that typos fail loudly instead of being ignored.
    model_config = ConfigDict(extra="forbid")


class Frame(_Model):
    """One 3D geometry: element symbols and Cartesian coordinates in Å."""

    symbols: list[str] = Field(min_length=1)
    coords: list[tuple[float, float, float]]
    comment: str = ""

    @model_validator(mode="after")
    def _check(self) -> "Frame":
        if len(self.symbols) != len(self.coords):
            raise ValueError(f"{len(self.symbols)} symbols but {len(self.coords)} coordinate rows")
        for i, xyz in enumerate(self.coords, start=1):
            if not all(math.isfinite(v) for v in xyz):
                raise ValueError(f"atom {i} has a non-finite coordinate: {xyz}")
        return self

    @property
    def n_atoms(self) -> int:
        return len(self.symbols)


class Structure3D(_Model):
    """A 3D structure with one or more frames (conformers, trajectory, IRC)."""

    frames: list[Frame] = Field(min_length=1)
    title: str = ""


# ---------------------------------------------------------------------------
# Result parts
# ---------------------------------------------------------------------------


class Formula(_Model):
    """An equation, stored twice: LaTeX for the UI, plain text for the terminal."""

    latex: str
    text: str


class Constant(_Model):
    """A physical constant used in a calculation, with its source."""

    name: str
    symbol: str
    value: float
    unit: str
    source: str


Cell = str | int | float | None


class Table(_Model):
    title: str = ""
    columns: list[str]
    rows: list[list[Cell]]
    # Indexes of columns that are for reference only (e.g. a "Check" column);
    # interfaces draw them narrow and dimmed.
    minor_columns: list[int] = []
    # Clickable cells: clicking a cell in `action_columns` runs the same tool again
    # with input field `action_field` set to the cell's text (e.g. a periodic table
    # where clicking "Fe" opens the iron card). Interfaces without clicks ignore it.
    action_field: str | None = None
    action_columns: list[int] = []

    @model_validator(mode="after")
    def _check(self) -> "Table":
        for i, row in enumerate(self.rows, start=1):
            if len(row) != len(self.columns):
                raise ValueError(
                    f"row {i} has {len(row)} cells but there are {len(self.columns)} columns"
                )
        return self


ArtifactKind = Literal["svg", "png", "sdf", "xyz", "html", "json"]


class Artifact(_Model):
    """A file produced by a tool."""

    kind: ArtifactKind
    path: Path
    title: str = ""


class ToolResult(_Model):
    """What every tool returns."""

    # Answer
    answer: str
    # Evidence
    formulas: list[Formula] = []
    constants: list[Constant] = []
    assumptions: list[str] = []
    sources: list[str] = []
    # Standing explanations (legends, data caveats) shown small at the bottom.
    # Use `warnings` only for problems with this particular input or result.
    notes: list[str] = []
    # Details
    tables: list[Table] = []
    structures: list[Structure3D] = []
    artifacts: list[Artifact] = []
    warnings: list[str] = []
    # Raw values for machines (--json output, later API/MCP/tool linking)
    data: dict[str, Any] = {}
