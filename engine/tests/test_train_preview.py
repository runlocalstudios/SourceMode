"""Dataset preview: what trains is what was looked at and approved."""

import json
from pathlib import Path

import pytest
from PIL import Image

from sourcemode.train.preview import (
    VARIABLE, approval_state, build_preview, collect_images, fingerprint, image_path,
    list_previews, load_preview, missing_attributes, preview_payload, record_approval,
)

CAPTION = ("jojo, a head-and-shoulders portrait, turned slightly toward her left, "
           "her hair worn loose, a soft closed-mouth smile, wearing a red top, "
           "lit by soft window daylight, against a softly blurred kitchen")


def make_dataset(tmp_path: Path, n=3, caption=CAPTION, with_txt=True) -> Path:
    d = tmp_path / "ds" / "image_face"
    d.mkdir(parents=True)
    for i in range(n):
        p = d / f"face_{i:03d}.png"
        Image.new("RGB", (16, 16), (10 * i, 20, 30)).save(p)
        if with_txt:
            p.with_suffix(".txt").write_text(caption, encoding="utf-8")
    return tmp_path / "ds"


def test_missing_attributes_names_what_the_caption_forgot():
    """The gabi failure: hair never captioned, so hair became the identity and the
    wardrobe pipeline fought it for a month. The aggregate gate scored that set 1.0."""
    assert missing_attributes(CAPTION) == []
    no_hair = ("gabi_ch, on a balcony above a city skyline, wearing a grey-blue knit "
               "sweater, turned three-quarters to the camera, gentle smile, flat overcast daylight")
    assert "hair" in missing_attributes(no_hair)
    assert "outfit" not in missing_attributes(no_hair)
    assert set(missing_attributes("")) == set(VARIABLE), "an empty caption names nothing"


def test_collect_reports_uncaptioned_images_rather_than_skipping_them(tmp_path: Path):
    """An uncaptioned image still trains. A dataset that was uncaptioned end to end
    once passed every caption check by silence, because they all sat behind `if caps`."""
    d = make_dataset(tmp_path, n=2, with_txt=False)
    ims = collect_images(d)
    assert len(ims) == 2
    assert all(im["uncaptioned"] and im["caption"] == "" for im in ims)


def test_build_preview_records_every_image_with_its_caption(tmp_path: Path):
    d = make_dataset(tmp_path, n=3)
    doc = build_preview(tmp_path / "root", d, trigger="jojo", measure=False)
    assert doc["n"] == 3 and len(doc["images"]) == 3
    assert all(im["caption"] == CAPTION for im in doc["images"])
    assert load_preview(tmp_path / "root", "ds")["fingerprint"] == doc["fingerprint"]
    assert [s["id"] for s in list_previews(tmp_path / "root")] == ["ds"]
    # the page never receives absolute paths
    assert "path" not in preview_payload(tmp_path / "root", "ds")["images"][0]
    assert image_path(tmp_path / "root", "ds", "face_000.png").is_file()
    assert image_path(tmp_path / "root", "ds", "../secret") is None


def test_editing_a_caption_revokes_approval(tmp_path: Path):
    """Approval is bound to the content, not the name.

    Verdicts keyed only by name survived three re-renders in the judge tool and
    scored the wrong pictures; approval must not repeat it.
    """
    root = tmp_path / "root"
    d = make_dataset(tmp_path, n=2)
    build_preview(root, d, measure=False)
    assert record_approval(root, "ds", True)["approved"]
    assert approval_state(root, "ds")["approved"]

    (d / "image_face" / "face_000.txt").write_text(CAPTION + " and a hat", encoding="utf-8")
    build_preview(root, d, measure=False)
    st = approval_state(root, "ds")
    assert st["stale"] and not st["approved"]

    # re-approving the new content clears it
    assert record_approval(root, "ds", True)["approved"]


def test_adding_an_image_revokes_approval(tmp_path: Path):
    root = tmp_path / "root"
    d = make_dataset(tmp_path, n=2)
    build_preview(root, d, measure=False)
    record_approval(root, "ds", True)

    p = d / "image_face" / "face_009.png"
    Image.new("RGB", (16, 16), "red").save(p)
    p.with_suffix(".txt").write_text(CAPTION, encoding="utf-8")
    build_preview(root, d, measure=False)
    assert not approval_state(root, "ds")["approved"]


def test_an_unknown_dataset_is_never_approved(tmp_path: Path):
    """Silence is not approval - the blocking check must fail closed."""
    st = approval_state(tmp_path / "root", "never-previewed")
    assert not st["approved"] and not st["stale"] and st["fingerprint"] is None
    with pytest.raises(KeyError):
        record_approval(tmp_path / "root", "never-previewed", True)


def test_rejecting_is_recorded_and_is_not_approval(tmp_path: Path):
    root = tmp_path / "root"
    build_preview(root, make_dataset(tmp_path, n=1), measure=False)
    record_approval(root, "ds", True)
    assert not record_approval(root, "ds", False)["approved"]
    assert json.loads((root / "approvals" / "ds.json").read_text())["approved"] is False


def test_fingerprint_ignores_ordering_but_not_content():
    a = [{"name": "b.png", "caption": "two", "sha": "22"},
         {"name": "a.png", "caption": "one", "sha": "11"}]
    b = list(reversed(a))
    assert fingerprint(a) == fingerprint(b)
    assert fingerprint(a) != fingerprint([{**a[0], "caption": "three"}, a[1]])


def test_router_serves_the_page_images_and_approval(tmp_path: Path):
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from sourcemode.train.preview import preview_router

    root = tmp_path / "root"
    build_preview(root, make_dataset(tmp_path, n=2), trigger="jojo", measure=False)
    cfg = {"train": {"previews": str(root)}}
    app = FastAPI()
    app.include_router(preview_router(cfg))
    c = TestClient(app)

    assert "training set" in c.get("/dataset").text
    assert c.get("/dataset/list").json()[0]["id"] == "ds"
    one = c.get("/dataset/ds").json()
    assert one["n"] == 2 and one["approval"]["approved"] is False
    assert c.get("/dataset/file", params={"ds": "ds", "name": "face_000.png"}).status_code == 200
    assert c.get("/dataset/file", params={"ds": "ds", "name": "nope.png"}).status_code == 404
    assert c.get("/dataset/missing").status_code == 404
    assert c.post("/dataset/ds/approve", json={"approved": True}).json()["approved"] is True
    assert c.get("/dataset/ds").json()["approval"]["approved"] is True
