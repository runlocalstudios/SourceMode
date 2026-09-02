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


def test_pose_transfer_default_pattern_matches_png_assets(tmp_path):
    """The default used to be *_standing.webp while the assets are .png.

    A whole 92-image batch matched nothing, exited 2 per folder, and from the
    log looked like it had run — the failure was invisible because the error
    went to a stream that was being filtered. The default is now
    extension-agnostic.
    """
    (tmp_path / "casual_01_standing.png").write_bytes(b"x")
    result = runner.invoke(app, ["pose", "transfer", "kneeling_wide",
                                 "--assets", str(tmp_path), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "casual_01_standing.png" in result.output


def test_pose_transfer_reports_what_the_folder_actually_holds(tmp_path):
    """An empty match must say why, not just that it found nothing."""
    (tmp_path / "notes.txt").write_text("not an asset")
    result = runner.invoke(app, ["pose", "transfer", "kneeling_wide",
                                 "--assets", str(tmp_path), "--dry-run"])
    assert result.exit_code == 2
    assert ".txt" in result.output


def test_pose_transfer_ignores_non_image_files(tmp_path):
    """*_standing.* must not sweep up sidecars sitting next to the assets."""
    (tmp_path / "casual_01_standing.png").write_bytes(b"x")
    (tmp_path / "casual_01_standing.json").write_text("{}")
    result = runner.invoke(app, ["pose", "transfer", "kneeling_wide",
                                 "--assets", str(tmp_path), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "1 image(s)" in result.output
    assert ".json" not in result.output
