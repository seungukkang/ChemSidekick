"""Print any ToolResult to the terminal, in the shared order:
answer -> evidence (formulas, constants, assumptions) -> details.
Sources are printed last, dimmed, as footnotes.
"""

from rich import box
from rich.console import Console
from rich.table import Table as RichTable
from rich.text import Text

from chemsidekick.core.registry import CATEGORIES, ToolSpec
from chemsidekick.core.schemas import Table, ToolResult


def _cell(value: object) -> Text:
    # Text() is used everywhere so that strings like "[Ar] 3d6" are not
    # mistaken for Rich markup tags.
    return Text("—" if value is None else str(value))


_WIDE = 10  # tables with more columns than this are drawn compactly


def _table(t: Table) -> RichTable:
    wide = len(t.columns) > _WIDE
    out = RichTable(
        title=t.title or None,
        title_justify="left",
        title_style="bold",
        box=None if wide else box.SIMPLE_HEAD,
        padding=(0, 1),
        collapse_padding=wide,
        pad_edge=not wide,
    )
    for col in t.columns:
        out.add_column(col, no_wrap=wide)
    for row in t.rows:
        out.add_row(*(_cell(v) for v in row))
    return out


def render_result(result: ToolResult, console: Console) -> None:
    console.print(Text(result.answer, style="bold"))

    for f in result.formulas:
        console.print(Text("  " + f.text))
    if result.constants:
        console.print(
            _table(
                Table(
                    title="Constants",
                    columns=["Name", "Symbol", "Value", "Unit", "Source"],
                    rows=[
                        [c.name, c.symbol, f"{c.value:g}", c.unit, c.source]
                        for c in result.constants
                    ],
                )
            )
        )
    for a in result.assumptions:
        console.print(Text(f"  Assumes: {a}", style="italic"))

    for t in result.tables:
        console.print(_table(t))
    for s in result.structures:
        n_atoms = s.frames[0].n_atoms
        console.print(Text(f"3D structure: {n_atoms} atoms, {len(s.frames)} frame(s)"))
    if result.artifacts:
        console.print(Text("Files:", style="bold"))
        for a in result.artifacts:
            console.print(Text(f"  {a.kind:5} {a.path}"))
    for w in result.warnings:
        console.print(Text(f"Warning: {w}", style="yellow"))
    for s in result.sources:
        console.print(Text(f"Source: {s}", style="dim"))


def render_tool_list(groups: dict[str, list[ToolSpec]], console: Console) -> None:
    for cat, specs in groups.items():
        out = RichTable(title=CATEGORIES[cat], title_justify="left", title_style="bold",
                        box=box.SIMPLE_HEAD, padding=(0, 1))  # fmt: skip
        out.add_column("Command")
        out.add_column("Description")
        out.add_column("Resources")
        for s in specs:
            out.add_row(Text(f"csk {s.name}"), Text(s.summary), Text(s.resources))
        console.print(out)
