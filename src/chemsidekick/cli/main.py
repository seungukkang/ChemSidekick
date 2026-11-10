"""Entry point for the `csk` command.

Built-in commands (list, search, recent, save, doctor, ui) are defined here. Every tool in the
registry becomes a `csk <tool>` command automatically: its options are
generated from the tool's Pydantic input model.
"""

import inspect
import subprocess
import sys
import types
import typing
import webbrowser
from pathlib import Path
from typing import Any, Literal, Union

import typer
from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo
from rich.console import Console

from chemsidekick import __version__
from chemsidekick.cli.render import (
    render_doctor,
    render_recent,
    render_result,
    render_tool_list,
)
from chemsidekick.core.config import ConfigError, load_config
from chemsidekick.core.external import doctor
from chemsidekick.core.registry import Registry, ToolSpec, discover
from chemsidekick.core.results import RecentStore
from chemsidekick.core.runner import ConfirmationRequired, RunError, run_tool
from chemsidekick.core.schemas import Artifact, ToolError, ToolResult
from chemsidekick.core.viewer import viewer_html

console = Console()
err_console = Console(stderr=True)


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"chemsidekick {__version__}")
        raise typer.Exit()


def _cli_type(annotation: Any) -> Any:
    """Reduce a field type to something Typer understands.

    `Annotated[...]` and `X | None` are unwrapped (Pydantic still validates the
    full type afterwards). `Literal["a", "b"]` is kept: Typer shows it as choices.
    """
    while typing.get_origin(annotation) is typing.Annotated:
        annotation = typing.get_args(annotation)[0]
    origin = typing.get_origin(annotation)
    if origin in (Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) != 1:
            raise TypeError(f"unsupported union type for CLI: {annotation}")
        return _cli_type(args[0])
    if origin is Literal or annotation in (str, int, float, bool):
        return annotation
    raise TypeError(f"unsupported field type for CLI: {annotation}")


def _parameter(name: str, field: FieldInfo) -> inspect.Parameter:
    """One input-model field -> one CLI argument or option."""
    cli_type = _cli_type(field.annotation)
    extra = field.json_schema_extra if isinstance(field.json_schema_extra, dict) else {}
    default = ... if field.is_required() else field.default
    common: dict[str, Any] = {"help": field.description}
    if extra.get("file_input"):
        # Text that is usually long (e.g. XYZ): a file path, or read from standard input.
        info = typer.Argument(
            None, show_default=False, metavar="[FILE]",
            help=f"{field.description} Use '-' or leave out to read standard input.",
        )  # fmt: skip
        return inspect.Parameter(
            name, inspect.Parameter.KEYWORD_ONLY, default=info, annotation=str | None
        )
    if extra.get("positional"):
        info = typer.Argument(default, show_default=False, **common)
    else:
        # json_schema_extra={"flag": "--max"} replaces the name derived from the field.
        flags = [str(extra.get("flag") or f"--{name.replace('_', '-')}")]
        if extra.get("short"):
            flags.append(str(extra["short"]))
        info = typer.Option(default, *flags, **common)
    return inspect.Parameter(
        name, inspect.Parameter.KEYWORD_ONLY, default=info, annotation=cli_type
    )


def _common(name: str, annotation: Any, option: Any) -> inspect.Parameter:
    return inspect.Parameter(
        name, inspect.Parameter.KEYWORD_ONLY, default=option, annotation=annotation
    )


# Options shared by every tool command. Their names start with "csk_" so they
# can never clash with a field of a tool's input model.
_COMMON_PARAMS = [
    _common("csk_json", bool, typer.Option(False, "--json", help="Print the result as JSON.")),
    _common("csk_save", bool, typer.Option(False, "--save", help="Save the result.")),
    _common(
        "csk_save_to",
        Path | None,
        typer.Option(None, "--save-to", help="Save the result into this folder."),
    ),
    _common(
        "csk_timeout",
        float | None,
        typer.Option(None, "--timeout", help="Time limit in seconds (overrides the default)."),
    ),
    _common("csk_yes", bool, typer.Option(False, "--yes", "-y", help="Skip confirmation.")),
    _common(
        "csk_no_open",
        bool,
        typer.Option(False, "--no-open", help="Do not open the 3D viewer in the browser."),
    ),
]


def _file_fields(model: type[BaseModel]) -> list[str]:
    return [
        n
        for n, f in model.model_fields.items()
        if isinstance(f.json_schema_extra, dict) and f.json_schema_extra.get("file_input")
    ]


def _read_text_input(value: str | None) -> str:
    """A file path -> its text; '-' or nothing -> standard input."""
    if value is None or value == "-":
        if sys.stdin.isatty():
            _fail("Give a file, or pipe the text in (e.g. `pbpaste | csk xyz`).")
        return sys.stdin.read()
    path = Path(value).expanduser()
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    if "\n" in value:
        return value  # the text itself, e.g. from a script
    _fail(f"File not found: {value}")


def _add_viewer(result: ToolResult, folder: Path) -> Path | None:
    """Save an HTML 3D viewer next to the result (the terminal cannot draw 3D)."""
    if not result.structures:
        return None
    paths = []
    for i, s in enumerate(result.structures, start=1):
        name = "viewer.html" if len(result.structures) == 1 else f"viewer-{i}.html"
        path = folder / name
        path.write_text(viewer_html(s), encoding="utf-8")
        result.artifacts.append(Artifact(kind="html", path=path, title="3D viewer"))
        paths.append(path)
    return paths[0]


def _fail(message: str) -> typing.NoReturn:
    err_console.print(f"[red]Error:[/red] {message}", highlight=False, markup=True)
    raise typer.Exit(code=1)


def _input_error_message(e: ValidationError) -> str:
    parts = []
    for err in e.errors():
        where = ".".join(str(p) for p in err["loc"]) or "input"
        parts.append(f"{where}: {err['msg']}")
    return "; ".join(parts)


def _load_config():
    try:
        return load_config()
    except ConfigError as e:
        _fail(str(e))


def _tool_command(spec: ToolSpec):
    """Build a Typer command function for one tool."""
    model: type[BaseModel] = spec.input_model
    params = [_parameter(n, f) for n, f in model.model_fields.items()] + _COMMON_PARAMS

    def command(**kwargs: Any) -> None:
        common = {k: kwargs.pop(k) for k in list(kwargs) if k.startswith("csk_")}
        for name in _file_fields(model):
            kwargs[name] = _read_text_input(kwargs[name])
        config = _load_config()
        try:
            inp = model(**kwargs)
        except ValidationError as e:
            _fail(_input_error_message(e))

        confirmed = common["csk_yes"]
        if spec.resources == "heavy" and not confirmed:
            if not sys.stdin.isatty():
                _fail(f"{spec.title} is a heavy tool. Add --yes to run it.")
            confirmed = typer.confirm(f"{spec.title} is a heavy tool. Run it?")
            if not confirmed:
                raise typer.Exit(code=1)

        store = RecentStore(limit=config.recent_limit)
        number, folder = store.new_folder(spec.name)
        try:
            outcome = run_tool(
                spec,
                inp,
                workdir=folder,
                config=config,
                timeout_s=common["csk_timeout"],
                confirmed=confirmed,
            )
        except (ToolError, ConfirmationRequired, RunError) as e:
            store.discard(folder)
            _fail(str(e))
        result = outcome.result
        viewer = _add_viewer(result, folder)
        store.record(
            number,
            folder,
            spec,
            inp,
            result,
            elapsed_s=outcome.elapsed_s,
            peak_memory_mb=outcome.peak_memory_mb,
        )

        saved = None
        if common["csk_save"] or common["csk_save_to"]:
            saved = store.save(number, common["csk_save_to"] or config.save_dir)

        if common["csk_json"]:
            typer.echo(result.model_dump_json(indent=2))
            return
        render_result(result, console)
        if viewer and not common["csk_no_open"]:
            webbrowser.open(viewer.as_uri())
            console.print("[dim]Opened the 3D viewer in the browser (--no-open to skip).[/dim]")
        if saved:
            console.print(f"Saved to {saved}", highlight=False)
        else:
            console.print(
                f"[dim]Result #{number} · `csk save {number}` to keep it[/dim]", highlight=False
            )

    command.__signature__ = inspect.Signature(params)  # type: ignore[attr-defined]
    command.__name__ = spec.name
    command.__doc__ = spec.summary
    return command


def build_app(registry: Registry) -> typer.Typer:
    app = typer.Typer(
        help="ChemSidekick: small chemistry tools, fast.",
        no_args_is_help=True,
        rich_markup_mode=None,
    )

    @app.callback()
    def main(
        version: bool = typer.Option(
            False,
            "--version",
            callback=_show_version,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ) -> None:
        """ChemSidekick: small chemistry tools, fast."""

    @app.command("list")
    def list_tools() -> None:
        """List all tools by category."""
        render_tool_list(registry.by_category(), console)

    @app.command("search")
    def search_tools(query: str = typer.Argument(..., help="Word to search for.")) -> None:
        """Search tools by name, keyword, or description."""
        found = registry.search(query)
        if not found:
            _fail(f"No tool matches {query!r}. Run `csk list` to see all tools.")
        groups: dict[str, list[ToolSpec]] = {}
        for spec in found:
            groups.setdefault(spec.category, []).append(spec)
        render_tool_list(groups, console)

    @app.command("recent")
    def recent(
        count: int = typer.Option(10, "--count", "-n", min=1, help="How many to show."),
    ) -> None:
        """Show the most recent results."""
        config = _load_config()
        entries = RecentStore(limit=config.recent_limit).entries()[:count]
        if not entries:
            console.print("No recent results yet.")
            return
        render_recent(entries, console)

    @app.command("save")
    def save(
        number: int | None = typer.Argument(
            None, help="Result number from `csk recent` (default: the latest)."
        ),
        to: Path | None = typer.Option(None, "--to", help="Save into this folder."),
    ) -> None:
        """Save a recent result so it is not deleted."""
        config = _load_config()
        store = RecentStore(limit=config.recent_limit)
        try:
            dest = store.save(number, to or config.save_dir)
        except LookupError as e:
            _fail(str(e))
        console.print(f"Saved to {dest}", highlight=False)

    @app.command("ui")
    def ui(
        port: int = typer.Option(8501, "--port", help="Port for the local web server."),
    ) -> None:
        """Open the ChemSidekick web interface in your browser."""
        app_file = Path(__file__).resolve().parents[1] / "ui" / "app.py"
        cmd = [
            sys.executable, "-m", "streamlit", "run", str(app_file),
            "--server.port", str(port),
            "--server.address", "localhost",
            "--browser.gatherUsageStats", "false",
            "--server.showEmailPrompt", "false",  # no first-run email question
            "--client.toolbarMode", "minimal",  # hide Streamlit's developer menu ("Deploy")
        ]  # fmt: skip
        raise typer.Exit(subprocess.call(cmd))

    @app.command("doctor")
    def doctor_cmd() -> None:
        """Check which external programs are installed."""
        render_doctor(doctor(_load_config()), console)

    for spec in registry.all():
        app.command(name=spec.name, help=f"[{spec.id}] {spec.summary}")(_tool_command(spec))

    return app


app = build_app(discover())
