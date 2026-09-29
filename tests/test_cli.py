from typer.testing import CliRunner

from chordotomy import __version__
from chordotomy.cli import app


def test_version() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"chordotomy {__version__}"
