"""Read small tables pasted as text, e.g. two columns copied from a spreadsheet.

    name   E(Hartree)      shift
    conf1  -1234.567890    3.42
    conf2  -1234.567012    3.61

Rules (the same for every tool that takes a pasted table):
- one row per line; columns separated by tabs, commas, semicolons, or spaces
- a first line without any number is a header and is skipped (its names are kept)
- a first column that is not a number is the row's label
- empty lines and lines starting with # are ignored
- numbers may use 1e-3, 1.2×10⁻³, or the Unicode minus sign
"""

import re
from dataclasses import dataclass

from chemsidekick.core.schemas import ToolError
from chemsidekick.core.units import UnitError, parse_number


@dataclass(frozen=True)
class Row:
    line: int  # 1-based line number in the pasted text
    label: str  # "" when the row has no label
    values: tuple[float, ...]


@dataclass(frozen=True)
class Parsed:
    header: tuple[str, ...]  # column names from a header line, or ()
    rows: tuple[Row, ...]

    @property
    def labeled(self) -> bool:
        return any(r.label for r in self.rows)


def _number(cell: str) -> float | None:
    try:
        value, rest = parse_number(cell)
    except UnitError:
        return None
    return value if value is not None and not rest else None


def _cells(line: str) -> list[str]:
    # Tabs, commas and semicolons separate columns; otherwise any run of spaces does.
    if re.search(r"[\t,;]", line):
        parts = re.split(r"[\t,;]", line)
    else:
        parts = line.split()
    return [p.strip() for p in parts if p.strip()]


def parse_table(text: str, *, min_values: int = 1, max_values: int | None = None) -> Parsed:
    """Parse pasted rows. Every row must have between min_values and max_values
    numbers (after an optional label); otherwise a ToolError names the line."""
    header: tuple[str, ...] = ()
    rows: list[Row] = []
    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cells = _cells(line)
        numbers = [_number(c) for c in cells]
        if not rows and not header and all(v is None for v in numbers):
            header = tuple(cells)
            continue
        label = ""
        if numbers and numbers[0] is None:
            label, cells, numbers = cells[0], cells[1:], numbers[1:]
        bad = [c for c, v in zip(cells, numbers, strict=True) if v is None]
        if bad:
            raise ToolError(f"Line {n}: {bad[0]!r} is not a number.")
        values = tuple(v for v in numbers if v is not None)
        if len(values) < min_values:
            need = "a number" if min_values == 1 else f"{min_values} numbers"
            raise ToolError(f"Line {n}: needs {need}, got {len(values)}.")
        if max_values is not None and len(values) > max_values:
            raise ToolError(f"Line {n}: at most {max_values} numbers, got {len(values)}.")
        rows.append(Row(n, label, values))
    if not rows:
        raise ToolError("No rows: paste one value per line (a label in front is optional).")
    return Parsed(header, tuple(rows))
