from typer.testing import CliRunner

from commander_ai.cli.main import app


def test_doctor_reports_foundation_status() -> None:
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "status=foundation-ok" in result.stdout
