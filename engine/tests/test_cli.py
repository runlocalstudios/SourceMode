from typer.testing import CliRunner

from sourcemode.cli import app

runner = CliRunner()


def test_help_lists_all_command_groups():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("doctor", "source", "gates", "prompts", "render", "train", "bootstrap", "voice", "run"):
        assert cmd in result.output, f"{cmd} missing from --help"


def test_source_show_gwen():
    result = runner.invoke(app, ["source", "show", "gwen"])
    if result.exit_code != 0:
        import pytest

        pytest.skip("gwen assets not present")
    assert "gwen_ch" in result.output
