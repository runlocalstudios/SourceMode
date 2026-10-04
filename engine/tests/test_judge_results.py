"""A judged set keeps its result, and the undo path finally has a caller.

Two losses this closes:

- `drop_stale_verdicts()` silently discarded a whole tally whenever a set was
  re-rendered. It is the one place in the product where a judged result can
  vanish, and it already knew it was about to.
- `record_verdict(..., None)` has documented "verdict None clears the item
  (undo)" since it was written and nothing has ever called it: the page's back
  button only moved the index, leaving the old verdict standing.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from sourcemode.assets.judge import (
    append_result,
    history,
    load_verdicts,
    make_set,
    record_verdict,
    results_path,
    summary,
)


def _set(root: Path, tmp: Path, set_id: str = "s1", n: int = 4,
         *, write_images: bool = True) -> list[str]:
    """Build (or rebuild) a set over `n` images.

    `write_images=False` rebuilds the MANIFEST over whatever is on disk, which is
    what a re-render looks like: same ids, different pixels. Writing the images
    again here would overwrite the re-rendered ones and the content hashes would
    match, which is the trap this signature exists to avoid.
    """
    tmp.mkdir(parents=True, exist_ok=True)
    items = []
    for i in range(n):
        p = tmp / f"{i}.png"
        if write_images:
            Image.new("RGB", (8, 8), (i, i, i)).save(p)
        items.append({"id": str(i), "path": p, "arm": "A" if i % 2 else "B",
                      "group": str(i // 2)})
    make_set(root, set_id, "a set", items)
    return [it["id"] for it in items]


def test_a_rerender_appends_the_tally_before_clearing_it(tmp_path):
    root, img = tmp_path / "judge", tmp_path / "img"
    _set(root, img)
    for i in ("0", "1", "2", "3"):
        record_verdict(root, "s1", i, "keep")
    assert summary(root, "s1")["judged"] == 4

    # re-render two of the images with different pixels, then rebuild the set
    for i in ("0", "1"):
        Image.new("RGB", (8, 8), (200, 10, 10)).save(img / f"{i}.png")
    _set(root, img, write_images=False)

    v = load_verdicts(root, "s1")
    assert set(v) == {"2", "3"}            # the stale two were dropped, as before
    runs = history(root, "s1")["runs"]
    assert len(runs) == 1                  # and the tally they were part of is kept
    assert runs[0]["judged"] == 4
    assert "re-rendered" in runs[0]["reason"]
    assert {a["arm"] for a in runs[0]["arms"]} == {"A", "B"}


def test_append_result_is_a_noop_with_nothing_judged(tmp_path):
    root = tmp_path / "judge"
    _set(root, tmp_path / "img")
    assert append_result(root, "s1", reason="x") is None
    assert not results_path(root, "s1").is_file()
    assert history(root, "s1")["runs"] == []


def test_append_result_is_a_noop_for_a_set_that_does_not_exist(tmp_path):
    assert append_result(tmp_path / "judge", "nope", reason="x") is None


def test_history_returns_newest_first(tmp_path):
    root = tmp_path / "judge"
    _set(root, tmp_path / "img")
    record_verdict(root, "s1", "0", "keep")
    append_result(root, "s1", reason="first")
    record_verdict(root, "s1", "1", "reject")
    append_result(root, "s1", reason="second")
    runs = history(root, "s1")["runs"]
    assert [r["reason"] for r in runs] == ["second", "first"]
    assert runs[0]["judged"] == 2


def test_one_corrupt_line_does_not_lose_the_history(tmp_path):
    root = tmp_path / "judge"
    _set(root, tmp_path / "img")
    record_verdict(root, "s1", "0", "keep")
    append_result(root, "s1", reason="good")
    with results_path(root, "s1").open("a", encoding="utf-8") as fh:
        fh.write("{half written" + chr(10))
    assert [r["reason"] for r in history(root, "s1")["runs"]] == ["good"]


def test_record_verdict_none_clears_and_persists(tmp_path):
    """The undo path. Documented since it was written, never once called."""
    root = tmp_path / "judge"
    _set(root, tmp_path / "img")
    record_verdict(root, "s1", "0", "keep")
    assert load_verdicts(root, "s1") == {"0": "keep"}
    record_verdict(root, "s1", "0", None)
    assert load_verdicts(root, "s1") == {}          # gone from disk, not just memory
    assert summary(root, "s1")["judged"] == 0


def test_clearing_an_unjudged_item_is_harmless(tmp_path):
    root = tmp_path / "judge"
    _set(root, tmp_path / "img")
    record_verdict(root, "s1", "2", None)
    assert load_verdicts(root, "s1") == {}
