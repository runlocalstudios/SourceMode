"""The sweep ends in a recorded decision.

The epoch sweep's arms ARE the epochs and `summary()` already returns the keep
rate per arm, so the comparison was always computed - and then thrown away. The
tests here pin the three things that made it unsafe to rely on:

- the arm grammar, which has three real hazards on disk (a bare `epoch 12`, an
  unpadded `epoch 5`, and a `rank32 epoch 10 (current best)` that must NOT parse)
- the ranking, which is on a Wilson lower bound and not on the raw rate
- the checkpoint resolver, where the FINAL epoch has no numeric suffix
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sourcemode.assets.judge import (
    TIE_LOW,
    epoch_arm,
    epoch_board,
    epoch_sweep_name,
    make_set,
    record_verdict,
    sweep_set_for,
    sweep_sets_for,
    wilson_low,
)
from sourcemode.train.epochs import (
    checkpoint_dirs,
    checkpoint_for,
    list_choices,
    load_choice,
    record_choice,
)


# --- the arm grammar ---------------------------------------------------------

@pytest.mark.parametrize(("arm", "want"), [
    ("ash_v2 epoch 16", ("ash_v2", 16)),
    ("bianca_lr2b epoch 25", ("bianca_lr2b", 25)),
    # epochs_priyanka.json: the prefix is EMPTY and "" is not None, so every
    # caller must test `is not None` rather than truthiness
    ("epoch 12", ("", 12)),
    # t2i_epochs_sunny.json: unpadded
    ("T2I LoRA epoch 5", ("T2I LoRA", 5)),
    # coarse_sunny_r32.json: zero-padded to two
    ("sunny_r32 epoch 04", ("sunny_r32", 4)),
])
def test_epoch_arm_parses_every_shape_on_disk(arm, want):
    assert epoch_arm(arm) == want


@pytest.mark.parametrize("arm", [
    # gabi_r64_stage2.json - trailing text, so the set falls back to the generic
    # arm table rather than being guessed at
    "rank32 epoch 10 (current best)",
    "casual",
    "reference",
    "LoRA 0.85 (today's setting)",
    "myepoch 4",          # the word boundary is real
    "epoch",
    "",
])
def test_epoch_arm_rejects_everything_else(arm):
    assert epoch_arm(arm) is None


def test_an_empty_prefix_is_not_a_missing_arm():
    """The bug this guards: `if not epoch_arm(a)` would discard `epoch 12`."""
    parsed = epoch_arm("epoch 12")
    assert parsed is not None
    assert parsed[0] == ""


def test_epoch_sweep_name_needs_every_arm_to_agree():
    one = {"items": [{"arm": "ash_v2 epoch 16"}, {"arm": "ash_v2 epoch 17"}]}
    assert epoch_sweep_name(one) == "ash_v2"
    mixed = {"items": [{"arm": "rank64 epoch 14"},
                       {"arm": "rank32 epoch 10 (current best)"}]}
    assert epoch_sweep_name(mixed) is None          # one bad arm sinks the set
    two = {"items": [{"arm": "a epoch 1"}, {"arm": "b epoch 2"}]}
    assert epoch_sweep_name(two) is None            # two prefixes is not one sweep
    assert epoch_sweep_name({"items": []}) is None


# --- the ranking -------------------------------------------------------------

def test_wilson_low_is_below_the_raw_rate_and_rewards_evidence():
    assert wilson_low(8, 10) == pytest.approx(0.649, abs=0.001)
    assert wilson_low(8, 10) < 0.8                       # thin evidence pays
    assert wilson_low(80, 100) > wilson_low(8, 10)       # same rate, more of it
    assert wilson_low(0, 0) == 0.0                       # nothing judged


def _sweep(tmp_path: Path, arms_keep: dict[int, int], *, scenes: int = 10,
           dataset: str = "demo_v2", set_id: str | None = None) -> tuple[Path, str]:
    """A real manifest plus verdicts: `{epoch: n_keeps}` over `scenes` scenes."""
    from PIL import Image

    root = tmp_path / "judge"
    img = tmp_path / "img"
    img.mkdir(parents=True, exist_ok=True)
    sid = set_id or f"dense_{dataset}_asset"
    items, verdicts = [], {}
    for epoch, keeps in arms_keep.items():
        for sc in range(scenes):
            iid = f"e{epoch}_s{sc}"
            p = img / f"{iid}.png"
            if not p.is_file():
                Image.new("RGB", (8, 8)).save(p)
            items.append({"id": iid, "path": p,
                          "arm": f"{dataset} epoch {epoch}", "group": str(sc)})
            verdicts[iid] = "keep" if sc < keeps else "reject"
    make_set(root, sid, f"{dataset} epoch eval", items)
    for iid, v in verdicts.items():
        record_verdict(root, sid, iid, v)
    return root, sid


def test_the_board_ranks_by_low_bound_not_by_rate(tmp_path):
    """8/10 and 80/100 are the same rate; the one with evidence must lead."""
    from PIL import Image

    root = tmp_path / "judge"
    img = tmp_path / "i"
    img.mkdir(parents=True)
    items, verds = [], {}
    for epoch, keep, n in ((16, 8, 10), (17, 80, 100)):
        for k in range(n):
            iid = f"e{epoch}_{k}"
            p = img / f"{iid}.png"
            Image.new("RGB", (8, 8)).save(p)
            items.append({"id": iid, "path": p, "arm": f"d_v2 epoch {epoch}",
                          "group": str(k)})
            verds[iid] = "keep" if k < keep else "reject"
    make_set(root, "dense_d_v2_asset", "t", items)
    for iid, v in verds.items():
        record_verdict(root, "dense_d_v2_asset", iid, v)

    b = epoch_board(root, "dense_d_v2_asset")
    assert [r["epoch"] for r in b["arms"]] == [17, 16]
    assert b["arms"][0]["rate"] == b["arms"][1]["rate"]      # same rate
    assert b["arms"][0]["low"] > b["arms"][1]["low"]         # not the same low


def test_a_tie_names_the_earlier_epoch_safer(tmp_path):
    root, sid = _sweep(tmp_path, {16: 8, 20: 8, 24: 3})
    b = epoch_board(root, sid)
    tied = [r for r in b["arms"] if r["tied"]]
    assert {r["epoch"] for r in tied} == {16, 20}
    safer = [r for r in b["arms"] if r["safer"]]
    assert len(safer) == 1
    assert safer[0]["epoch"] == 16          # earlier, as less overfit
    assert b["tie_low"] == TIE_LOW


def test_the_board_sorts_numerically_not_lexically(tmp_path):
    """summary()['arms'] is sorted by the arm STRING, so an unpadded sweep
    arrives as epoch 10, 15, 20, 5. Equal scores must still come back 5 first."""
    root, sid = _sweep(tmp_path, {5: 4, 10: 4, 15: 4, 20: 4})
    b = epoch_board(root, sid)
    assert [r["epoch"] for r in b["arms"]] == [5, 10, 15, 20]


def test_the_grid_has_holes_not_zeros_when_half_judged(tmp_path):
    from PIL import Image

    root = tmp_path / "judge"
    img = tmp_path / "i"
    img.mkdir(parents=True)
    items = []
    for sc in range(4):
        iid = f"s{sc}"
        p = img / f"{iid}.png"
        Image.new("RGB", (8, 8)).save(p)
        items.append({"id": iid, "path": p, "arm": "d_v2 epoch 9", "group": str(sc)})
    make_set(root, "dense_d_v2_asset", "t", items)
    record_verdict(root, "dense_d_v2_asset", "s0", "keep")
    record_verdict(root, "dense_d_v2_asset", "s1", "reject")

    b = epoch_board(root, "dense_d_v2_asset")
    grid = b["arms"][0]["grid"]
    assert grid == {"0": "keep", "1": "reject"}   # s2/s3 absent, not "reject"
    assert b["judged"] == 2
    assert b["n"] == 4


def test_the_board_is_none_for_a_set_that_is_not_an_epoch_sweep(tmp_path):
    from PIL import Image

    root = tmp_path / "judge"
    img = tmp_path / "i"
    img.mkdir(parents=True)
    items = []
    for i, arm in enumerate(("casual", "workout")):
        p = img / f"{i}.png"
        Image.new("RGB", (8, 8)).save(p)
        items.append({"id": str(i), "path": p, "arm": arm, "group": "0"})
    make_set(root, "assets_amanda", "wardrobe", items)
    assert epoch_board(root, "assets_amanda") is None
    assert epoch_board(root, "no_such_set") is None


# --- resolving the sweep set, which the repo gets wrong ----------------------

def _manifest(root: Path, name: str, arms: list[str], *, items_per: int = 2) -> None:
    d = root / "sets"
    d.mkdir(parents=True, exist_ok=True)
    items = [{"id": f"{a}-{k}", "path": f"x/{a}-{k}.png", "arm": a, "group": str(k)}
             for a in arms for k in range(items_per)]
    (d / f"{name}.json").write_text(json.dumps(
        {"id": name, "title": name, "items": items,
         "order": [i["id"] for i in items]}), encoding="utf-8")


def test_a_sweep_resolves_without_an_asset_suffix(tmp_path):
    """THE REPO BUG. Of 29 `dense_*` sets on disk only 6 carry `_asset`;
    dense_ash_v2.json is a full epoch sweep with no suffix at all. Resolving on
    `dense_<ds>_asset.json` alone finds nothing for it."""
    _manifest(tmp_path, "dense_ash_v2", ["ash_v2 epoch 16", "ash_v2 epoch 17"])
    got = sweep_set_for(tmp_path, "ash_v2")
    assert got is not None
    assert got["id"] == "dense_ash_v2"
    assert got["epochs"] == [16, 17]


def test_an_asset_suffixed_sweep_is_still_an_epoch_sweep(tmp_path):
    """`_asset` does not mean "wardrobe": dense_amanda_v2_asset's arms are
    `amanda_v2 epoch 17`..., so the suffix says nothing about the arms."""
    _manifest(tmp_path, "dense_amanda_v2_asset",
              ["amanda_v2 epoch 17", "amanda_v2 epoch 18"])
    got = sweep_set_for(tmp_path, "amanda_v2")
    assert got is not None
    assert got["output_name"] == "amanda_v2"


def test_a_wardrobe_set_resolves_to_nothing(tmp_path):
    _manifest(tmp_path, "assets_amanda", ["casual", "workout"])
    assert sweep_sets_for(tmp_path, "amanda") == []


def test_a_malformed_manifest_is_skipped_not_fatal(tmp_path):
    d = tmp_path / "sets"
    d.mkdir(parents=True)
    (d / "dense_ash_v2.json").write_text("{not json", encoding="utf-8")
    _manifest(tmp_path, "dense_ash_v2_asset", ["ash_v2 epoch 20"])
    got = sweep_sets_for(tmp_path, "ash_v2")
    assert [r["id"] for r in got] == ["dense_ash_v2_asset"]


def test_two_sweeps_for_one_dataset_come_back_newest_first(tmp_path):
    import os
    import time

    _manifest(tmp_path, "dense_ash_v2", ["ash_v2 epoch 16"])
    _manifest(tmp_path, "dense_ash_v2_asset", ["ash_v2 epoch 22"])
    later = time.time() + 50
    os.utime(tmp_path / "sets" / "dense_ash_v2_asset.json", (later, later))
    assert [r["id"] for r in sweep_sets_for(tmp_path, "ash_v2")][0] == "dense_ash_v2_asset"


# --- the checkpoint resolver -------------------------------------------------

def _ckpt(out: Path, dataset: str, names: list[str], sub: str = "lora") -> Path:
    d = out / "lora-datasets" / dataset / sub
    d.mkdir(parents=True, exist_ok=True)
    for n in names:
        (d / n).write_bytes(b"x")
    return d


def test_checkpoint_for_finds_a_numbered_epoch(tmp_path):
    _ckpt(tmp_path, "ash_v2", ["ash_v2-000017.safetensors"])
    got = checkpoint_for(tmp_path, "ash_v2", "ash_v2", 17)
    assert got and got.endswith("ash_v2-000017.safetensors")


def test_checkpoint_for_finds_the_bare_final_epoch(tmp_path):
    """On disk amanda_internal_v2/lora/ holds -000001..-000023 PLUS a bare
    amanda_internal_v2.safetensors, and that bare file is epoch 24. A
    `*-{epoch:06d}` glob alone returns None for the epoch most likely to win."""
    _ckpt(tmp_path, "a_v2",
          ["a_v2.safetensors", "a_v2-000022.safetensors", "a_v2-000023.safetensors"])
    got = checkpoint_for(tmp_path, "a_v2", "a_v2", 24)
    assert got and got.endswith("a_v2.safetensors")


def test_the_bare_file_is_refused_for_an_epoch_below_the_numbered_top(tmp_path):
    """On a 16-19 sweep, epoch 19 is the sweep's top arm but NOT the run's last
    epoch, and the bare file there belongs to a later epoch entirely."""
    _ckpt(tmp_path, "a_v2",
          ["a_v2.safetensors", "a_v2-000022.safetensors", "a_v2-000023.safetensors"])
    assert checkpoint_for(tmp_path, "a_v2", "a_v2", 19) is None


def test_checkpoint_for_searches_a_lora_sibling_directory(tmp_path):
    """bianca_v2 has lora/, lora_bianca_lr2/ and lora_bianca_lr2b/ side by side,
    and the ARM says which one the sweep means."""
    _ckpt(tmp_path, "bianca_v2", ["bianca_lr2b-000025.safetensors"],
          sub="lora_bianca_lr2b")
    got = checkpoint_for(tmp_path, "bianca_v2", "bianca_lr2b", 25)
    assert got and got.endswith("bianca_lr2b-000025.safetensors")
    assert any(p.name == "lora_bianca_lr2b"
               for p in checkpoint_dirs(tmp_path, "bianca_v2", "bianca_lr2b"))


def test_an_output_name_that_is_not_a_dataset_still_resolves(tmp_path):
    """`dense_bianca_lr2b_fav` resolves to a DATASET "bianca_lr2b" that has no
    directory - those checkpoints live under bianca_v2/lora_bianca_lr2b/."""
    _ckpt(tmp_path, "bianca_v2", ["bianca_lr2b-000027.safetensors"],
          sub="lora_bianca_lr2b")
    got = checkpoint_for(tmp_path, "bianca_lr2b", "bianca_lr2b", 27)
    assert got and got.endswith("bianca_lr2b-000027.safetensors")


def test_a_missing_checkpoint_is_none_not_an_error(tmp_path):
    assert checkpoint_for(tmp_path, "nobody_v2", "nobody_v2", 3) is None


# --- the record --------------------------------------------------------------

def test_record_choice_round_trips(tmp_path):
    _ckpt(tmp_path, "ash_v2", ["ash_v2-000017.safetensors"])
    rec = record_choice(tmp_path, "ash", dataset="ash_v2", output_name="ash_v2",
                        epoch=17, from_set="dense_ash_v2", keep=8, n=10, low=0.649)
    assert rec["epoch"] == 17
    assert rec["rate"] == 0.8
    assert rec["lora"].endswith("ash_v2-000017.safetensors")
    assert load_choice(tmp_path, "ash") == rec
    assert [r["character"] for r in list_choices(tmp_path)] == ["ash"]
    # atomic: no .tmp left behind
    assert not list((tmp_path / "epoch-choices").glob("*.tmp"))


def test_a_choice_is_recorded_even_when_the_checkpoint_was_pruned(tmp_path):
    """ash_v2/lora/ holds exactly one file today; the losers are gone. A choice
    is a judgement, and a missing file is not a reason to refuse to record it."""
    _ckpt(tmp_path, "ash_v2", ["ash_v2-000017.safetensors"])
    rec = record_choice(tmp_path, "ash", dataset="ash_v2", epoch=21)
    assert rec["lora"] is None
    assert rec["epoch"] == 21
    assert load_choice(tmp_path, "ash")["lora"] is None


def test_record_choice_with_no_keep_count_has_no_rate(tmp_path):
    rec = record_choice(tmp_path, "ash", dataset="ash_v2", epoch=4)
    assert rec["rate"] is None
    assert rec["keep"] is None


@pytest.mark.parametrize("bad", ["", "../x", "a/b", "a" + chr(92) + "b"])
def test_a_character_id_that_escapes_the_directory_is_refused(tmp_path, bad):
    with pytest.raises(ValueError, match="character id"):
        record_choice(tmp_path, bad, dataset="d_v2", epoch=1)
    assert load_choice(tmp_path, bad) is None


def test_a_half_written_choice_file_does_not_lose_the_others(tmp_path):
    record_choice(tmp_path, "ash", dataset="ash_v2", epoch=17)
    (tmp_path / "epoch-choices" / "broken.json").write_text("{", encoding="utf-8")
    assert [r["character"] for r in list_choices(tmp_path)] == ["ash"]
    assert load_choice(tmp_path, "broken") is None


def test_the_board_reports_a_choice_only_for_the_set_it_came_from(tmp_path):
    root, sid = _sweep(tmp_path / "j", {16: 8, 20: 3}, dataset="demo_v2")
    out = tmp_path / "o"
    assert epoch_board(root, sid, outputs=out)["chosen"] is None
    record_choice(out, "demo", dataset="demo_v2", epoch=16, from_set=sid)
    assert epoch_board(root, sid, outputs=out)["chosen"]["epoch"] == 16
    # a choice made from a DIFFERENT set is not this board's answer
    record_choice(out, "demo", dataset="demo_v2", epoch=20, from_set="other_set")
    assert epoch_board(root, sid, outputs=out)["chosen"] is None
