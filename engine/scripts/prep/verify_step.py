"""Did a prep-chain step produce what it exists to produce? Exit 1 if not.

    python scripts/prep/verify_step.py <char> <step>

Steps: gather, gaze, captions, hair, preview, cull. Each check reads the files
the step is supposed to have written and compares them with the images that
are actually staged. A marker on an empty result is how a failed step used to
reach the Training sets tab: three trainings "done" in 37 s on a missing TOML,
Gabi with 33 uncaptioned images, Casey's recheck dead mid-run with the plan's
hair left on every ponytail and CASEYDONE written anyway. The chain now writes
DONE only after every step verifies.

Prints one line per finding; nothing else. No model is loaded.
"""
import json
import sys
from pathlib import Path

CHAR = sys.argv[1].lower()
STEP = sys.argv[2]
DS = Path(f"outputs/lora-datasets/{CHAR}_v2")
IMG = DS / "image_src"


def pngs() -> list[str]:
    return sorted(p.name for p in IMG.glob("src_*.png"))


def jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def gather() -> list[str]:
    names = pngs()
    if not names:
        return [f"nothing staged in {IMG}"]
    man = jload(DS / "manifest.json")
    if man is None:
        return ["manifest.json was not written"]
    listed = {m.get("file") for m in man}
    missing = [n for n in names if n not in listed]
    return [f"{len(missing)} staged images are not in manifest.json: {missing[:4]}"] if missing else []


def gaze() -> list[str]:
    g = jload(DS / "gaze_mp.json")
    if g is None:
        return ["gaze_mp.json was not written - captions would silently drop the gaze clause"]
    names = pngs()
    have = sum(1 for n in names if n in g)
    # MediaPipe finds no face in a few; under half measured means it did not run
    return [f"gaze measured for {have} of {len(names)} images"] if have < len(names) / 2 else []


def captions() -> list[str]:
    names = pngs()
    out = []
    empty, missing = [], []
    for n in names:
        t = IMG / (Path(n).stem + ".txt")
        if not t.is_file():
            missing.append(n)
        elif not t.read_text(encoding="utf-8").strip():
            empty.append(n)
    if missing:
        out.append(f"{len(missing)} of {len(names)} images have no caption: {missing[:4]}")
    if empty:
        out.append(f"{len(empty)} captions are empty: {empty[:4]}")
    return out


def hair() -> list[str]:
    """After the hair confirm + recheck: every caption names the hair, and the
    verdict file exists for the re-assemble to read."""
    out = captions()
    if out:
        return out
    if not (DS / "vl_hair_confirm.jsonl").is_file():
        out.append("vl_hair_confirm.jsonl was not written - the re-assemble would use the plan's hair")
    names = pngs()
    no_hair = [n for n in names
               if "her hair" not in (IMG / (Path(n).stem + ".txt")).read_text(encoding="utf-8")]
    # Gabi's first set reached training with 45 of 69 captions silent on hair.
    # A handful the VL could not read is fixed on the page; a tenth is a pass
    # that did not run.
    if len(no_hair) > max(2, len(names) // 10):
        out.append(f"{len(no_hair)} of {len(names)} captions never mention hair: {no_hair[:4]}")
    elif no_hair:
        print(f"VERIFY {STEP}: note - {len(no_hair)} captions do not mention hair: {no_hair}", flush=True)
    return out


def preview() -> list[str]:
    from sourcemode.config import load_config  # noqa: PLC0415
    from sourcemode.train.preview import load_preview, preview_root  # noqa: PLC0415

    doc = load_preview(preview_root(load_config()), f"{CHAR}_v2")
    if doc is None:
        return [f"no preview document for {CHAR}_v2"]
    names = pngs()
    shown = {im.get("name") for im in doc.get("images", [])}
    missing = [n for n in names if n not in shown]
    out = []
    if missing:
        out.append(f"{len(missing)} staged images are not on the page: {missing[:4]}")
    uncaptioned = [im.get("name") for im in doc.get("images", []) if not (im.get("caption") or "").strip()]
    if uncaptioned:
        out.append(f"{len(uncaptioned)} images on the page have no caption: {uncaptioned[:4]}")
    return out


def cull() -> list[str]:
    return [] if (DS / "hair_up_cull.json").is_file() else ["hair_up_cull.json was not written"]


CHECKS = {"gather": gather, "gaze": gaze, "captions": captions, "hair": hair,
          "preview": preview, "cull": cull}
if STEP not in CHECKS:
    raise SystemExit(f"unknown step {STEP!r}; one of {', '.join(CHECKS)}")
problems = CHECKS[STEP]()
for p in problems:
    print(f"VERIFY {STEP}: {p}", flush=True)
if not problems:
    print(f"VERIFY {STEP}: ok ({len(pngs())} images)", flush=True)
raise SystemExit(1 if problems else 0)
