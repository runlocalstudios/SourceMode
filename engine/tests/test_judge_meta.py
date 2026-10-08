"""A judge set records what its writer knew; readers stop parsing the set id.

`dense_jaina_v2_asset_nofreckles` was once read as a dataset called
jaina_v2_asset_nofreckles: no checkpoints found, every arm "pruned", three
epoch picks filed under characters that do not exist (2026-10-07).
"""

from PIL import Image

from sourcemode.assets.judge import epoch_board, load_set, make_set, record_verdict


def _items(tmp_path, dataset="d_v2"):
    img = tmp_path / "img"
    img.mkdir(exist_ok=True)
    items = []
    for ep in (16, 17):
        for sc in range(3):
            p = img / f"e{ep}_{sc}.png"
            Image.new("RGB", (8, 8)).save(p)
            items.append({"id": f"e{ep}_{sc}", "path": p, "arm": f"{dataset} epoch {ep}", "group": str(sc)})
    return items


def test_meta_is_written_with_paths_as_strings(tmp_path):
    root = tmp_path / "judge"
    make_set(root, "s", "t", _items(tmp_path),
             meta={"character": "d", "dataset": "d_v2", "renders_dir": tmp_path / "out"})
    doc = load_set(root, "s")
    assert doc["meta"] == {"character": "d", "dataset": "d_v2", "renders_dir": str(tmp_path / "out")}
    make_set(root, "s2", "t", _items(tmp_path))
    assert load_set(root, "s2")["meta"] == {}


def test_the_board_takes_dataset_and_character_from_meta_not_the_id(tmp_path):
    root = tmp_path / "judge"
    sid = "dense_d_v2_asset_sometag_with_underscores"
    make_set(root, sid, "t", _items(tmp_path), meta={"character": "d", "dataset": "d_v2"})
    for it in _items(tmp_path):
        record_verdict(root, sid, it["id"], "keep")
    b = epoch_board(root, sid)
    assert b["dataset"] == "d_v2" and b["character"] == "d"


def test_a_set_without_meta_still_parses_its_id(tmp_path):
    root = tmp_path / "judge"
    sid = "dense_d_v2_asset_nofreckles"
    make_set(root, sid, "t", _items(tmp_path))
    for it in _items(tmp_path):
        record_verdict(root, sid, it["id"], "keep")
    assert epoch_board(root, sid)["dataset"] == "d_v2"
