"""Nothing the pipeline runs may live in a session scratchpad.

The training script, the epoch sweep and the whole dataset-prep chain all ran
out of one Claude session's directory under AppData\\Local\\Temp. Everything
worked until that directory was cleaned, at which point:

- a training run would finish and its eval step would fail with
  "EVAL FAILED - no judge set", stranding a five-hour run with no way to pick an
  epoch, and
- gather/caption/preview would stop existing entirely, with nothing in the repo
  to rebuild them from.

A queue job record is the worst place for such a path, because the record
outlives the session that wrote it. So the commands are built from ENGINE_ROOT.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sourcemode.config import ENGINE_ROOT

# Any per-session or per-user temp directory. Deliberately broad: the point is
# not to ban one old uuid, it is to ban the shape.
TEMP_SHAPE = re.compile(
    r"(AppData[\\/]Local[\\/]Temp|[\\/]tmp[\\/]|Temp[\\/]claude|scratchpad)",
    re.I)

SCANNED = ("*.ps1", "*.py")


def _files() -> list[Path]:
    out: list[Path] = []
    for sub in ("scripts", "sourcemode"):
        for pat in SCANNED:
            out += [p for p in (ENGINE_ROOT / sub).rglob(pat)
                    if "__pycache__" not in p.parts]
    return out


def test_no_pipeline_file_points_at_a_temp_directory():
    bad = []
    for p in _files():
        try:
            text = p.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue          # a comment explaining the old path is fine
            if TEMP_SHAPE.search(line):
                bad.append(f"{p.relative_to(ENGINE_ROOT).as_posix()}:{i}: {line.strip()[:90]}")
    assert not bad, (
        "these run out of a temp directory and will break when it is cleaned:\n"
        + "\n".join(bad))


def test_the_scripts_the_pipeline_invokes_are_in_the_repo():
    """Each of these was only ever in a session scratchpad."""
    for rel in ("scripts/train_character.ps1",
                "scripts/character_chain.ps1",
                "scripts/eval/dense_epoch_eval.py",
                "scripts/eval/asset_scenes.py",
                "scripts/eval/favorable_scenes.py",
                "scripts/prep/gather_character.py",
                "scripts/prep/gaze_mp.py",
                "scripts/prep/caption_from_vl.py",
                "scripts/prep/hair_confirm2.py",
                "scripts/prep/build_previews.py"):
        assert (ENGINE_ROOT / rel).is_file(), f"{rel} is missing from the repo"


@pytest.mark.parametrize("script", ["train_character.ps1", "character_chain.ps1"])
def test_every_path_a_driver_script_resolves_exists(script):
    """The `$X = "C:\\..."` assignments at the top of each driver must point at
    something real, or the failure is a silent zero-byte log hours later."""
    text = (ENGINE_ROOT / "scripts" / script).read_text(encoding="utf-8-sig")
    assigns = re.findall(r'^\$(\w+)\s*=\s*"(C:[^"]+)"\s*$', text, re.M)
    assert assigns, f"{script} declares no absolute paths - did its shape change?"
    missing = [(name, val) for name, val in assigns
               # $log and friends are composed from other vars, not literal roots
               if "$" not in val and not Path(val).exists()]
    assert not missing, f"{script} points at paths that do not exist: {missing}"


def test_the_queue_builds_both_commands_from_the_repo():
    """A queue entry outlives the session that wrote it, so it is the last place
    a temp path belongs. Both commands come from ENGINE_ROOT."""
    from sourcemode.monitor.queue_page import prep_command, training_command

    cfg: dict = {}
    for cmd in (training_command(cfg, "vivian_v2"), prep_command(cfg, "vivian")):
        joined = " ".join(cmd)
        assert not TEMP_SHAPE.search(joined), joined
        script = Path(cmd[cmd.index("-File") + 1])
        assert script.is_file(), script
        assert str(ENGINE_ROOT) in str(script)


# --- a job that is running but not progressing -------------------------------

def test_the_overrun_check_catches_the_job_that_only_logs_that_it_is_waiting():
    """THE CASE. tess's chain ran 4h 48m against a 23-minute estimate, logging
    "STALLED: 0 shots, unchanged for an hour" every hour. Its newest signal was
    never older than ~60 min, so the quiet-log test could never fire on it - a
    heartbeat that only says "still waiting" is not progress. Elapsed against
    the job's own measured estimate is what separates them."""
    from sourcemode.monitor.queue_page import _state_of

    job = dict(status="running", hold=False, exit_code=None, is_next=False,
               blocked_reason=None, kind="prep")
    r = _state_of(job, paused=False, runner_alive=True, log_age_s=None,
                  quiet_s=59 * 60,              # under QUIET_S: the heartbeat
                  elapsed_s=4.8 * 3600, expected_s=23 * 60)
    assert r["status"] == "you"
    assert "against an estimate" in r["why"]


def test_a_slow_but_real_run_is_not_flagged():
    """The slowest measured chain is 43 min against a 23 min median - 1.9x.
    The line sits at 3x so real variation never trips it."""
    from sourcemode.monitor.queue_page import _state_of

    job = dict(status="running", hold=False, exit_code=None, is_next=False,
               blocked_reason=None, kind="prep")
    r = _state_of(job, paused=False, runner_alive=True, log_age_s=None,
                  quiet_s=30, elapsed_s=43 * 60, expected_s=23 * 60)
    assert r["status"] == "live"


def test_nothing_is_flagged_in_its_first_hour():
    """A 9-render A/B estimated at 11 minutes is 3x over at 33 minutes, which is
    far too twitchy. The floor stops short jobs crying wolf."""
    from sourcemode.monitor.queue_page import _state_of

    job = dict(status="running", hold=False, exit_code=None, is_next=False,
               blocked_reason=None, kind="eval")
    r = _state_of(job, paused=False, runner_alive=True, log_age_s=None,
                  quiet_s=30, elapsed_s=35 * 60, expected_s=11 * 60)
    assert r["status"] == "live"


def test_a_job_with_no_estimate_is_never_flagged_by_overrun():
    """Unknown length means unknown, not suspicious - the same rule the plan
    bar follows when it refuses to call an unknown job zero-length."""
    from sourcemode.monitor.queue_page import _state_of

    job = dict(status="running", hold=False, exit_code=None, is_next=False,
               blocked_reason=None, kind="other")
    r = _state_of(job, paused=False, runner_alive=True, log_age_s=None,
                  quiet_s=30, elapsed_s=20 * 3600, expected_s=None)
    assert r["status"] == "live"
