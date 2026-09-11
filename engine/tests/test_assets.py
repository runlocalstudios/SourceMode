"""Asset cutouts: everything but the model itself, tested with an injected remover."""

import json
from pathlib import Path

import numpy as np
from PIL import Image

from sourcemode.assets.cutout import (
    alpha_report, checkerboard_sheet, collect, cutout_batch, cutout_file, fit_canvas, parse_size,
)


def figure(w=200, h=300, box=(60, 40, 140, 300)):
    """An RGB render with a flat grey background and a rectangle 'figure'."""
    img = Image.new("RGB", (w, h), (200, 200, 200))
    px = img.load()
    for y in range(box[1], box[3]):
        for x in range(box[0], box[2]):
            px[x, y] = (120, 60, 30)
    return img


def fake_remover(img: Image.Image) -> Image.Image:
    """Keys out the flat grey: alpha 255 where the pixel isn't background."""
    arr = np.asarray(img.convert("RGB")).astype(int)
    fg = np.abs(arr - np.array([200, 200, 200])).sum(axis=2) > 30
    out = np.dstack([arr, np.where(fg, 255, 0)]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def test_alpha_report_clean_standing_figure():
    a = np.zeros((300, 200), np.uint8); a[40:300, 60:140] = 255
    r = alpha_report(a)
    assert r["coverage"] == round(80 * 260 / 60000, 4)
    assert r["partial"] == 0.0 and r["components"] == 1
    assert r["touches"] == ["bottom"] and r["flags"] == []      # feet on the floor line is normal


def test_alpha_report_flags():
    a = np.zeros((100, 100), np.uint8)
    assert alpha_report(a)["flags"] == ["empty"]
    a[0:50, 0:50] = 255                                         # touches top+left
    assert set(alpha_report(a)["flags"]) == {"clipped"}
    b = np.zeros((100, 100), np.uint8); b[10:50, 10:50] = 255; b[70:90, 70:90] = 255
    assert "islands" in alpha_report(b)["flags"] and alpha_report(b)["components"] == 2
    c = np.full((100, 100), 128, np.uint8)                      # everything half-transparent
    assert "hollow" in alpha_report(c)["flags"]
    d = np.zeros((100, 100), np.uint8); d[50:52, 50:52] = 255
    assert "tiny" in alpha_report(d)["flags"]


def test_fit_canvas_pads_bottom_centre_without_upscaling():
    img = Image.new("RGBA", (100, 125), (255, 0, 0, 255))     # 4:5 like the photo sets
    out = fit_canvas(img, (100, 150))
    assert out.size == (100, 150)
    a = np.asarray(out.getchannel("A"))
    assert a[:25].max() == 0 and a[25:].min() == 255           # transparent strip on top, figure at the bottom
    small = fit_canvas(Image.new("RGBA", (10, 10), (0, 255, 0, 255)), (100, 150))
    assert np.asarray(small.getchannel("A")).sum() == 255 * 100  # not upscaled


def test_fit_canvas_scales_down_to_fit():
    out = fit_canvas(Image.new("RGBA", (2048, 2560), (0, 0, 255, 255)), (1024, 1536))
    a = np.asarray(out.getchannel("A"))
    assert out.size == (1024, 1536) and (a > 0).sum() == 1024 * 1280


def test_parse_size():
    assert parse_size("1024x1536") == (1024, 1536)
    assert parse_size("1024×1536") == (1024, 1536)
    assert parse_size(None) is None


def test_cutout_file_writes_png_webp_and_sidecar(tmp_path: Path):
    src = tmp_path / "priyanka_sundress_s9100.png"; figure().save(src)
    r = cutout_file(src, tmp_path / "out", remover=fake_remover, model="fake", size=(200, 400), webp=True)
    png = Image.open(r["outputs"]["png"]); wp = Image.open(r["outputs"]["webp"])
    assert png.mode == "RGBA" and png.size == (200, 400)
    assert wp.format == "WEBP" and wp.mode == "RGBA" and wp.size == (200, 400)
    side = json.loads((tmp_path / "out" / "priyanka_sundress_s9100.json").read_text())
    assert side["model"] == "fake" and side["source"].endswith("s9100.png") and len(side["source_sha256"]) == 16
    assert side["report"]["flags"] == [] and side["report"]["touches"] == ["bottom"]


def test_cutout_batch_logs_flags_and_sheet(tmp_path: Path):
    srcs = []
    for i in range(3):
        p = tmp_path / f"shot_{i}.png"; figure().save(p); srcs.append(p)
    lines = []
    res = cutout_batch(srcs, tmp_path / "out", remover=fake_remover, model="fake", log=lines.append)
    assert len(res) == 3 and all("coverage" in ln for ln in lines)
    sheet = checkerboard_sheet([Path(r["outputs"]["png"]) for r in res], tmp_path / "review" / "sheet.png")
    assert sheet.exists() and Image.open(sheet).size[0] == 4 * 320


def test_cutout_batch_mirrors_folders_so_same_named_shots_do_not_collide(tmp_path: Path):
    """Every character's photo set has a shot_00_s9100.png; two of them must both survive."""
    a = tmp_path / "priyanka" / "00_sundress"; b = tmp_path / "sunny" / "00_sundress"
    a.mkdir(parents=True); b.mkdir(parents=True)
    figure().save(a / "shot_00_s9100.png"); figure(box=(20, 40, 100, 300)).save(b / "shot_00_s9100.png")
    res = cutout_batch([a / "shot_00_s9100.png", b / "shot_00_s9100.png"], tmp_path / "out",
                       remover=fake_remover, model="fake", log=lambda s: None)
    outs = sorted(Path(r["outputs"]["png"]).relative_to((tmp_path / "out").resolve()).as_posix() for r in res)
    assert outs == ["priyanka/00_sundress/shot_00_s9100.png", "sunny/00_sundress/shot_00_s9100.png"]
    assert len({r["report"]["bbox"][0] for r in res}) == 2          # genuinely different images kept


def test_cutout_carries_slot_identity_from_render_sidecar_or_folder(tmp_path: Path):
    from sourcemode.assets.cutout import source_meta
    d = tmp_path / "priyanka" / "renders" / "casual_date_03_standing"; d.mkdir(parents=True)
    src = d / "shot_00_s7100.png"; figure().save(src)
    m = source_meta(src)                                    # folder name alone is enough
    assert m["asset"] == {"character": "priyanka", "category": "casual_date", "look": 3, "pose": "standing"}
    src.with_suffix(".json").write_text(json.dumps({"asset": {"character": "priyanka", "category": "casual_date",
                                                              "look": 3, "pose": "standing", "shot": 0}, "score": 0.81}))
    r = cutout_file(src, tmp_path / "out", remover=fake_remover, model="fake")
    assert r["asset"]["look"] == 3 and r["score"] == 0.81   # sidecar wins and adds the score
    loose = tmp_path / "loose.png"; figure().save(loose)
    assert "asset" not in cutout_file(loose, tmp_path / "out2", remover=fake_remover, model="fake")


# ------------------------------------------------------------------ catalog

def test_runtime_names_follow_the_game_contract():
    from sourcemode.assets.catalog import look_id, parse_runtime_name, runtime_name
    assert runtime_name("casual", 3) == "casual_03_standing.webp"
    assert runtime_name("fancy_dining_gallery", 12, "sitting") == "fancy_dining_gallery_12_sitting.webp"
    assert runtime_name("weekly_casual", 1) == "casual_01_standing.webp"      # art-source alias -> runtime prefix
    assert look_id("work", 5) == "work_05"
    assert parse_runtime_name("fancy_dining_gallery_02_standing.webp") == {"category": "fancy_dining_gallery", "look": 2, "pose": "standing"}
    assert parse_runtime_name("casual_07_sitting.webp")["pose"] == "sitting"
    assert parse_runtime_name("profile.webp") is None
    assert parse_runtime_name("work_03.webp") is None                        # legacy, no pose
    import pytest
    with pytest.raises(ValueError):
        runtime_name("casual", 1, "kneeling")


def test_existing_looks_reads_a_shipped_outfits_folder(tmp_path: Path):
    from sourcemode.assets.catalog import existing_looks
    for n in ("casual_01_standing.webp", "casual_07_standing.webp", "work_05_standing.webp", "profile.webp"):
        (tmp_path / n).write_bytes(b"x")
    assert existing_looks(tmp_path) == {"casual": 7, "work": 5}
    assert existing_looks(tmp_path / "nope") == {}


def test_plan_assigns_look_numbers_once_and_can_extend_a_pack():
    from sourcemode.assets.catalog import PACK_28, make_plan, plan_slots
    plan = make_plan("priyanka", looks={"work": [{"outfit": "a blazer", "hair": "a bun"}]},
                     lora="sourcemode\\priyanka\\priyanka_v1.safetensors", source_asset="x.png")
    slots = plan_slots(plan)
    assert len(slots) == sum(PACK_28.values()) == 28
    assert [s["id"] for s in slots if s["category"] == "casual"] == [f"casual_{i:02d}" for i in range(1, 8)]
    work = [s for s in slots if s["category"] == "work"]
    assert work[0]["outfit"] == "a blazer" and work[1]["outfit"] == ""      # unfilled looks stay blank
    assert work[0]["filename"] == "work_01_standing.webp"
    ext = make_plan("priyanka", counts={"casual": 2}, start_after={"casual": 7})
    assert [s["id"] for s in plan_slots(ext)] == ["casual_08", "casual_09"]


def test_place_picks_best_per_slot_and_names_by_contract(tmp_path: Path):
    from sourcemode.assets.catalog import make_plan, mapping_sheet, pack_registration, place
    plan = make_plan("sunny", counts={"casual": 1, "work": 1})
    def cut(cat, look, name, score, flags=()):
        p = tmp_path / "cut" / name; p.parent.mkdir(exist_ok=True, parents=True)
        im = Image.new("RGBA", (40, 60), (0, 0, 0, 0)); im.paste((255, 0, 0, 255), (10, 10, 30, 60))
        im.save(p, "WEBP", exact=True)                    # a real cutout: transparent margin, opaque figure
        return {"source": f"C:/r/{cat}_{look:02d}_standing/{name.replace('.webp', '.png')}", "outputs": {"webp": str(p)},
                "asset": {"character": "sunny", "category": cat, "look": look, "pose": "standing"},
                "score": score, "report": {"flags": list(flags), "partial": 0.01}}
    cuts = [cut("casual", 1, "a.webp", 0.90, flags=("hollow",)),  # best score but flagged -> loses
            cut("casual", 1, "b.webp", 0.80),
            cut("work", 1, "c.webp", 0.70)]
    m = place(cuts, plan, tmp_path / "staging")
    files = sorted(p.name for p in (tmp_path / "staging" / "sunny" / "outfits").iterdir())
    assert files == ["casual_01_standing.webp", "work_01_standing.webp"]
    casual = next(s for s in m["slots"] if s["id"] == "casual_01")
    assert casual["from"].endswith("b.png") and casual["candidates"] == 2 and m["missing"] == []
    assert Image.open(tmp_path / "staging" / "sunny" / "outfits" / "casual_01_standing.webp").mode == "RGBA"
    # a human override beats the ranking
    m2 = place(cuts, plan, tmp_path / "staging2", pick={"casual_01": "a.webp"})
    assert next(s for s in m2["slots"] if s["id"] == "casual_01")["from"].endswith("a.png")
    # empty slot is reported, not invented
    m3 = place(cuts[:2], plan, tmp_path / "staging3")
    assert m3["missing"] == ["work_01"]
    sheet = mapping_sheet(m, tmp_path / "staging", tmp_path / "staging" / "sunny" / "review.jpg")
    assert sheet.exists()
    assert pack_registration(plan, work_locations=["coffeeShop"]) == "  sunny: { id: 'sunny', workLocations: ['coffeeShop'] },"


def test_shot_prompt_names_the_look_and_a_keyable_background():
    from sourcemode.assets.render import shot_prompt
    p = shot_prompt("priyanka", {"outfit": "a red dress", "hair": "a high ponytail", "pose": "standing"})
    assert p.startswith("priyanka_ch. ") and "a red dress" in p and "a high ponytail" in p
    assert "medium grey background" in p and "glasses" not in p


def test_collect_skips_plates_and_non_images(tmp_path: Path):
    (tmp_path / "a.png").write_bytes(b"x"); (tmp_path / "_plate.png").write_bytes(b"x")
    (tmp_path / "scores.json").write_bytes(b"x"); (tmp_path / "sub").mkdir(); (tmp_path / "sub" / "b.PNG").write_bytes(b"x")
    got = [p.name for p in collect([tmp_path])]
    assert got == ["a.png"] or set(got) == {"a.png", "b.PNG"}
    assert "_plate.png" not in got and "scores.json" not in got
    assert collect([tmp_path / "a.png", tmp_path / "scores.json"]) == [tmp_path / "a.png"]
