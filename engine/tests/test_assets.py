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


def test_collect_skips_plates_and_non_images(tmp_path: Path):
    (tmp_path / "a.png").write_bytes(b"x"); (tmp_path / "_plate.png").write_bytes(b"x")
    (tmp_path / "scores.json").write_bytes(b"x"); (tmp_path / "sub").mkdir(); (tmp_path / "sub" / "b.PNG").write_bytes(b"x")
    got = [p.name for p in collect([tmp_path])]
    assert got == ["a.png"] or set(got) == {"a.png", "b.PNG"}
    assert "_plate.png" not in got and "scores.json" not in got
    assert collect([tmp_path / "a.png", tmp_path / "scores.json"]) == [tmp_path / "a.png"]
