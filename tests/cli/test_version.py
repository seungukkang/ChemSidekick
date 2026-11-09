from typer.testing import CliRunner

from chemsidekick import __version__
from chemsidekick.cli.main import app

runner = CliRunner()


def test_version_flag_prints_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"chemsidekick {__version__}"
