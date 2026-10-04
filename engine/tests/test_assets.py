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
    slot = {"outfit": "a red dress", "hair": "a high ponytail", "pose": "standing"}
    p = shot_prompt("priyanka", slot)
    assert p.startswith("priyanka. ") and "a red dress" in p and "a high ponytail" in p
    # magenta since 2026-10-02: the grey plate left residue in the cutouts, so the
    # backdrop is now the Codex chroma colour and keyed with --chroma magenta
    assert "magenta #FF00FF background" in p and "glasses" not in p
    # the trigger is the bare name by default, but a plan can name an older token
    assert shot_prompt("priyanka", slot, "priyanka_ch").startswith("priyanka_ch. ")


def test_collect_skips_plates_and_non_images(tmp_path: Path):
    (tmp_path / "a.png").write_bytes(b"x"); (tmp_path / "_plate.png").write_bytes(b"x")
    (tmp_path / "scores.json").write_bytes(b"x"); (tmp_path / "sub").mkdir(); (tmp_path / "sub" / "b.PNG").write_bytes(b"x")
    got = [p.name for p in collect([tmp_path])]
    assert got == ["a.png"] or set(got) == {"a.png", "b.PNG"}
    assert "_plate.png" not in got and "scores.json" not in got
    assert collect([tmp_path / "a.png", tmp_path / "scores.json"]) == [tmp_path / "a.png"]


def test_chroma_remover_keys_magenta_and_keeps_the_figure():
    """A render we shot ourselves on #FF00FF keys exactly, with no model."""
    import numpy as np
    from PIL import Image

    from sourcemode.assets.cutout import MAGENTA, chroma_remover

    im = Image.new("RGB", (40, 60), MAGENTA)
    im.paste((180, 140, 120), (10, 10, 30, 50))          # a skin-toned figure
    out = chroma_remover()(im)
    a = np.asarray(out)[:, :, 3]
    assert out.mode == "RGBA"
    assert a[0, 0] == 0 and a[59, 39] == 0               # background fully transparent
    assert a[30, 20] == 255                              # figure fully opaque


def test_shadowed_magenta_in_an_enclosed_gap_still_keys():
    """The production failure: the gap between an arm and a hip is magenta in
    shadow, and an RGB-distance key leaves it as an opaque blob."""
    import numpy as np
    from PIL import Image

    from sourcemode.assets.cutout import chroma_remover

    im = Image.new("RGB", (30, 30), (255, 0, 255))
    im.paste((190, 150, 130), (5, 5, 25, 25))            # the figure
    for xy, shade in (((12, 12), (120, 0, 120)), ((13, 12), (70, 0, 70)), ((14, 12), (40, 2, 44))):
        im.putpixel(xy, shade)                            # enclosed gap, progressively darker
    a = np.asarray(chroma_remover()(im))[:, :, 3]
    assert a[12, 12] == 0 and a[12, 13] == 0 and a[12, 14] == 0
    assert a[20, 20] == 255                               # the figure around it is untouched


def test_saturated_red_clothing_is_not_tarnished():
    """The other production failure: red garments came out dark and orange because
    despill subtracted the magenta excess from every pixel."""
    import numpy as np
    from PIL import Image

    from sourcemode.assets.cutout import chroma_remover

    reds = [(200, 30, 30), (180, 20, 60), (220, 40, 70), (255, 0, 40)]
    im = Image.new("RGB", (len(reds) * 4 + 8, 12), (255, 0, 255))
    for i, c in enumerate(reds):
        im.paste(c, (4 + i * 4, 4, 8 + i * 4, 8))
    out = np.asarray(chroma_remover(despill=1.0)(im))
    for i, c in enumerate(reds):
        px = out[6, 6 + i * 4]
        assert tuple(int(v) for v in px[:3]) == c, f"{c} shifted to {tuple(px[:3])}"
        assert px[3] == 255


def test_chroma_remover_despills_only_partial_edge_pixels():
    """Spill is removed where a pixel is a mix of figure and backdrop, and nowhere else."""
    import numpy as np
    from PIL import Image

    from sourcemode.assets.cutout import chroma_remover

    im = Image.new("RGB", (6, 6), (255, 0, 255))
    im.putpixel((3, 3), (210, 90, 210))                   # hair half-covering the backdrop
    out = np.asarray(chroma_remover(despill=1.0)(im))
    a = out[3, 3, 3]
    assert 0 < a < 255                                     # partial coverage
    r, g, b = (int(v) for v in out[3, 3, :3])
    # The pixel must stop being magenta-dominated. Not "r below its observed value":
    # unpremultiply brightens every channel, so the meaningful test is the cast.
    assert r - g <= 0 and b - g <= 0, f"still magenta-dominated ({r},{g},{b})"
    assert (210 - 90) - (r - g) > 100                       # and the cast really was removed
    assert np.asarray(chroma_remover(despill=0.0)(im))[3, 3, 0] == 210   # opt out works


def test_chroma_remover_supports_a_green_key():
    import numpy as np
    from PIL import Image

    from sourcemode.assets.cutout import GREEN, chroma_remover

    im = Image.new("RGB", (8, 8), GREEN)
    im.paste((200, 30, 30), (2, 2, 6, 6))                 # a magenta-wearing character's red top
    a = np.asarray(chroma_remover(GREEN)(im))[:, :, 3]
    assert a[0, 0] == 0 and a[4, 4] == 255




def test_the_key_separates_shadowed_magenta_from_red_clothing():
    """The two production failures are one discriminator problem: a difference-based
    score gives shadowed magenta 38 and crimson 40, indistinguishable. Keyness,
    which also requires R and B to be balanced, must separate them cleanly."""
    import numpy as np

    from sourcemode.assets.cutout import MAGENTA, key_spill

    def k(c):
        return float(key_spill(np.array([[c]], dtype=np.float32), MAGENTA)[0, 0])

    backdrop = [(255, 0, 255), (120, 0, 120), (70, 0, 70), (40, 2, 44)]
    garments = [(180, 20, 60), (255, 0, 40), (200, 30, 30), (255, 255, 255), (0, 0, 0)]
    assert min(k(c) for c in backdrop) > 0.70, "shadowed magenta must key"
    assert max(k(c) for c in garments) < 0.40, "no garment may key"
    assert k((190, 150, 130)) == 0.0 and k((20, 15, 18)) < 0.4


def test_despill_never_pushes_a_pixel_to_the_key_complement():
    """Despill may remove the key's colour, never invert past neutral.

    Our alpha is a keyness ramp, not true coverage, so unpremultiply over-subtracts
    wherever the two disagree: 72,437 of 86,230 partial-alpha pixels across val's
    plates came out more than 25 counts violet from a GREEN backdrop. The mirror of
    the red tarnish, and just as wrong.
    """
    import numpy as np

    from sourcemode.assets.cutout import GREEN, MAGENTA, chroma_remover, despill_unpremultiply

    # A dark green-lit edge pixel at half coverage. Plain unpremultiply removes
    # 0.5 * 255 of green, far more green than the pixel has, and the result clips
    # to a pure magenta. Capped at the excess it stops exactly at neutral.
    rgb = np.array([[[30.0, 120.0, 40.0]]])
    a = np.array([[0.5]])
    out = despill_unpremultiply(rgb, a, GREEN)
    assert out[0, 0, 1] >= min(out[0, 0, 0], out[0, 0, 2]), "must not invert past neutral"
    assert out[0, 0, 1] == 60.0, "G capped at the 30-count excess, then /0.5"
    assert out[0, 0, 0] == 60.0 and out[0, 0, 2] == 80.0, "weak channels only brightened"

    # a pixel with no excess loses no colour at all, only the brightening
    flat = np.array([[[80.0, 80.0, 80.0]]])
    assert despill_unpremultiply(flat, a, GREEN)[0, 0].tolist() == [160.0, 160.0, 160.0]

    # a magenta key caps R and B, not G
    m = np.array([[[210.0, 90.0, 210.0]]])
    mo = despill_unpremultiply(m, a, MAGENTA)
    assert mo[0, 0, 0] <= mo[0, 0, 1] and mo[0, 0, 2] <= mo[0, 0, 1], "magenta pulled out"

    # end to end: a real plate's edge pixel stays out of the violets
    from PIL import Image
    im = Image.new("RGB", (6, 6), (0, 255, 0))
    im.putpixel((3, 3), (60, 110, 70))                 # dark hair partly over the backdrop
    px = np.asarray(chroma_remover(GREEN, inner=0.25, outer=0.45, despill=1.0)(im))[3, 3]
    r, g, b = (int(v) for v in px[:3])
    assert 0 < px[3] < 255, "must be a partial edge pixel for this to test anything"
    assert g >= min(r, b), f"despill produced violet ({r},{g},{b})"


def test_key_spill_ignores_near_black_pixels():
    """Purity is a ratio, so noise in a dark pixel reads as high keyness.

    Val's black latex dress had 2.9% of its near-black pixels score above the
    keying threshold on a couple of counts of green bias, and shipped punched
    full of holes that showed as white dots on a light background. The floor must
    not reach the darkest backdrop the enclosed-gap case needs.
    """
    import numpy as np

    from sourcemode.assets.cutout import GREEN, MAGENTA, key_spill

    def k(c, key=GREEN, **kw):
        return float(key_spill(np.array([[c]], dtype=np.float32), key, **kw)[0, 0])

    # black latex with a few counts of green bias: was keying, must not
    for c in ((2, 5, 3), (6, 11, 7), (1, 4, 2), (8, 14, 9)):
        assert k(c) < 0.25, f"{c} scored {k(c):.2f} and would punch a hole"
    # lit and shadowed backdrop both still key
    assert k((0, 255, 0)) > 0.9 and k((20, 120, 25)) > 0.5
    # the magenta enclosed-gap case from the despill work is untouched
    assert k((40, 2, 44), MAGENTA) > 0.70
    # opting out restores the old ratio-only behaviour
    assert k((2, 5, 3), floor=0.0) > 0.25


def test_fill_alpha_holes_closes_partial_alpha_speckles():
    """The speckles are mostly partial alpha, which an `alpha < 128` test misses.

    In val's latex dress, alpha 129-250 pixels outnumbered near-transparent ones
    ten to one, so the original hole filling closed almost none of the defect.
    Filled pixels must also lose their backdrop colour, since a keyed pixel's own
    RGB is either pure backdrop or an unpremultiply by a near-zero divisor.
    """
    import numpy as np

    from sourcemode.assets.cutout import fill_alpha_holes

    a = np.zeros((40, 40, 4), dtype=np.uint8)
    a[5:35, 5:35] = [20, 20, 20, 255]          # a dark opaque figure
    a[10, 10] = [0, 255, 0, 200]               # partial speckle, backdrop-coloured
    a[20:22, 20:22] = [0, 255, 0, 160]         # a small partial island
    a[15, 15] = [0, 255, 0, 0]                 # a fully transparent pinhole
    a[0:5, :] = [0, 255, 0, 0]                 # the real backdrop, touching the border

    out, n = fill_alpha_holes(a)
    assert n == 6, f"filled {n}, expected the speckle, the 2x2 island and the pinhole"
    assert out[10, 10, 3] == 255 and out[20, 20, 3] == 255 and out[15, 15, 3] == 255
    assert tuple(out[10, 10, :3]) == (20, 20, 20), "filled pixel kept its backdrop colour"
    assert out[0, 0, 3] == 0, "the real backdrop must stay transparent"

    # a genuine gap reaching the outside stays open however small
    b = np.zeros((40, 40, 4), dtype=np.uint8)
    b[:, :] = [20, 20, 20, 255]
    b[0:30, 20] = [0, 0, 0, 0]                 # a slit from the top edge inward
    out2, n2 = fill_alpha_holes(b)
    assert n2 == 0 and out2[10, 20, 3] == 0


def test_auto_chroma_keys_a_backdrop_that_is_not_the_intended_colour():
    """Val's plates were meant to be #00FF00 and arrived as (45,227,36) through
    (94,229,63). The fixed green test scores the yellower ones only 0.60, which
    leaves a haze; detecting the actual colour sidesteps it."""
    import numpy as np
    from PIL import Image

    from sourcemode.assets.cutout import auto_chroma_remover

    for backdrop in [(45, 227, 36), (94, 229, 63), (72, 226, 47)]:
        im = Image.new("RGB", (40, 60), backdrop)
        im.paste((190, 150, 130), (10, 10, 30, 50))          # the figure
        a = np.asarray(auto_chroma_remover()(im))[:, :, 3]
        assert a[0, 0] == 0, f"{backdrop} not keyed"
        assert a[30, 20] == 255, f"{backdrop} ate the figure"


def test_auto_chroma_leaves_the_image_alone_when_the_border_is_not_a_backdrop():
    import numpy as np
    from PIL import Image

    from sourcemode.assets.cutout import auto_chroma_remover

    rng = np.random.default_rng(0)
    noisy = Image.fromarray(rng.integers(0, 255, (40, 40, 3), dtype=np.uint8))
    out = auto_chroma_remover()(noisy)
    assert out.mode == "RGBA"
    assert (np.asarray(out)[:, :, 3] == 255).all()            # nothing keyed


def test_edge_spill_suppression_clears_green_from_opaque_hair():
    """Unpremultiply only fixes partial pixels. An opaque hair strand carrying
    bounce off a green backdrop keeps it and reads as olive - val's curls held
    22,789 such pixels."""
    import numpy as np
    from PIL import Image

    from sourcemode.assets.cutout import GREEN, chroma_remover

    im = Image.new("RGB", (80, 80), GREEN)
    im.paste((54, 61, 25), (30, 30, 50, 50))          # green-contaminated dark hair
    plain = np.asarray(chroma_remover(GREEN, inner=0.25, outer=0.45)(im))
    fixed = np.asarray(chroma_remover(GREEN, inner=0.25, outer=0.45, edge_spill_px=48)(im))
    r, g, b = (int(v) for v in plain[40, 40, :3])
    assert g > max(r, b), "fixture should start with green dominant"
    r2, g2, b2 = (int(v) for v in fixed[40, 40, :3])
    assert g2 <= max(r2, b2) + 1, f"green still dominant: {(r2, g2, b2)}"
    assert fixed[40, 40, 3] == 255                      # still opaque


def test_edge_spill_leaves_a_green_garment_alone_away_from_the_edge():
    """Band-limited on purpose: a genuinely green garment in the middle of a torso
    must survive, the same reason despill is never applied globally."""
    import numpy as np
    from PIL import Image

    from sourcemode.assets.cutout import GREEN, chroma_remover

    im = Image.new("RGB", (400, 400), GREEN)
    im.paste((150, 120, 110), (60, 60, 340, 340))     # a large figure
    im.paste((40, 160, 60), (170, 170, 230, 230))     # green top, far from any edge
    out = np.asarray(chroma_remover(GREEN, inner=0.25, outer=0.45, edge_spill_px=24)(im))
    r, g, b = (int(v) for v in out[200, 200, :3])
    assert (r, g, b) == (40, 160, 60), f"green garment altered to {(r, g, b)}"


def test_fill_alpha_holes_closes_interior_speckles_but_not_real_gaps():
    """A chroma key punches transparent dots inside dark hair; those read as light
    flecks once composited. A real gap between curls reaches the outside."""
    import numpy as np

    from sourcemode.assets.cutout import fill_alpha_holes

    rgba = np.zeros((100, 100, 4), dtype=np.uint8)
    rgba[..., 3] = 0
    rgba[20:80, 20:80, 3] = 255                  # the figure
    rgba[40:44, 40:44, 3] = 0                    # a speckle inside it (16 px)
    rgba[20:80, 0:25, 3] = 0                     # a gap open to the left border
    out, filled = fill_alpha_holes(rgba, max_area=400)
    assert filled == 16
    assert out[42, 42, 3] == 255                 # speckle closed
    assert out[50, 10, 3] == 0                   # border-connected gap untouched


def test_fill_alpha_holes_respects_max_area():
    import numpy as np

    from sourcemode.assets.cutout import fill_alpha_holes

    rgba = np.zeros((200, 200, 4), dtype=np.uint8)
    rgba[..., 3] = 255
    rgba[80:130, 80:130, 3] = 0                  # a 2500 px interior region
    out, filled = fill_alpha_holes(rgba, max_area=400)
    assert filled == 0 and out[100, 100, 3] == 0
