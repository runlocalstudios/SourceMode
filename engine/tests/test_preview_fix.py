"""The fix list, the clause rule, the approval record, and two server bugs.

The dataset page reported caption trouble in aggregate (gate pass/FAIL) and
per-image (chips) with nothing in between, so a 104-image set got scrolled. These
pin the "here are the 4 rows you actually have to fix" path, and the two
server-side defects found while building it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from sourcemode.train.preview import (
    approval_record,
    build_preview,
    caption_report,
    edit_report,
    exclude_image,
    fix_rows,
    needs_look,
    record_approval,
    set_caption,
    set_captions,
    with_clause,
)


# --- with_clause: addGaze()'s rule, moved server-side -----------------------

def test_the_clause_lands_before_the_hair_clause():
    cap = "tess, waist-up, facing the camera, her hair loose, in a kitchen"
    assert with_clause(cap, "looking off camera") == (
        "tess, waist-up, facing the camera, looking off camera, "
        "her hair loose, in a kitchen")


def test_the_clause_falls_back_to_position_two():
    cap = "tess, waist-up, in a kitchen"
    assert with_clause(cap, "looking off camera") == (
        "tess, waist-up, looking off camera, in a kitchen")


def test_the_clause_is_idempotent():
    cap = "tess, waist-up, looking off camera, her hair loose"
    assert with_clause(cap, "looking off camera") == cap


def test_the_clause_handles_a_short_caption():
    assert with_clause("tess", "looking off camera") == "tess, looking off camera"
    assert with_clause("", "looking off camera") == "looking off camera"


def test_the_inserted_clause_is_classified_as_gaze():
    """Which is what makes a quick fix self-report in edit_report()."""
    from sourcemode.train.preview import classify_clause

    assert classify_clause("looking off camera") == "gaze"


# --- the fix list ------------------------------------------------------------

def _ds(tmp_path: Path, rows: list[dict]) -> tuple[Path, Path]:
    """rows: [{name, caption, uncertain?}] -> (preview root, dataset dir)."""
    root, d = tmp_path / "prev", tmp_path / "ds" / "image_face"
    d.mkdir(parents=True)
    for r in rows:
        p = d / r["name"]
        Image.new("RGB", (8, 8)).save(p)
        p.with_suffix(".txt").write_text(r.get("caption", ""), encoding="utf-8")
    doc = build_preview(root, tmp_path / "ds", dataset_id="t_v2", measure=False)
    # stamp the close calls the detectors would have produced
    by = {r["name"]: r for r in rows}
    for im in doc["images"]:
        im["uncertain"] = list(by[im["name"]].get("uncertain") or [])
    (root / "previews" / "t_v2.json").write_text(json.dumps(doc), encoding="utf-8")
    return root, tmp_path / "ds"


def test_fix_rows_is_exactly_needs_look(tmp_path):
    root, _ = _ds(tmp_path, [
        {"name": "a.png", "caption": "x, waist-up, her hair loose, in a kitchen, lit"},
        {"name": "b.png", "caption": ""},                                # uncaptioned
        {"name": "c.png", "caption": "x, waist-up", "uncertain": ["gaze?"]},
        {"name": "d.png", "caption": "x, waist-up", "uncertain": ["not lora-gen"]},
    ])
    f = fix_rows(root, "t_v2")
    assert [r["name"] for r in f["rows"]] == ["b.png", "c.png", "d.png"]
    # worst first: NO CAPTION leads
    assert f["rows"][0]["reasons"] == ["NO CAPTION"]
    # and it is not a new judgement - it is needs_look(), row for row
    from sourcemode.train.preview import load_preview

    doc = load_preview(root, "t_v2")
    assert {r["name"] for r in f["rows"]} == {
        im["name"] for im in doc["images"] if needs_look(im)}


def test_only_a_gaze_row_gets_a_suggestion(tmp_path):
    root, _ = _ds(tmp_path, [
        {"name": "c.png", "caption": "x, waist-up, her hair loose",
         "uncertain": ["gaze?"]},
        {"name": "d.png", "caption": "x, waist-up", "uncertain": ["not lora-gen"]},
    ])
    rows = {r["name"]: r for r in fix_rows(root, "t_v2")["rows"]}
    assert rows["c.png"]["suggestion"]["kind"] == "off_cam"
    assert "looking off camera" in rows["c.png"]["suggestion"]["caption"]
    assert rows["d.png"]["suggestion"] is None   # nothing automatic fits


def test_a_gaze_row_that_already_says_it_gets_no_suggestion(tmp_path):
    root, _ = _ds(tmp_path, [
        {"name": "c.png", "caption": "x, looking off camera, her hair loose",
         "uncertain": ["gaze?"]},
    ])
    assert fix_rows(root, "t_v2")["rows"][0]["suggestion"] is None


def test_by_reason_counts_and_offers_a_bulk_where_one_exists(tmp_path):
    root, _ = _ds(tmp_path, [
        {"name": f"{i}.png", "caption": "x, waist-up", "uncertain": ["gaze?"]}
        for i in range(4)
    ] + [{"name": "z.png", "caption": "x", "uncertain": ["not lora-gen"]}])
    by = {b["reason"]: b for b in fix_rows(root, "t_v2")["by_reason"]}
    assert by["gaze?"]["n"] == 4
    assert by["gaze?"]["bulk"] == "off_cam"
    assert by["not lora-gen"]["bulk"] is None


def test_an_empty_set_has_an_empty_fix_list(tmp_path):
    root, _ = _ds(tmp_path, [
        {"name": "a.png", "caption": "x, waist-up, her hair loose, in a kitchen, lit"}])
    assert fix_rows(root, "t_v2")["rows"] == []
    assert fix_rows(root, "nope")["rows"] == []


def test_the_fix_list_never_blocks_approval(tmp_path):
    """A flag is a prompt to look, never a verdict."""
    root, _ = _ds(tmp_path, [{"name": "b.png", "caption": ""}])
    assert fix_rows(root, "t_v2")["rows"]
    st = record_approval(root, "t_v2", True)
    assert st["approved"] is True        # approving over a flag is allowed


# --- set_captions ------------------------------------------------------------

def test_each_caption_in_a_bulk_write_is_logged_separately(tmp_path):
    """edit_report()'s "three of the same clause is systematic" threshold must
    count what actually happened, not count one request as one edit."""
    root, _ = _ds(tmp_path, [
        {"name": f"{i}.png", "caption": "x, waist-up, her hair loose"}
        for i in range(4)])
    out = set_captions(root, "t_v2", [
        {"name": f"{i}.png",
         "caption": with_clause("x, waist-up, her hair loose", "looking off camera")}
        for i in range(4)])
    assert out["n_written"] == 4
    assert out["failed"] == []
    rep = edit_report(root, "t_v2")
    gaze = [c for c in rep["by_clause"] if c["clause"] == "gaze"]
    assert gaze and gaze[0]["n"] == 4
    assert any(c["clause"] == "gaze" for c in rep["needs_automation"])


def test_an_unknown_name_in_a_bulk_write_is_reported_not_fatal(tmp_path):
    root, _ = _ds(tmp_path, [{"name": "a.png", "caption": "x, waist-up"}])
    out = set_captions(root, "t_v2", [{"name": "a.png", "caption": "x, waist-up, y"},
                                      {"name": "ghost.png", "caption": "z"}])
    assert out["n_written"] == 1
    assert out["failed"] == ["ghost.png"]


def test_a_caption_write_returns_the_close_calls_the_chips_need(tmp_path):
    """B1: the page used to re-render chips from `uncaptioned` + `missing` only,
    silently dropping the `gaze?` chip the server had just returned."""
    root, _ = _ds(tmp_path, [
        {"name": "c.png", "caption": "x, waist-up", "uncertain": ["gaze?"]}])
    r = set_caption(root, "t_v2", "c.png", "x, waist-up, her hair loose")
    assert "uncertain" in r
    assert r["uncertain"] == ["gaze?"]


# --- B6: an empty caption report is not a FAIL about captions ---------------

def test_caption_report_of_an_empty_set_carries_passed(tmp_path):
    """The early return omitted `passed`, and the page renders a missing key as
    FAIL - so a set with no images painted red for an unrelated reason."""
    rep = caption_report([])
    assert rep["n"] == 0
    assert "passed" in rep
    assert rep["passed"] is False
    assert rep["failed"] == ["captions"]
    assert rep["median_words"] == 0


# --- B7: exclusions must not bury the clause signal ------------------------

def test_exclusions_are_not_counted_as_clauses(tmp_path):
    """236 of 342 rows in the real edit log are exclusions. Bucketing them under
    their `kind` invented pseudo-clauses that outranked every real clause in a
    count-sorted report, burying the signal the report exists to surface."""
    root, _ = _ds(tmp_path, [
        {"name": f"{i}.png", "caption": "x, waist-up, her hair loose"}
        for i in range(5)])
    # three real caption corrections of one clause - the systematic signal
    for i in range(3):
        set_caption(root, "t_v2", f"{i}.png",
                    "x, waist-up, her hair in a ponytail")
    # and a pile of exclusions, which are not caption corrections at all
    for i in range(3, 5):
        exclude_image(root, "t_v2", f"{i}.png", True)

    rep = edit_report(root, "t_v2")
    clauses = {c["clause"] for c in rep["by_clause"]}
    assert "excluded" not in clauses
    assert "restored" not in clauses
    hair = [c for c in rep["by_clause"] if c["clause"] == "hair"]
    assert hair and hair[0]["n"] == 3
    assert [c["clause"] for c in rep["needs_automation"]] == ["hair"]


# --- the approval record ----------------------------------------------------

def test_the_approval_record_lists_only_what_changed_after_the_approval(tmp_path):
    import time

    root, _ = _ds(tmp_path, [
        {"name": f"{i}.png", "caption": "x, waist-up, her hair loose"}
        for i in range(3)])
    set_caption(root, "t_v2", "0.png", "x, waist-up, her hair in a bun")  # before
    # Timestamps are second-resolution on both sides, so the test steps past the
    # second boundary rather than asserting an order the data cannot carry.
    time.sleep(1.05)
    record_approval(root, "t_v2", True)
    rec = approval_record(root, "t_v2")
    assert rec["approved"] is True
    assert rec["n_since"] == 0          # the earlier edit is not why it lapsed

    time.sleep(1.05)
    set_caption(root, "t_v2", "1.png", "x, waist-up, her hair in a braid")  # after
    rec = approval_record(root, "t_v2")
    assert rec["approved"] is False
    assert rec["stale"] is True
    assert rec["n_since"] == 1
    assert rec["since"][0]["image"] == "1.png"
    assert "hair" in rec["since"][0]["clauses"]
    assert rec["approved_fingerprint"] != rec["fingerprint"]


def test_an_unapproved_set_has_no_since_list(tmp_path):
    root, _ = _ds(tmp_path, [{"name": "a.png", "caption": "x, waist-up"}])
    rec = approval_record(root, "t_v2")
    assert rec["approved"] is False
    assert rec["since"] == []
    assert rec["n_since"] == 0


@pytest.mark.parametrize("missing", ["ghost_v2", "", "../x"])
def test_the_approval_record_of_a_set_that_is_not_there(tmp_path, missing):
    rec = approval_record(tmp_path / "prev", missing)
    assert rec["approved"] is False


def test_a_same_second_edit_explains_a_lapsed_approval(tmp_path):
    """Both sides are stamped to the second, so an edit in the approval's own
    second cannot be ordered against it. When the fingerprint says the set
    changed, reporting "lapsed, 0 changes" explains nothing - so a same-second
    edit is included."""
    root, _ = _ds(tmp_path, [
        {"name": f"{i}.png", "caption": "x, waist-up, her hair loose"}
        for i in range(2)])
    record_approval(root, "t_v2", True)
    set_caption(root, "t_v2", "0.png", "x, waist-up, her hair in a bun")
    rec = approval_record(root, "t_v2")
    assert rec["stale"] is True
    assert rec["n_since"] >= 1
    assert rec["since"][-1]["image"] == "0.png"
