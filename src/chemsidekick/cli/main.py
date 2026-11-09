"""Entry point for the `csk` command.

Built-in commands (list, search) are defined here. Every tool in the
registry becomes a `csk <tool>` command automatically: its options are
generated from the tool's Pydantic input model.
"""

import inspect
import types
import typing
from typing import Any, Literal, Union

import typer
from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo
from rich.console import Console

from chemsidekick import __version__
from chemsidekick.cli.render import render_result, render_tool_list
from chemsidekick.core.registry import Registry, ToolSpec, discover
from chemsidekick.core.schemas import ToolError

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
    if extra.get("positional"):
        info = typer.Argument(default, show_default=False, **common)
    else:
        flags = [f"--{name.replace('_', '-')}"]
        if extra.get("short"):
            flags.append(str(extra["short"]))
        info = typer.Option(default, *flags, **common)
    return inspect.Parameter(
        name, inspect.Parameter.KEYWORD_ONLY, default=info, annotation=cli_type
    )


_JSON_PARAM = inspect.Parameter(
    "json_output",
    inspect.Parameter.KEYWORD_ONLY,
    default=typer.Option(False, "--json", help="Print the full result as JSON."),
    annotation=bool,
)


def _fail(message: str) -> typing.NoReturn:
    err_console.print(f"[red]Error:[/red] {message}", highlight=False, markup=True)
    raise typer.Exit(code=1)


def _input_error_message(e: ValidationError) -> str:
    parts = []
    for err in e.errors():
        where = ".".join(str(p) for p in err["loc"]) or "input"
        parts.append(f"{where}: {err['msg']}")
    return "; ".join(parts)


def _tool_command(spec: ToolSpec):
    """Build a Typer command function for one tool."""
    model: type[BaseModel] = spec.input_model
    params = [_parameter(n, f) for n, f in model.model_fields.items()] + [_JSON_PARAM]

    def command(**kwargs: Any) -> None:
        as_json = kwargs.pop("json_output")
        try:
            inp = model(**kwargs)
            result = spec.run(inp)
        except ValidationError as e:
            _fail(_input_error_message(e))
        except ToolError as e:
            _fail(str(e))
        if as_json:
            typer.echo(result.model_dump_json(indent=2))
        else:
            render_result(result, console)

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

    for spec in registry.all():
        app.command(name=spec.name, help=spec.summary)(_tool_command(spec))

    return app


app = build_app(discover())
