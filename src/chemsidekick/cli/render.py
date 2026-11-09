"""Print any ToolResult to the terminal, in the shared order:
answer -> formulas -> details (tables, files) -> warnings, then footnotes
(notes, assumptions, references) dimmed at the bottom.
"""

from rich import box
from rich.console import Console
from rich.table import Table as RichTable
from rich.text import Text

from chemsidekick.core.external import ExternalProgram, Located, env_var_name
from chemsidekick.core.registry import CATEGORIES, ToolSpec
from chemsidekick.core.results import RecentEntry
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
    for i, col in enumerate(t.columns):
        minor = i in t.minor_columns
        out.add_column(col, no_wrap=wide or minor, style="dim" if minor else None)
    for row in t.rows:
        out.add_row(*(_cell(v) for v in row))
    return out


def render_result(result: ToolResult, console: Console) -> None:
    console.print(Text(result.answer, style="bold"))
    for h in result.highlights:
        console.print(Text.assemble((f"  {h.label}: ", "dim"), (h.value, "")))

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
    for line in [*result.notes, *(f"Assumes: {a}" for a in result.assumptions)]:
        console.print(Text(line, style="dim"))
    if result.sources:
        console.print(Text("References", style="dim bold"))
        for s in result.sources:
            console.print(Text(f"  {s}", style="dim"))


def render_tool_list(groups: dict[str, list[ToolSpec]], console: Console) -> None:
    for cat, specs in groups.items():
        out = RichTable(title=CATEGORIES[cat].title, title_justify="left", title_style="bold",
                        box=box.SIMPLE_HEAD, padding=(0, 1))  # fmt: skip
        out.add_column("ID")
        out.add_column("Command")
        out.add_column("Description")
        out.add_column("Resources")
        for s in specs:
            out.add_row(Text(s.id), Text(f"csk {s.name}"), Text(s.summary), Text(s.resources))
        console.print(out)


def render_recent(entries: list[RecentEntry], console: Console) -> None:
    out = RichTable(box=box.SIMPLE_HEAD, padding=(0, 1))
    for col in ["#", "ID", "Tool", "When", "Answer"]:
        out.add_column(col)
    for e in entries:
        out.add_row(
            Text(str(e.number)),
            Text(e.tool_id),
            Text(e.tool),
            Text(e.created.strftime("%Y-%m-%d %H:%M")),
            Text(e.answer),
        )
    console.print(out)
    console.print(Text("`csk save <#>` keeps a result.", style="dim"))


def render_doctor(rows: list[tuple[ExternalProgram, Located | None]], console: Console) -> None:
    if not rows:
        console.print("No external programs registered.")
        return
    out = RichTable(box=box.SIMPLE_HEAD, padding=(0, 1))
    for col in ["Program", "Status", "Found by", "Command", "Version"]:
        out.add_column(col)
    for program, located in rows:
        if located is None:
            out.add_row(
                Text(program.name),
                Text("missing", style="red"),
                Text("—"),
                Text(program.install_hint or f"set {env_var_name(program)}"),
                Text("—"),
            )
        else:
            out.add_row(
                Text(program.name),
                Text("ok", style="green"),
                Text(located.found_by),
                Text(" ".join(located.command)),
                Text(located.version or "?"),
            )
    console.print(out)
