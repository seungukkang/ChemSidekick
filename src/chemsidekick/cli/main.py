"""Entry point for the `csk` command.

Built-in commands (list, search, run, gif, recent, save, doctor, ui) are defined here. Every tool
in the registry becomes a `csk <tool>` command automatically: its options are
generated from the tool's Pydantic input model.

With `--json`, commands print one JSON object from the contract (core/contract.py)
on stdout, for errors too, and exit with the contract's exit code.
`csk run <tool> --json` takes the tool's input as a JSON object on standard input;
interfaces such as the Raycast extension use it instead of building options.
"""

import inspect
import json
import subprocess
import sys
import types
import typing
import webbrowser
from collections.abc import Callable
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
from chemsidekick.core.contract import (
    ErrorDetail,
    ErrorInfo,
    ErrorResponse,
    GifRequest,
    GifResponse,
    RunInfo,
    RunResponse,
    SaveResponse,
    error_info,
    exit_code,
    tool_list,
)
from chemsidekick.core.external import doctor
from chemsidekick.core.registry import Registry, ToolSpec, discover
from chemsidekick.core.results import RecentStore
from chemsidekick.core.runner import RunError, run_tool
from chemsidekick.core.schemas import Artifact, ToolError, ToolResult
from chemsidekick.core.spin import FRAMES, spin_card
from chemsidekick.core.theme import THEME_COLOR
from chemsidekick.core.viewer import viewer_html

console = Console()
err_console = Console(stderr=True)


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"chemsidekick {__version__}")
        raise typer.Exit()


# ---------------------------------------------------------------------------
# Errors: one place decides between the JSON contract and red text
# ---------------------------------------------------------------------------


class CliError(Exception):
    """An error found by the CLI itself, with its contract error type."""

    def __init__(
        self, message: str, type: str = "input", details: list[ErrorDetail] | None = None
    ) -> None:
        super().__init__(message)
        self.type = type
        self.details = details or []


def _fail(message: str, type: str = "input") -> typing.NoReturn:
    raise CliError(message, type)


def _guarded(json_mode: bool, body: Callable[[], None]) -> None:
    """Run a command body; report any error in the right form and exit with its code."""
    try:
        body()
        return
    except typer.Exit:
        raise
    except CliError as e:
        info = ErrorInfo(type=e.type, message=str(e), details=e.details)  # type: ignore[arg-type]
    except (ValidationError, ToolError, RunError, ConfigError) as e:
        info = error_info(e)
    except Exception as e:
        if not json_mode:
            raise  # a bug: show the traceback in the terminal
        info = error_info(e)
    if json_mode:
        typer.echo(ErrorResponse(error=info).model_dump_json(indent=2))
    else:
        err_console.print(f"[red]Error:[/red] {info.message}", highlight=False, markup=True)
    raise typer.Exit(code=exit_code(info.type))


def _load_config():
    return load_config()  # ConfigError is reported by _guarded


# ---------------------------------------------------------------------------
# Input model -> command-line options
# ---------------------------------------------------------------------------


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


# Options shared by every tool command (and `csk run`). Their names start with
# "csk_" so they can never clash with a field of a tool's input model.
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
    _common(
        "csk_no_record",
        bool,
        typer.Option(
            False,
            "--no-record",
            help="Do not keep this run in the recent results (files go to a temporary folder).",
        ),
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


# ---------------------------------------------------------------------------
# Running a tool (shared by `csk <tool>` and `csk run <tool>`)
# ---------------------------------------------------------------------------


def _execute(spec: ToolSpec, inp: BaseModel, common: dict[str, Any]) -> None:
    json_mode = common["csk_json"]
    record = not common["csk_no_record"]
    if not record and (common["csk_save"] or common["csk_save_to"]):
        _fail("--save cannot be combined with --no-record.")
    config = _load_config()

    confirmed = common["csk_yes"]
    if spec.resources == "heavy" and not confirmed:
        if json_mode or not sys.stdin.isatty():
            _fail(f"{spec.title} is a heavy tool. Add --yes to run it.", "confirm")
        confirmed = typer.confirm(f"{spec.title} is a heavy tool. Run it?")
        if not confirmed:
            raise typer.Exit(code=exit_code("confirm"))

    store = RecentStore(limit=config.recent_limit)
    if record:
        number, folder = store.new_folder(spec.name)
    else:
        number, folder = None, store.scratch_folder(spec.name)
    try:
        outcome = run_tool(
            spec,
            inp,
            workdir=folder,
            config=config,
            timeout_s=common["csk_timeout"],
            confirmed=confirmed,
        )
    except BaseException:
        store.discard(folder)
        raise
    result = outcome.result
    viewer = _add_viewer(result, folder)
    if number is not None:
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
    if number is not None and (common["csk_save"] or common["csk_save_to"]):
        saved = store.save(number, common["csk_save_to"] or config.save_dir)

    if json_mode:
        response = RunResponse(
            result=result,
            run=RunInfo(
                tool=spec.name,
                tool_id=spec.id,
                number=number,
                folder=str(folder),
                recorded=number is not None,
                elapsed_s=round(outcome.elapsed_s, 3),
                peak_memory_mb=outcome.peak_memory_mb,
            ),
        )
        typer.echo(response.model_dump_json(indent=2))
        return
    render_result(result, console)
    if viewer and not common["csk_no_open"]:
        webbrowser.open(viewer.as_uri())
        console.print("[dim]Opened the 3D viewer in the browser (--no-open to skip).[/dim]")
    if saved:
        console.print(f"Saved to {saved}", highlight=False)
    elif number is None:
        console.print("[dim]Not kept in the recent results (--no-record).[/dim]", highlight=False)
    else:
        console.print(
            f"[dim]Result #{number} · `csk save {number}` to keep it[/dim]", highlight=False
        )


def _tool_command(spec: ToolSpec):
    """Build a Typer command function for one tool."""
    model: type[BaseModel] = spec.input_model
    params = [_parameter(n, f) for n, f in model.model_fields.items()] + _COMMON_PARAMS

    def command(**kwargs: Any) -> None:
        common = {k: kwargs.pop(k) for k in list(kwargs) if k.startswith("csk_")}

        def body() -> None:
            for name in _file_fields(model):
                kwargs[name] = _read_text_input(kwargs[name])
            _execute(spec, model(**kwargs), common)

        _guarded(common["csk_json"], body)

    command.__signature__ = inspect.Signature(params)  # type: ignore[attr-defined]
    command.__name__ = spec.name
    command.__doc__ = spec.summary
    return command


def _find_tool(registry: Registry, name_or_id: str) -> ToolSpec:
    if name_or_id in registry:
        return registry.get(name_or_id)
    try:
        return registry.by_id(name_or_id)
    except KeyError:
        _fail(f"No tool named {name_or_id!r}. Run `csk list` to see all tools.")


def _read_json_input() -> dict[str, Any]:
    """The tool input for `csk run`: a JSON object on standard input ({} if none)."""
    text = "" if sys.stdin.isatty() else sys.stdin.read()
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        _fail(f"The input is not valid JSON: {e}")
    if not isinstance(data, dict):
        _fail('The input must be a JSON object, e.g. {"smiles": "CCO"}.')
    return data


def _run_command(registry: Registry):
    """`csk run <tool>`: input as JSON on standard input, for programs (e.g. Raycast)."""
    tool_param = inspect.Parameter(
        "tool",
        inspect.Parameter.KEYWORD_ONLY,
        default=typer.Argument(..., help="Tool name or ID, e.g. stereo or STR-02."),
        annotation=str,
    )

    def run(**kwargs: Any) -> None:
        common = {k: kwargs.pop(k) for k in list(kwargs) if k.startswith("csk_")}

        def body() -> None:
            spec = _find_tool(registry, kwargs["tool"])
            data = _read_json_input()
            # Programs build this input, so a misspelled field is a bug to report,
            # not something to ignore (tool input models accept extra fields).
            unknown = sorted(set(data) - set(spec.input_model.model_fields))
            if unknown:
                known = ", ".join(spec.input_model.model_fields) or "none"
                raise CliError(
                    f"Unknown input field(s) for {spec.name}: {', '.join(unknown)} "
                    f"(known: {known}).",
                    details=[ErrorDetail(field=f, message="unknown field") for f in unknown],
                )
            _execute(spec, spec.input_model.model_validate(data), common)

        _guarded(common["csk_json"], body)

    run.__signature__ = inspect.Signature([tool_param, *_COMMON_PARAMS])  # type: ignore[attr-defined]
    run.__doc__ = (
        "Run a tool with its input given as a JSON object on standard input, "
        'e.g. echo \'{"smiles": "CC(Br)C(Br)C"}\' | csk run stereo --json'
    )
    return run


# ---------------------------------------------------------------------------
# The app
# ---------------------------------------------------------------------------

_JSON_OPTION = typer.Option(False, "--json", help="Print as JSON.")


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

    def _print_tools(specs: list[ToolSpec], as_json: bool) -> None:
        if as_json:
            typer.echo(tool_list(specs, _load_config()).model_dump_json(indent=2))
            return
        groups: dict[str, list[ToolSpec]] = {}
        for spec in specs:
            groups.setdefault(spec.category, []).append(spec)
        render_tool_list(groups, console)

    @app.command("list")
    def list_tools(as_json: bool = _JSON_OPTION) -> None:
        """List all tools by category."""
        _guarded(as_json, lambda: _print_tools(registry.all(), as_json))

    @app.command("search")
    def search_tools(
        query: str = typer.Argument(..., help="Word to search for."),
        as_json: bool = _JSON_OPTION,
    ) -> None:
        """Search tools by name, keyword, or description."""

        def body() -> None:
            found = registry.search(query)
            if not found and not as_json:
                _fail(f"No tool matches {query!r}. Run `csk list` to see all tools.")
            _print_tools(found, as_json)

        _guarded(as_json, body)

    app.command("run")(_run_command(registry))

    @app.command("gif")
    def gif(as_json: bool = _JSON_OPTION) -> None:
        """Rotating 3D view of one structure as an animated GIF.

        Input on standard input, as JSON: {"frame": {"symbols": [...], "coords": [...]},
        "title": "...", "note": "..."}; a frame of any tool's 3D result (e.g. stereo, xyz).
        """

        def body() -> None:
            request = GifRequest.model_validate(_read_json_input())
            config = _load_config()
            folder = RecentStore(limit=config.recent_limit).scratch_folder("gif")
            path = spin_card(request.frame, folder / "spin.gif", request.title, request.note)
            if as_json:
                typer.echo(GifResponse(path=str(path), frames=FRAMES).model_dump_json(indent=2))
            else:
                console.print(str(path), highlight=False)

        _guarded(as_json, body)

    @app.command("recent")
    def recent(
        count: int = typer.Option(10, "--count", "-n", min=1, help="How many to show."),
    ) -> None:
        """Show the most recent results."""

        def body() -> None:
            config = _load_config()
            entries = RecentStore(limit=config.recent_limit).entries()[:count]
            if not entries:
                console.print("No recent results yet.")
                return
            render_recent(entries, console)

        _guarded(False, body)

    @app.command("save")
    def save(
        number: int | None = typer.Argument(
            None, help="Result number from `csk recent` (default: the latest)."
        ),
        to: Path | None = typer.Option(None, "--to", help="Save into this folder."),
        as_json: bool = _JSON_OPTION,
    ) -> None:
        """Save a recent result so it is not deleted."""

        def body() -> None:
            config = _load_config()
            store = RecentStore(limit=config.recent_limit)
            try:
                entry = store.get(number)
                dest = store.save(entry.number, to or config.save_dir)
            except LookupError as e:
                _fail(str(e))
            if as_json:
                response = SaveResponse(number=entry.number, saved_to=str(dest))
                typer.echo(response.model_dump_json(indent=2))
            else:
                console.print(f"Saved to {dest}", highlight=False)

        _guarded(as_json, body)

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
            "--theme.primaryColor", THEME_COLOR,  # core/theme.py
        ]  # fmt: skip
        raise typer.Exit(subprocess.call(cmd))

    @app.command("doctor")
    def doctor_cmd() -> None:
        """Check which external programs are installed."""
        _guarded(False, lambda: render_doctor(doctor(_load_config()), console))

    for spec in registry.all():
        app.command(name=spec.name, help=f"[{spec.id}] {spec.summary}")(_tool_command(spec))

    return app


app = build_app(discover())
