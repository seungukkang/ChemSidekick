"""Entry point for the `csk` command."""

import typer

from chemsidekick import __version__

app = typer.Typer(
    help="ChemSidekick: small chemistry tools, fast.",
    no_args_is_help=True,
)


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"chemsidekick {__version__}")
        raise typer.Exit()


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
