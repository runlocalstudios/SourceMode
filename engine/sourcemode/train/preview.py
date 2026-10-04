"""Look at a training set before spending GPU time on it: every image beside the
caption that will be trained on it, on a phone.

Two datasets shipped with defects that were plainly visible in the captions and
that nobody looked at. 64% of gabi's captions never mentioned hair, so her hair
was absorbed into the trigger and the wardrobe pipeline spent the next month
fighting it. The gate scores a dataset in aggregate and said 1.0 for that set,
because "every caption is distinct and long enough" is true and useless here.

So this is not another scorer. It is the human read: the picture, the exact
string, and a note of which variable attributes the caption forgot to name.
Training does not start until the preview is approved, and approval is bound to
a fingerprint of the images and captions, so editing either revokes it.

    outputs/train-previews/previews/<id>.json    what was measured, per image
    outputs/train-previews/approvals/<id>.json   {approved, at, fingerprint}

    GET  /dataset                       the page
    GET  /dataset/list                  [{id, n, gate_passed, approved, stale}]
    GET  /dataset/<id>                  images + captions + gate findings
    GET  /dataset/file?ds=&name=        one image (paths come from the preview)
    POST /dataset/<id>/approve          {approved: bool}
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from ..monitor.ui import page

# What the asset pipeline varies per render. Anything it varies must be named in
# the caption or it is not variable - it becomes part of the identity instead.
# `hair` is first because omitting it is the mistake that actually cost us.
VARIABLE = {
    "hair": ("hair", "braid", "ponytail", "bun", "updo", "curls"),
    "outfit": ("wearing", "dress", "top", "shirt", "sweater", "jacket", "tee",
               "blouse", "coat", "tank", "cardigan", "hoodie", "suit"),
    "setting": ("in ", "on ", "against", "backdrop", "background", "studio"),
    "expression": ("smile", "smiling", "laughing", "neutral", "expression",
                   "grin", "lips", "mouth"),
    "angle": ("facing", "turned", "three-quarter", "profile", "over her shoulder",
              "from above", "from below", "looking"),
    "lighting": ("light", "lit", "daylight", "sunlight", "shade", "lamp", "overcast", "glow",
                 "dusk", "dawn", "neon", "candle", "firelight", "moonlight", "backlit",
                 "golden", "sunset", "sunrise", "shadow", "illuminat", "glare", "flash",
                 "evening", "morning", "afternoon", "night", "twilight", "ambient",
                 "noon", "midday", "sunny", "cloudy", "bright", "dim", "dark"),
}


# Descriptors of WHO SHE IS. Captioning these keeps them variable, which is the
# exact inverse of the coverage problem and just as damaging: the trigger never
# learns the trait. Matched as phrases, not bare words - "eyes closed" is a pose,
# "blue eyes" is identity.
IDENTITY_TERMS = {
    "hair colour or length": ("blonde", "brunette", "dark hair", "black hair", "red hair",
                              "auburn", "burgundy hair", "long hair", "short hair",
                              "long dark", "curly hair", "straight hair", "wavy hair",
                              "shoulder-length"),
    "eyes": ("blue eyes", "brown eyes", "green eyes", "hazel eyes", "dark eyes", "wide eyes"),
    "skin or features": ("freckles", "dimples", "beauty mark", "olive skin", "fair skin",
                         "pale skin", "tanned skin", "complexion"),
    "face shape": ("jawline", "cheekbones", "round face", "oval face", "high forehead",
                   "full lips", "thin lips", "button nose"),
    "age": ("year-old", "years old", "mid twenties", "in her twenties", "in her thirties"),
    "build": ("slim build", "curvy", "petite", "athletic build", "slender"),
}

# Closed vocabularies for the attributes we control the wording of. Used to spot an
# attribute that is named on every image and yet always says the same thing, which
# is absorbed into the trigger exactly as if it had never been named.
VALUE_VOCAB = {
    "hair": ("loose", "braid", "ponytail", "bun", "updo", "clipped", "tucked", "headband",
             "gathered", "twisted", "pinned"),
    "framing": ("tight head portrait", "head-and-shoulders", "head-and-chest", "waist-up",
                "thighs up", "full length", "close-up"),
    "angle": ("facing the camera", "turned slightly", "three-quarter", "almost to profile",
              "full profile", "over her shoulder", "from above", "from below"),
}

CONSTANT_SHARE = 0.60     # one value on more than this share is effectively constant
REPEATED_SHARE = 0.50     # a phrase on more than this share binds to the trigger
MIN_WORDS = 12            # below this a caption cannot name the six attributes at all


def _finding(check: str, passed: bool, detail: str, value=None) -> dict:
    return {"check": check, "passed": passed, "detail": detail, "value": value}


def caption_report(captions: list[str]) -> dict:
    """Every caption failure mode we have actually been bitten by. Pure.

    Coverage alone is not enough, which is why this exists alongside
    `missing_attributes`.

    Calibration, because I got this wrong once already. Coverage is standard
    practice and cheap, not something our data demonstrates. I claimed hair
    coverage explained our results, by absorption: uncaptioned hair binds to the
    trigger and later prompts fight it. gabi's training images are ~90% loose
    hair, so absorption predicts that prompting loose is the easy case. It is the
    hard one - 38% against a ponytail's 68%, controlled for framing, n=110 each.
    The prediction is backwards, so absorption is not the mechanism there. Most
    likely the ponytail simply leaves more of the face visible, which is the
    pixel-budget finding again.

    What survives, and matters more than coverage: an attribute must VARY IN THE
    IMAGES. Writing a word down does not make a constant variable. That is what
    the "attributes vary" check is for, and it is the check that would have caught
    gabi, whose 69 images are loose and down in about 65 of them.

    It would NOT have flagged jojo, and I wrongly said it should: her 99 images do
    carry ponytails, pigtails, buns, braids and updos matching their captions,
    because the shot plan asked for them. I had judged her set from the first 32
    files sorted by name. Build the sheet of all of it.
    """
    n = len(captions)
    low = [c.lower() for c in captions]
    out: list[dict] = []
    if not n:
        # `passed` must be present: the page reads `cr.passed` and renders a
        # missing key as FAIL, so a set with no images used to paint red for a
        # reason that had nothing to do with its captions.
        return {"n": 0, "passed": False, "failed": ["captions"], "coverage": {},
                "median_words": 0,
                "findings": [_finding("captions", False, "no captions at all")]}

    # 1. coverage: anything the render pipeline varies must be named
    coverage = {}
    for attr in VARIABLE:
        named = sum(1 for c in captions if attr not in missing_attributes(c))
        coverage[attr] = named / n
        out.append(_finding(
            f"names {attr}", coverage[attr] >= 0.9,
            f"{named}/{n} captions name {attr}"
            + ("" if coverage[attr] >= 0.9 else
               "; standard practice is that what is not captioned binds to the trigger"),
            round(coverage[attr], 3)))

    # 2. the inverse: identity traits must NOT be captioned
    leaks = []
    for cat, terms in IDENTITY_TERMS.items():
        hits = {t: sum(t in c for c in low) for t in terms}
        hits = {t: v for t, v in hits.items() if v}
        if hits:
            leaks.append({"category": cat, "terms": hits})
    out.append(_finding(
        "no identity in captions", not leaks,
        "clean" if not leaks else "; ".join(
            f"{l['category']}: " + ", ".join(f"{t!r} x{v}" for t, v in l["terms"].items())
            for l in leaks) + " - captioned traits stay variable and are never learned",
        leaks))

    # 3. named but constant
    constants = []
    for attr, vocab in VALUE_VOCAB.items():
        counts = {w: sum(w in c for c in low) for w in vocab}
        counts = {w: v for w, v in counts.items() if v}
        if counts:
            top, cnt = max(counts.items(), key=lambda kv: kv[1])
            if cnt / n > CONSTANT_SHARE:
                constants.append({"attr": attr, "value": top, "share": round(cnt / n, 3)})
    out.append(_finding(
        "attributes vary", not constants,
        "each named attribute takes several values" if not constants else "; ".join(
            f"{c['attr']} is {c['value']!r} on {c['share']:.0%} - named but effectively constant"
            for c in constants),
        constants))

    # 4. a phrase on most captions binds to the trigger
    grams: dict[str, int] = {}
    for c in low:
        w = "".join(ch if ch.isalpha() or ch == " " else " " for ch in c).split()
        for k in (4, 5):
            for i in range(len(w) - k + 1):
                g = " ".join(w[i:i + k])
                grams[g] = grams.get(g, 0) + 1
    repeated = sorted(((g, v) for g, v in grams.items() if v / n > REPEATED_SHARE),
                      key=lambda kv: -kv[1])[:5]
    out.append(_finding(
        "no boilerplate phrase", not repeated,
        "no phrase on a majority of captions" if not repeated else "; ".join(
            f"{g!r} on {v / n:.0%}" for g, v in repeated),
        [{"phrase": g, "share": round(v / n, 3)} for g, v in repeated]))

    # There was a fifth check here, asserting that phrases used at render time must
    # appear in the training captions. It was wrong and it is gone. Jeremy asked the
    # obvious question - Qwen already knows what "from the thighs up" means - and the
    # renders settle it: asked for full length, the model produced full length with
    # the feet in frame and the face at 12% of frame width; asked for thighs up, 19%.
    # The instruction was understood and obeyed both times.
    # Nor is it distribution shift. gabi's training crops span 2.2-2.7x face width,
    # so BOTH render framings sit outside them, yet thighs-up keeps 52% and full
    # length keeps 12%. What separates them is the 122px face against the 229px one.
    # Caption coverage still matters for attributes ON the subject - her hair was
    # absorbed and prompting against it costs real keep rate - but composition is
    # not that, and a check without a mechanism is worse than no check.

    # 5. length
    words = sorted(len(c.split()) for c in captions)
    short = sum(1 for w in words if w < MIN_WORDS)
    out.append(_finding(
        "captions long enough", short == 0,
        f"median {words[n // 2]} words, shortest {words[0]}"
        + ("" if short == 0 else f"; {short} under {MIN_WORDS} words cannot name the attributes"),
        words[n // 2]))

    failed = [f["check"] for f in out if not f["passed"]]
    return {"n": n, "findings": out, "coverage": coverage, "passed": not failed,
            "failed": failed, "median_words": words[n // 2]}


def preview_root(cfg: dict) -> Path:
    from ..config import ENGINE_ROOT  # noqa: PLC0415

    root = Path(cfg.get("train", {}).get("previews", "outputs/train-previews"))
    return root if root.is_absolute() else ENGINE_ROOT / root


def missing_attributes(caption: str) -> list[str]:
    """Which variable attributes this caption never names.

    Deliberately a keyword test, not a model: it has to be obvious why a caption
    was flagged, and a flag is a prompt to look, not a verdict.
    """
    low = caption.lower()
    return [k for k, words in VARIABLE.items() if not any(w in low for w in words)]


# --- close calls -------------------------------------------------------------
# Jeremy's ask: "only really review the captions carefully if something is weird
# about a picture or a pose". Every clause in a caption comes from a detector that
# made a call; most calls are not close. These margins mark the ones that are, so
# a 73-image set reads as a handful of rows instead of 73.
#
# The margins are the detector's own threshold plus a band either side. A flag is
# a prompt to look, never a verdict - the same contract as missing_attributes.
GAZE_THRESHOLD, GAZE_MARGIN = 0.85, 0.25   # gaze_mp.py residual
JAW_THRESHOLD, JAW_MARGIN = 0.10, 0.04     # MediaPipe jawOpen
FACE_FLOOR_PX = 300                        # genmedia hard rule 2
# Below this a face is too small to train on at all - such images are excluded
# at gather time rather than flagged for review.
FACE_DROP_PX = 250

AMBIGUOUS_HAIR = {"halfup"}


def read_signals(dataset_dir: Path) -> dict[str, dict]:
    """Per-image detector output the captioner left beside the dataset.

    Absent files are not an error: older sets predate a detector, and a set with
    no signals simply has no close calls to report.
    """
    dataset_dir = Path(dataset_dir)
    sig: dict[str, dict] = {}

    gz = dataset_dir / "gaze_mp.json"
    if gz.is_file():
        try:
            raw = json.loads(gz.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        for name, v in raw.items():
            # early runs wrote a bare residual; later runs write the full record
            rec = v if isinstance(v, dict) else {"resid": v}
            sig.setdefault(name, {}).update(
                {"resid": rec.get("resid"), "jaw": rec.get("jaw")})

    # Provenance: a Lora-Gen image traces back to a <char>_shot_NNN file recorded
    # at gather time. Anything else is hand-collected and gets flagged for review.
    mf = dataset_dir / "manifest.json"
    if mf.is_file():
        try:
            rows = json.loads(mf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rows = []
        for r in rows:
            name = r.get("file")
            if not name:
                continue
            origin = Path(str(r.get("original", ""))).name
            if not re.search(r"_shot_\d+", origin, re.I):
                sig.setdefault(name, {})["no_plan"] = True

    coarse: dict[str, str] = {}
    vh = dataset_dir / "vl_hair.jsonl"
    if vh.is_file():
        for line in vh.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                coarse[Path(r["image_path"]).name] = re.sub(r"[^a-z]", "", r["caption"].lower())
    confirmed: dict[str, str] = {}
    vc = dataset_dir / "vl_hair_confirm.jsonl"
    if vc.is_file():
        try:
            confirmed = json.loads(vc.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            confirmed = {}
    for name, label in coarse.items():
        sig.setdefault(name, {})["hair"] = confirmed.get(name, label)
        sig[name]["hair_confirmed"] = name in confirmed

    # the shot plan and the VL read the hair differently on these; the plan's wording
    # was written, but the pair is worth an eye
    pc = dataset_dir / "plan_conflict.json"
    if pc.is_file():
        try:
            for name in json.loads(pc.read_text(encoding="utf-8")):
                sig.setdefault(name, {})["plan_conflict"] = True
        except (OSError, ValueError):
            pass
    return sig


def close_calls(im: dict, sig: dict) -> list[str]:
    """Short reasons this image's caption is worth reading. Empty is the good case.

    Jeremy, 2026-09-23, naming the whole list: gaze he is unsure of, small faces,
    and anything that did not come from a Lora-Gen run. The hair flags and the
    mouth flag are gone with his say-so - the plan's wording agrees with the photo
    closely enough that he stopped correcting it, and a flag he always dismisses
    costs more attention than it saves.
    """
    out = []
    resid = sig.get("resid")
    if resid is not None and abs(abs(resid) - GAZE_THRESHOLD) <= GAZE_MARGIN:
        out.append("gaze?")
    # Jeremy, 2026-09-29: a small face is no longer a summons. Anything between
    # FACE_DROP_PX and FACE_FLOOR_PX is simply trained on; anything BELOW
    # FACE_DROP_PX never reaches the set at all, so it needs no flag either.
    # Across the six live sets a 250px cut drops 0-6 images each (cindy 0, maddie 2,
    # bianca 2, geena 4, ash 6, trina 6) - small enough not to dent a set.
    px = im.get("face_px")
    if px is not None and px < FACE_DROP_PX:
        out.append(f"face {px}px - TOO SMALL, drop")
    # Hand-collected photos predate the shot plan and are not held to its framing,
    # lighting or resolution, so they are the ones worth a second look.
    if sig.get("no_plan"):
        out.append("not lora-gen")
    return out


def needs_look(im: dict) -> bool:
    """The short list. Missing attributes are chips, not a summons - they fire on
    most of a set and would make the filter useless."""
    return bool(im.get("uncaptioned") or im.get("uncertain"))


def fingerprint(images: list[dict]) -> str:
    """Identity of exactly this set of pictures and strings.

    Approval is bound to it so that editing a caption, swapping an image or adding
    one silently revokes approval rather than carrying it forward. The judge tool
    learned this the expensive way: verdicts keyed only by name survived three
    re-renders and scored the wrong pictures.
    """
    h = hashlib.sha1(usedforsecurity=False)
    for im in sorted(images, key=lambda x: x["name"]):
        h.update(im["name"].encode("utf-8"))
        h.update(b"\0")
        h.update(im["caption"].encode("utf-8"))
        h.update(b"\0")
        h.update((im.get("sha") or "").encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()[:16]


def _sha(path: Path) -> str | None:
    try:
        h = hashlib.sha1(usedforsecurity=False)
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except OSError:
        return None


def collect_images(dataset_dir: Path) -> list[dict]:
    """Every trainable image in a musubi dataset dir, with its caption.

    A missing or empty .txt is reported rather than skipped - an uncaptioned image
    still trains, and a dataset that was uncaptioned end to end once passed every
    caption check by silence.
    """
    dataset_dir = Path(dataset_dir)
    dirs = [d for d in sorted(dataset_dir.iterdir()) if d.is_dir() and d.name.startswith("image")]
    if not dirs:
        dirs = [dataset_dir]
    out = []
    for d in dirs:
        for p in sorted(d.iterdir()):
            if p.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            txt = p.with_suffix(".txt")
            caption = txt.read_text(encoding="utf-8").strip() if txt.is_file() else ""
            out.append({"name": p.name, "path": str(p), "caption": caption,
                        "sha": _sha(p), "missing": missing_attributes(caption),
                        "uncaptioned": not caption})
    return out


def build_preview(root: Path, dataset_dir: Path, *, dataset_id: str | None = None,
                  trigger: str = "", render_size: tuple[int, int] | None = None,
                  measure: bool = True, bucket_px: int = 1024) -> dict:
    """Measure the set and write the preview. `measure=False` skips InsightFace."""
    dataset_dir = Path(dataset_dir)
    ds_id = dataset_id or dataset_dir.name
    images = collect_images(dataset_dir)

    gate: dict = {}
    if measure:
        from ..gates.dataset import evaluate, measure_dataset  # noqa: PLC0415

        m = measure_dataset(dataset_dir, render_size=render_size, bucket_px=bucket_px)
        gate = evaluate(m, trigger=trigger)
        px = {f.name: (f.face_px, f.yaw_deg) for f in m.faces}
        for im in images:
            if im["name"] in px:
                im["face_px"], im["yaw_deg"] = int(px[im["name"]][0]), round(float(px[im["name"]][1]), 1)

    sig = read_signals(dataset_dir)
    for im in images:
        im["uncertain"] = close_calls(im, sig.get(im["name"], {}))

    captions = caption_report([im["caption"] for im in images])
    prior = load_preview(root, ds_id) or {}
    still_out = [im for im in prior.get("excluded", []) if Path(im["path"]).is_file()]
    doc = {
        "id": ds_id,
        "captions": captions,
        "excluded": still_out,
        "dataset_dir": str(dataset_dir),
        "trigger": trigger,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n": len(images),
        "gate": gate,
        "images": images,
        "fingerprint": fingerprint(images),
    }
    d = root / "previews"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{ds_id}.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return doc


def load_preview(root: Path, ds_id: str) -> dict | None:
    if not ds_id or "/" in ds_id or "\\" in ds_id or ds_id.startswith("."):
        return None
    p = root / "previews" / f"{ds_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def approval_state(root: Path, ds_id: str) -> dict:
    """Approved, and still approved for THIS content.

    `stale` means the images or captions changed after approval, which counts as
    not approved. Silence is never approval: a dataset with no record at all is
    reported the same as a rejected one.
    """
    doc = load_preview(root, ds_id)
    p = root / "approvals" / f"{ds_id}.json"
    rec = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    fp = doc["fingerprint"] if doc else None
    stale = bool(rec.get("approved")) and rec.get("fingerprint") != fp
    return {"approved": bool(rec.get("approved")) and not stale,
            "at": rec.get("at"), "stale": stale,
            "approved_fingerprint": rec.get("fingerprint"), "fingerprint": fp}


def record_approval(root: Path, ds_id: str, approved: bool) -> dict:
    doc = load_preview(root, ds_id)
    if doc is None:
        raise KeyError(ds_id)
    d = root / "approvals"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{ds_id}.json").write_text(json.dumps({
        "approved": bool(approved),
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fingerprint": doc["fingerprint"],
    }, indent=1), encoding="utf-8")
    return approval_state(root, ds_id)


def exclude_image(root: Path, ds_id: str, name: str, excluded: bool) -> dict:
    """Take one image out of the training set, or put it back. Nothing is deleted.

    The image and its caption move to `<dataset>/_excluded/`, a sibling of the
    folder the trainer reads, so the trainer cannot see it and Jeremy can undo it.
    The preview keeps the entry with its measurements so undo needs no re-measure.
    The fingerprint is recomputed over the remaining images, which is what makes
    a prior approval lapse: a set that has lost a photo is a different set.
    """
    doc = load_preview(root, ds_id)
    if doc is None:
        raise KeyError(ds_id)
    pool = doc["images"] + doc.get("excluded", [])
    entry = next((im for im in pool if im["name"] == name), None)
    if entry is None:
        raise KeyError(name)
    log_edit(root, ds_id, name, entry.get("caption", ""), "",
             kind="excluded" if excluded else "restored")
    ds_dir = Path(doc["dataset_dir"])
    src = Path(entry["path"])
    img_dir = src.parent if src.parent.name != "_excluded" else Path(entry["home"])
    exc_dir = ds_dir / "_excluded"
    if excluded:
        exc_dir.mkdir(parents=True, exist_ok=True)
        dest_dir, entry["home"] = exc_dir, str(img_dir)
    else:
        dest_dir = Path(entry.get("home", img_dir))
    for ext in (src.suffix, ".txt"):
        f = src.with_suffix(ext)
        if f.is_file():
            f.replace(dest_dir / f.name)
    entry["path"] = str(dest_dir / src.name)
    doc["images"] = [im for im in pool if im is not entry and im.get("_state") != "excluded"]
    doc["excluded"] = [im for im in pool if im is not entry and im.get("_state") == "excluded"]
    entry["_state"] = "excluded" if excluded else "kept"
    (doc["excluded"] if excluded else doc["images"]).append(entry)
    doc["images"].sort(key=lambda im: im["name"]); doc["excluded"].sort(key=lambda im: im["name"])
    doc["n"] = len(doc["images"])
    doc["fingerprint"] = fingerprint(doc["images"])
    doc["captions"] = caption_report([im["caption"] for im in doc["images"]])
    (root / "previews" / f"{ds_id}.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return {"name": name, "excluded": excluded, "n": doc["n"], "n_excluded": len(doc["excluded"]),
            "fingerprint": doc["fingerprint"], "approval": approval_state(root, ds_id)}


# --- what Jeremy actually has to correct -------------------------------------
# His rule, 2026-09-22: "any time that I have to change anything more than twice on
# a training set, you follow up to figure out how to fix it in an automated fashion.
# If it's just something that I have to fix once or twice, that may not rise to
# needing to be fixed." So every edit is logged with WHICH CLAUSE changed, and the
# report counts by clause so a systematic error separates itself from a one-off.
CLAUSE_PATTERNS = (
    ("hair", ("her hair",)),
    ("outfit", ("wearing", "nothing visible")),
    ("gaze", ("looking off camera", "looking at the camera", "looking away")),
    ("expression", ("smile", "expression", "mid-speech", "lips", "laughing", "smirk",
                    "teeth", "mouth")),
    ("framing", ("portrait", "waist-up", "head-and", "close-up", "tight head")),
    ("angle", ("facing the camera", "turned", "three-quarter", "profile", "shot from")),
    # One list, not two: "warm sunset glow" was called "no lighting" by the chip
    # check because glow was in neither (Jeremy, 2026-10-03).
    # Setting BEFORE lighting now that time-of-day words count as lighting: "in a
    # night club with neon lights" is a setting, and reversing these two would call
    # it lighting. A clause that opens with a preposition is a place, not a light.
    ("setting", ("in a ", "in the ", "on a ", "on the ", "at a ", "at the ",
                 "against", "backdrop")),
    ("lighting", VARIABLE["lighting"]),
)
EDITS = "caption_edits.jsonl"


def classify_clause(text: str) -> str:
    """Which part of the caption a phrase is. First match wins, so the order above
    matters: 'her hair' before anything that merely mentions light or a setting."""
    low = text.lower()
    for kind, words in CLAUSE_PATTERNS:
        if any(w in low for w in words):
            return kind
    return "other"


def diff_clauses(before: str, after: str) -> list[dict]:
    """The comma-separated phrases that changed, tagged by clause type.

    Captions are assembled as comma-separated clauses, so a set difference over the
    phrases isolates the edit without needing a real diff algorithm.
    """
    b = [x.strip() for x in before.split(",") if x.strip()]
    a = [x.strip() for x in after.split(",") if x.strip()]
    removed, added = [x for x in b if x not in a], [x for x in a if x not in b]
    out = []
    for kind in dict.fromkeys([classify_clause(x) for x in removed + added]):
        out.append({"clause": kind,
                    "from": next((x for x in removed if classify_clause(x) == kind), None),
                    "to": next((x for x in added if classify_clause(x) == kind), None)})
    return out


def log_edit(root: Path, ds_id: str, name: str, before: str, after: str, kind: str = "caption") -> None:
    """Append one edit. Never raises: a logging failure must not lose his correction."""
    try:
        rec = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "dataset": ds_id, "image": name, "kind": kind,
               "before": before, "after": after,
               "clauses": diff_clauses(before, after) if kind == "caption" else []}
        with (root / EDITS).open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + chr(10))
    except OSError:
        pass


def edit_report(root: Path, ds_id: str | None = None) -> dict:
    """Counts per dataset and clause, and what crossed the follow-up threshold.

    Three or more corrections of the same clause in one set is a systematic error in
    the captioner, not a one-off - that is the line Jeremy drew.
    """
    rows = []
    f = root / EDITS
    if f.is_file():
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    if ds_id:
        rows = [r for r in rows if r["dataset"] == ds_id]
    by: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        # Only CAPTION edits have clauses. An exclusion or a restore has none,
        # and bucketing it under its `kind` invented pseudo-clauses ("excluded",
        # "restored") that outnumbered every real clause and buried the "three
        # of the same clause is systematic" signal this report exists to find.
        if r.get("kind", "caption") != "caption":
            continue
        for c in r.get("clauses") or [{"clause": "other"}]:
            by.setdefault((r["dataset"], c["clause"]), []).append(r)
    counts = [{"dataset": d, "clause": c, "n": len(v),
               "images": sorted({x["image"] for x in v}),
               "examples": [{"from": e.get("from"), "to": e.get("to")}
                            for x in v[:3] for e in (x.get("clauses") or [])
                            if e.get("clause") == c][:3]}
              for (d, c), v in by.items()]
    counts.sort(key=lambda x: -x["n"])
    return {"total_edits": len(rows), "by_clause": counts,
            "needs_automation": [c for c in counts if c["n"] >= 3]}


def set_caption(root: Path, ds_id: str, name: str, caption: str) -> dict:
    """Correct one image's caption from the preview. Writes the training file.

    This is Jeremy's quick-feedback path: "maya src_025 - her hair is in low
    pigtails, not loose". The .txt beside the image is the thing the trainer reads,
    so that is what changes; the preview entry, its attribute chips, the caption
    report and the fingerprint follow, and approval lapses until he re-approves,
    because a set whose captions changed is a different set.
    """
    doc = load_preview(root, ds_id)
    if doc is None:
        raise KeyError(ds_id)
    pool = doc["images"] + doc.get("excluded", [])
    entry = next((im for im in pool if im["name"] == name), None)
    if entry is None:
        raise KeyError(name)
    caption = " ".join(str(caption).split())
    before = entry.get("caption", "")
    if caption != before:
        log_edit(root, ds_id, name, before, caption)
    Path(entry["path"]).with_suffix(".txt").write_text(caption, encoding="utf-8")
    entry["caption"] = caption
    entry["missing"] = missing_attributes(caption)
    entry["uncaptioned"] = not caption
    doc["fingerprint"] = fingerprint(doc["images"])
    doc["captions"] = caption_report([im["caption"] for im in doc["images"]])
    (root / "previews" / f"{ds_id}.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return {"name": name, "caption": caption, "missing": entry["missing"],
            "uncertain": entry.get("uncertain", []), "uncaptioned": entry["uncaptioned"],
            "fingerprint": doc["fingerprint"], "captions": doc["captions"], "approval": approval_state(root, ds_id)}


def with_clause(caption: str, clause: str,
                after: tuple[str, ...] = ("her hair",)) -> str:
    """Insert one generated clause where the captioner would have put it.

    This is the page's old `addGaze()` rule moved server-side verbatim: before
    the first clause matching `^her hair`, else at `min(2, len(parts))` - after
    the trigger and the framing clause. One implementation, unit-testable, and
    the page stops holding product logic. Idempotent.

    The inserted clause is classified "gaze" by CLAUSE_PATTERNS, so a quick fix
    lands in edit_report()'s per-clause counts and will trip needs_automation at
    three. The quick fix self-reports, which is the point.
    """
    parts = [x.strip() for x in caption.split(",") if x.strip()]
    if clause in parts:
        return caption
    at = next((i for i, x in enumerate(parts)
               if any(x.lower().startswith(a) for a in after)), None)
    parts.insert(at if at is not None else min(2, len(parts)), clause)
    return ", ".join(parts)


def fix_rows(root: Path, ds_id: str) -> dict:
    """The short list: only rows with something to DO, each with its suggestion.

    Not a new judgement - exactly the rows `needs_look()` already returns
    (uncaptioned, or carrying a close call), ordered worst first, with the one
    correction that fits where there is one. A flag is still a prompt to look:
    nothing here edits anything, and nothing here blocks approval.
    """
    doc = load_preview(root, ds_id) or {}
    rows = []
    for im in doc.get("images", []):
        if not needs_look(im):
            continue
        reasons = (["NO CAPTION"] if im.get("uncaptioned") else []) \
            + list(im.get("uncertain") or [])
        cap = im.get("caption") or ""
        sug = None
        if "gaze?" in reasons and "looking off camera" not in cap:
            sug = {"kind": "off_cam",
                   "caption": with_clause(cap, "looking off camera")}
        rows.append({"name": im["name"], "reasons": reasons, "caption": cap,
                     "suggestion": sug})
    rows.sort(key=lambda r: (0 if "NO CAPTION" in r["reasons"] else 1, r["name"]))
    by: dict[str, int] = {}
    for r in rows:
        for x in r["reasons"]:
            by[x] = by.get(x, 0) + 1
    return {"n": doc.get("n", 0), "rows": rows,
            "by_reason": [{"reason": k, "n": v,
                           "bulk": "off_cam" if k == "gaze?" else None}
                          for k, v in sorted(by.items(), key=lambda kv: -kv[1])]}


def set_captions(root: Path, ds_id: str, edits: list[dict]) -> dict:
    """Several captions in one request, each logged as its own edit.

    One request so the fingerprint is recomputed once and the page gets one
    answer; separate log entries so edit_report()'s "three of the same clause is
    systematic" threshold still counts what actually happened.
    """
    out, failed = [], []
    for e in edits:
        try:
            out.append(set_caption(root, ds_id, str(e["name"]), str(e.get("caption", ""))))
        except KeyError:
            failed.append(e.get("name"))
    return {"n_written": len(out), "rows": out, "failed": failed,
            "captions": (load_preview(root, ds_id) or {}).get("captions"),
            "approval": approval_state(root, ds_id)}


def approval_record(root: Path, ds_id: str) -> dict:
    """Approval as a record, with the reason it lapsed if it did.

    The fingerprint binding already works and is already invisible: the page said
    "approval STALE - set changed since" and nothing about WHAT changed, so the
    only way to find out was to re-read 104 captions. Everything here is derived
    from the edit log that `log_edit()` has been writing all along - no new file,
    no migration.
    """
    st = approval_state(root, ds_id)
    since = []
    if st.get("at"):
        mine = []
        f = root / EDITS
        if f.is_file():
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("dataset") == ds_id and rec.get("at"):
                    mine.append(rec)

        # Both the approval and every edit are stamped to the SECOND, so an edit
        # recorded in the same second as the approval cannot be ordered against
        # it. Which way to resolve that depends on what the fingerprint says:
        #
        #   stale    something definitely changed, and a same-second edit is the
        #            likeliest cause, so include it (>=) rather than report
        #            "lapsed, 0 changes" - which explains nothing.
        #   current  the fingerprint matches, so a same-second edit either
        #            predates the approval or was reverted. Excluding it (>)
        #            keeps an approved set from listing phantom changes.
        after = (lambda a: a >= st["at"]) if st["stale"] else (lambda a: a > st["at"])
        for rec in mine:
            if not after(rec["at"]):
                continue
            since.append({"at": rec["at"], "image": rec.get("image"),
                          "kind": rec.get("kind", "caption"),
                          "clauses": [c.get("clause") for c in (rec.get("clauses") or [])]})
    kinds: dict[str, int] = {}
    for e in since:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    return {**st, "since": since, "n_since": len(since), "since_by_kind": kinds}


def list_previews(root: Path) -> list[dict]:
    """Unapproved first: those are the ones blocking a training run."""
    out = []
    d = root / "previews"
    for p in sorted(d.glob("*.json")) if d.exists() else []:
        doc = json.loads(p.read_text(encoding="utf-8"))
        st = approval_state(root, doc["id"])
        flagged = sum(1 for im in doc["images"] if needs_look(im))
        # `sub`/`status`/`group` are what the one picker shows, in the same shape
        # the judging list uses, so the two tabs read alike.
        if st["stale"]:
            status, group = "you", "needs"
            sub = f"{doc['n']} images · approval lapsed"
        elif st["approved"]:
            status, group = "done", "done"
            sub = f"{doc['n']} images · approved"
        else:
            status, group = "you", "needs"
            sub = f"{doc['n']} images" + (f" · {flagged} need a look" if flagged else "")
        out.append({"id": doc["id"], "n": doc["n"], "built_at": doc["built_at"],
                    "gate_passed": bool(doc.get("gate", {}).get("passed")),
                    "caption_failed": doc.get("captions", {}).get("failed", []),
                    "flagged": flagged, "done": bool(st["approved"]),
                    "sub": sub, "status": status, "group": group, **st})
    return sorted(out, key=lambda s: (s["approved"], s["id"]))


def _appearance_for(ds_id: str) -> dict:
    """Her appearance record's pre-flight, keyed by character - `marisol_v2`
    is marisol. Never raises: a badly shaped record must not take the page down."""
    import re as _re  # noqa: PLC0415

    try:
        from ..assets.appearance import check  # noqa: PLC0415

        return check(_re.sub(r"_v\d+$", "", ds_id))
    except Exception as exc:  # noqa: BLE001
        return {"ok": True, "missing": [], "warnings": [f"could not check: {exc}"],
                "has_record": False}


def preview_payload(root: Path, ds_id: str) -> dict | None:
    doc = load_preview(root, ds_id)
    if doc is None:
        return None
    strip = lambda ims: [{k: v for k, v in im.items() if k not in ("path", "home")} for im in ims]
    return {**doc, "approval": approval_record(root, ds_id),
            "appearance": _appearance_for(ds_id),
            "images": strip(doc["images"]), "excluded": strip(doc.get("excluded", []))}


# --- phone-sized delivery ----------------------------------------------------
# Renders stay 1024x1536; only what goes down the wire shrinks. Face pixels at
# GENERATION are what drive identity, so the images themselves are untouched.
_WEB_MAX = 900


def web_copy(src: "Path", w: int = _WEB_MAX) -> "Path":
    """A JPEG no wider than `w` on its long edge, cached beside the original.

    Falls back to the original on any failure - a review page that shows nothing
    is worse than one that is slow.
    """
    from pathlib import Path as _P  # noqa: PLC0415
    src = _P(src)
    if w <= 0:
        return src
    try:
        from PIL import Image  # noqa: PLC0415
        cache = src.parent / "_web" / f"{src.stem}_{w}.jpg"
        if cache.is_file() and cache.stat().st_mtime >= src.stat().st_mtime:
            return cache
        im = Image.open(src)
        if max(im.size) <= w and src.suffix.lower() in (".jpg", ".jpeg"):
            return src
        im = im.convert("RGB")
        im.thumbnail((w, w), Image.LANCZOS)
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(".tmp")
        im.save(tmp, "JPEG", quality=82, optimize=True)
        tmp.replace(cache)
        return cache
    except Exception:
        return src


def image_path(root: Path, ds_id: str, name: str) -> Path | None:
    doc = load_preview(root, ds_id)
    if doc is None:
        return None
    for im in doc["images"] + doc.get("excluded", []):
        if im["name"] == name:
            p = Path(im["path"])
            return p if p.is_file() else None
    return None


OWN_CSS = r"""
/* One image + one caption, side by side on a monitor, stacked on a phone. */
#head{position:sticky;top:0;z-index:10;background:var(--g0);
  padding:var(--s3) 0 var(--s2);border-bottom:1px solid var(--g3)}
.drow{display:flex;gap:var(--s4);padding:var(--s4) 0;
  border-bottom:1px solid var(--g3);align-items:flex-start}
.drow>img{flex:none;width:min(42vw,320px);border-radius:var(--r1);
  background:var(--photo);cursor:zoom-in}
.drow .cap{flex:1;min-width:0}
.drow.out{opacity:.4}
.drow.hide{display:none}
.drow .rowtop{display:flex;gap:var(--s2);align-items:flex-start}
.drow .rowtop .cap-box{flex:1}
.drow .meta{font:var(--t-small);color:var(--g6);margin-top:var(--s2);
  font-family:var(--mono)}
.drow.focusrow{box-shadow:0 0 0 2px var(--you) inset;border-radius:var(--r1)}
#bottom{height:calc(var(--tap) + var(--s5))}
@media (max-width:820px){
  .drow{flex-direction:column}
  .drow>img{width:100%;max-height:58vh;object-fit:contain}
}
"""

BODY = """
<div class=wrap id=app>
  <div class=col-main>
    <div id=head>
      <button class=picker id=pick aria-haspopup=dialog>
        <span class=picker-txt><div id=setname>loading&hellip;</div>
        <div class=sub id=setsub></div></span>
        <span class=chev aria-hidden=true>&#9662;</span></button>
      <div id=facts></div>
    </div>
    <div id=approval></div>
    <details class=report id=report><summary>report</summary><div id=repbody></div></details>
    <div id=list></div>
    <div id=bottom></div>
  </div>
  <div class=col-rail id=rail></div>
</div>
<div id=bars></div>
"""

OWN_JS = r"""
const $=id=>document.getElementById(id);
/* `set` is the loaded dataset. It is NOT called `cur`: a local `const cur` in the
   caption editor used to shadow the module-level one, so saving a caption wrote
   properties onto a string and the header rendered "undefined in set". */
let set=null, sets=[], fix=null, pos=null, onlyLook=false, fixAt=-1;
try{ onlyLook=localStorage.getItem('onlyLook')==='1'; }catch(e){}

const fileUrl=(ds,name)=>'/dataset/file?ds='+encodeURIComponent(ds)
  +'&name='+encodeURIComponent(name);
const rowOf=name=>document.querySelector('.drow[data-name="'+CSS.escape(name)+'"]');

async function loadList(){
  try{ sets=await SM.getJSON('/dataset/list'); }
  catch(e){ return fail('Could not load the training sets',e.message); }
  const hashed=location.hash.slice(1);
  const known=hashed?sets.find(s=>s.id===hashed):null;
  /* A hash pointing at a set that no longer exists used to render a blank page
     forever: open() took FastAPI's 404 body as the payload and threw on
     `set.images`. The judge page fixed exactly this and recorded it; this page
     never got the fix. */
  if(hashed&&!known) return gone(hashed,(sets[0]||{}).id);
  const want=known?hashed:(sets[0]||{}).id;
  if(!want) return fail('No training sets','Build a preview first.');
  await open(want);
}
function openPicker(){
  SM.sheet({title:'Training set',current:set&&set.id,
    items:sets.map(s=>({id:s.id,title:s.id,sub:s.sub,status:s.status,group:s.group,
      progress:null})),
    onPick:id=>open(id).catch(e=>SM.toast(e.message))});
}
$('pick').onclick=openPicker;

async function open(id){
  const r=await fetch('/dataset/'+encodeURIComponent(id),{cache:'no-store'});
  if(!r.ok) throw new Error('HTTP '+r.status);
  set=await r.json();
  if(location.hash.slice(1)!==id) history.replaceState(null,'','#'+id);
  exitFix();
  await Promise.all([refreshFix(),refreshPos()]);
  renderAll();
}
const refreshFix=()=>SM.getJSON('/dataset/'+encodeURIComponent(set.id)+'/fixlist')
  .then(d=>{fix=d;}).catch(()=>{fix=null;});
const refreshPos=()=>SM.getJSON('/queue/position?dataset='+encodeURIComponent(set.id))
  .then(d=>{pos=d;}).catch(()=>{pos=null;});

function renderAll(){ header(); rows(); bar(); }

/* --- header: facts that are also filters -------------------------------- */
function header(){
  $('setname').textContent=set.id;
  const a=set.approval||{};
  $('setsub').textContent=set.n+' images'
    +(a.approved?' · approved':(a.stale?' · approval lapsed':' · not approved'));
  const g=set.gate||{}, cr=set.captions||{};
  const nLook=fix?fix.rows.length:0;
  const nOut=(set.excluded||[]).length;
  let h='<div class=facts>'
    +'<span class="fact inert"><b>'+set.n+'</b> in set</span>'
    +(nLook?'<button class="fact flag'+(onlyLook?' on':'')+'" data-act=onlylook>'
       +'<b>'+nLook+'</b> need you</button>':'')
    +'<span class="fact inert">gate '+(g.passed?'pass':'<b>FAIL</b>')+'</span>'
    +'<span class="fact inert">captions '+(cr.passed?'pass'
       :'<b>FAIL</b> ('+((cr.failed||[]).length)+')')+'</span>'
    +(nOut?'<span class="fact inert"><b>'+nOut+'</b> removed</span>':'')
    +(nLook?'<button class="fact" data-act=startfix>Fix '+nLook+' rows &rarr;</button>':'')
    +'</div>';
  SM.set($('facts'),null,h);
  /* the report */
  let rep='<div class=findings>';
  for(const f of (g.findings||[])) if(!f.passed)
    rep+='<div class="finding fail"><span class=mark>&#10007;</span><span>'
      +SM.esc(f.check)+': '+SM.esc(f.detail)+'</span></div>';
  for(const f of (cr.findings||[]))
    rep+='<div class="finding '+(f.passed?'pass':'fail')+'"><span class=mark>'
      +(f.passed?'&#10003;':'&#10007;')+'</span><span>'+SM.esc(f.check)+': '
      +SM.esc(f.detail)+'</span></div>';
  rep+='</div><div class=basis>A gate annotates. Nothing here blocks approval.</div>';
  SM.set($('repbody'),null,rep);
  const bad=(g.findings||[]).filter(f=>!f.passed).length
           +(cr.findings||[]).filter(f=>!f.passed).length;
  $('report').querySelector('summary').textContent=
    bad?(bad+' finding'+(bad>1?'s':'')+' - tap for the report'):'report';
  approvalCard();
}

/* --- approval as a record, with the reason it lapsed -------------------- */
function approvalCard(){
  const a=set.approval||{};
  const when=a.at?(' on '+String(a.at).slice(0,16).replace('T',' ')):'';
  let h='';
  if(a.approved)
    h='<div class="card e-done"><div class=card-head>'+SM.pill('done','Approved')
      +'<h3>Approved'+when+'</h3></div>'
      +'<div class=basis>fingerprint '+SM.esc(a.fingerprint||'')+'</div></div>';
  else if(a.stale){
    const n=a.n_since||0;
    h='<div class="card e-you"><div class=card-head>'+SM.pill('you','Lapsed')
      +'<h3>Approval lapsed</h3></div>'
      +'<div class=card-sub>You approved this'+when+' as <code>'
      +SM.esc(a.approved_fingerprint||'')+'</code>. '
      +(n?(n+' change'+(n===1?'':'s')+' since.'):'The set has changed since.')
      +' It is now <code>'+SM.esc(a.fingerprint||'')+'</code>.</div>';
    if(n){
      h+='<details class=report><summary>What changed ('+n+')</summary>';
      for(const e of (a.since||[]).slice(0,40))
        h+='<div class=basis>'+SM.esc(String(e.at).slice(0,16).replace('T',' '))
          +' &middot; '+SM.esc(e.image||'')+' &middot; '
          +SM.esc(e.kind==='caption'?(e.clauses.filter(Boolean).join(', ')||'caption')
                                     :e.kind)+'</div>';
      h+='</details>';
    }
    h+='</div>';
  }
  SM.set($('approval'),null,h);
}

/* --- rows ---------------------------------------------------------------- */
function chipsFor(im){
  /* B1: this used to render only `uncaptioned` + `missing`, so saving a caption
     silently DELETED that row's `gaze?` chip even though set_caption() returns
     `uncertain`. All three sources, one function, used everywhere.
     Severity, not hue-as-category: red = a defect that will train,
     amber = look at this, grey = a note. */
  return (im.uncaptioned?'<span class="chip chip-stop">NO CAPTION</span>':'')
    +(im.uncertain||[]).map(u=>'<span class="chip chip-you">'+SM.esc(u)+'</span>').join('')
    +(im.missing||[]).map(m=>'<span class=chip>no '+SM.esc(m)+'</span>').join('');
}
const looks=im=>!!(im.uncaptioned||(im.uncertain||[]).length);

function rows(){
  const all=[...(set.images||[]).map(i=>({...i,_out:false})),
             ...(set.excluded||[]).map(i=>({...i,_out:true}))]
    .sort((a,b)=>a.name<b.name?-1:1);
  let h='';
  for(const im of all){
    const meta=[im.face_px?('face '+im.face_px+'px'):null,
                (im.yaw_deg!==undefined&&im.yaw_deg!==null)?('yaw '+im.yaw_deg+'°'):null]
      .filter(Boolean).join(' · ');
    h+='<div class="drow'+(im._out?' out':'')+'" data-look="'+(looks(im)?1:0)+'"'
      +' data-name="'+SM.esc(im.name)+'">'
      +'<img loading=lazy src="'+fileUrl(set.id,im.name)+'" alt="'+SM.esc(im.name)+'">'
      +'<div class=cap><div class=rowtop>'
      +'<button class="cap-box'+(im.caption?'':' empty')+'" data-act=edit'
      +' data-name="'+SM.esc(im.name)+'" title="tap to correct this caption">'
      +SM.esc(im.caption||'(empty)')+'</button>'
      +'<button class="btn btn-icon'+(im._out?' btn-primary':' btn-danger')+'"'
      +' data-act=toggle data-name="'+SM.esc(im.name)+'" data-out="'+(im._out?0:1)+'"'
      +' title="'+(im._out?'put back in the training set':'remove from the training set')
      +'">'+(im._out?'&#8626;':'&#10007;')+'</button>'
      +'</div><div class=chips>'+chipsFor(im)+'</div>'
      +'<div class=meta>'+SM.esc(im.name)+(meta?' · '+meta:'')+'</div>'
      +'</div></div>';
  }
  $('list').innerHTML=h;
  applyOnly();
}
/* A close call is a prompt to look, so the filter only ever HIDES rows. */
function applyOnly(){
  for(const r of document.querySelectorAll('#list .drow'))
    r.classList.toggle('hide', onlyLook && r.dataset.look!=='1');
}
/* B2: data-look was written once at render and applyOnly() was never re-run
   after an edit, so a row you had just fixed stayed in the filter. */
function refreshLook(name,im){
  const r=rowOf(name); if(!r) return;
  r.dataset.look=looks(im)?'1':'0';
  SM.set(r,'.chips',chipsFor(im));
  applyOnly();
}

/* --- the bottom bar: the primary label states the consequence ----------- */
function bar(){
  if(fixAt>=0) return fixBar();
  const a=set.approval||{};
  const g=set.gate||{}, cr=set.captions||{};
  const over=[(g.passed?null:'the gate'),(cr.passed?null:'captions')].filter(Boolean);
  let label='Approve for training';
  if(pos&&pos.estimate&&pos.estimate.total_s)
    label+=' — '+SM.dur(pos.estimate.total_s);
  if(pos&&pos.place) label+=', '+ordinal(pos.place)+' in the training order';
  SM.set($('bars'),null,'<div class=actbar>'
    +(a.approved
       ? '<button class="btn btn-danger" data-act=approve data-v=0>Withdraw approval</button>'
         +'<span class=dim>approved; it is in the training order</span>'
       : '<button class="btn btn-primary" data-act=approve data-v=1>'+SM.esc(label)
         +'</button><button class="btn" data-act=approve data-v=0>Reject</button>')
    +(over.length&&!a.approved
       ? '<span class=over>Approving over '+over.length+' finding'
         +(over.length>1?'s':'')+' ('+over.join(' and ')+') — a gate annotates,'
         +' it does not block.</span>'
       : '')
    +appearanceNote()
    +'</div>');
}
/* Approval triggers training, and training ends in the sweep - the first time
   text alone has to carry her identity. If her record is missing then, the
   sweep hours from now renders her from the trigger alone. Say so here. */
function appearanceNote(){
  const ap=set.appearance; if(!ap) return '';
  const bits=[];
  for(const m of (ap.missing||[])) bits.push('MISSING '+m.split(' - ')[0]);
  for(const w of (ap.warnings||[])) bits.push(w.split(' - ')[0]);
  if(!bits.length) return '';
  return '<span class=over>'+(ap.ok?'Appearance record: ':'Appearance record INCOMPLETE - ')
    +SM.esc(bits.join(' · '))+(ap.ok?'':'. The sweep after training will render her from'
    +' the trigger alone; add it to characters/appearance.json first')+'.</span>';
}
const ordinal=n=>n+(['th','st','nd','rd'][(n%100-20)%10]||['th','st','nd','rd'][n%100]||'th');

/* --- fix mode ------------------------------------------------------------ */
function startFix(){
  if(!fix||!fix.rows.length) return;
  fixAt=0; gotoFix();
}
function exitFix(){
  fixAt=-1;
  for(const r of document.querySelectorAll('.drow.focusrow')) r.classList.remove('focusrow');
}
function gotoFix(){
  const row=fix.rows[fixAt];
  if(!row) { exitFix(); renderAll(); return; }
  for(const r of document.querySelectorAll('.drow.focusrow')) r.classList.remove('focusrow');
  const el=rowOf(row.name);
  if(el){
    el.classList.remove('hide');          /* never hide the row you are fixing */
    el.classList.add('focusrow');
    /* scroll it into view and focus NOTHING: a focused textarea pops the
       keyboard on a phone and covers the thing you are looking at */
    el.scrollIntoView({block:'center',behavior:'smooth'});
  }
  fixBar();
}
function fixBar(){
  const row=fix&&fix.rows[fixAt];
  if(!row){
    SM.set($('bars'),null,'<div class="fixbar done"><span class=lbl>'
      +'<b>Nothing is flagged any more.</b><span>Every row you were asked to look'
      +' at has been seen.</span></span>'
      +'<button class="btn btn-primary" data-act=endfix>Back to the set</button></div>');
    return;
  }
  const sug=row.suggestion;
  SM.set($('bars'),null,'<div class=fixbar>'
    +'<button class="btn btn-icon" data-act=fixprev aria-label="previous"'
    +(fixAt===0?' disabled':'')+'>&#8249;</button>'
    +'<span class=lbl><b>Fix '+(fixAt+1)+' of '+fix.rows.length+'</b>'
    +'<span>'+SM.esc(row.reasons.join(' · '))+'</span></span>'
    +(sug?'<button class="btn btn-primary" data-act=applysug data-name="'
       +SM.esc(row.name)+'">Apply &ldquo;off cam&rdquo;</button>':'')
    +'<button class="btn" data-act=fixnext>'+(fixAt+1>=fix.rows.length?'Done':'Skip')
    +'</button>'
    +'<button class="btn btn-icon btn-ghost" data-act=endfix aria-label="leave fix mode">'
    +'&#10005;</button></div>');
}

/* --- actions: one delegated listener ------------------------------------ */
document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-act]'); if(!b) return;
  const a=b.dataset.act;
  if(a==='onlylook'){
    onlyLook=!onlyLook;
    try{ localStorage.setItem('onlyLook',onlyLook?'1':'0'); }catch(err){}
    applyOnly(); header(); return;
  }
  if(a==='startfix') return startFix();
  if(a==='endfix'){ exitFix(); renderAll(); return; }
  if(a==='fixprev'){ if(fixAt>0){ fixAt--; gotoFix(); } return; }
  if(a==='fixnext'){ fixAt++; gotoFix(); return; }
  if(a==='edit') return editCaption(b.dataset.name);
  if(a==='pick') return openPicker();
  if(a==='gpu') return SM.nav('gpu');
  b.disabled=true;
  try{
    if(a==='approve') await approve(b.dataset.v==='1');
    else if(a==='toggle') await toggle(b.dataset.name,b.dataset.out==='1');
    else if(a==='applysug') await applySuggestion(b.dataset.name);
  }catch(err){ SM.toast(err.message); }
  finally{ b.disabled=false; }
});

async function approve(v){
  const a=await SM.postJSON('/dataset/'+encodeURIComponent(set.id)+'/approve',{approved:v});
  set.approval=a;
  await Promise.all([refreshPos(),refreshFix()]);
  renderAll();
  SM.recount();
  if(v&&pos){
    /* the one place a review flow hands over to the trigger, deliberately:
       approval IS the trigger and approval order IS the training order */
    SM.toast(set.id+' approved — '+ordinal(pos.place)+' in the training order',
      {label:'Open the queue',run:()=>SM.nav('gpu')});
  }
}

async function toggle(name,out){
  const r=await SM.postJSON('/dataset/'+encodeURIComponent(set.id)+'/exclude',
    {name:name,excluded:out});
  /* Change ONLY this row. Rebuilding the list re-creates every <img>, they
     reload lazily, the page height changes under the thumb and the scroll jumps. */
  const el=rowOf(name);
  if(el){
    el.classList.toggle('out',out);
    const btn=el.querySelector('[data-act=toggle]');
    btn.dataset.out=out?'0':'1';
    btn.className='btn btn-icon'+(out?' btn-primary':' btn-danger');
    btn.innerHTML=out?'&#8626;':'&#10007;';
    btn.title=out?'put back in the training set':'remove from the training set';
  }
  const pool=[...(set.images||[]),...(set.excluded||[])].filter(Boolean);
  const ent=pool.find(i=>i&&i.name===name);
  set.images=pool.filter(i=>i!==ent&&!i._out);
  set.excluded=pool.filter(i=>i!==ent&&i._out);
  if(ent){ ent._out=out; (out?set.excluded:set.images).push(ent); }
  set.n=r.n; set.approval=r.approval;
  await Promise.all([refreshFix(),refreshPos()]);
  header(); bar();
}

function editCaption(name){
  const el=rowOf(name); if(!el||el.querySelector('.editor')) return;
  const box=el.querySelector('.cap-box');
  const text=box.classList.contains('empty')?'':box.textContent;
  const ed=document.createElement('div');
  ed.className='editor';
  ed.innerHTML='<textarea spellcheck=false></textarea>'
    +'<div class=btn-row><button class="btn btn-primary" data-save>Save caption</button>'
    +'<button class="btn btn-ghost" data-cancel>Cancel</button></div>';
  ed.querySelector('textarea').value=text;
  box.hidden=true; box.after(ed);
  ed.querySelector('textarea').focus();
  ed.querySelector('[data-cancel]').onclick=()=>{ ed.remove(); box.hidden=false; };
  ed.querySelector('[data-save]').onclick=async()=>{
    const v=ed.querySelector('textarea').value;
    try{
      const r=await SM.postJSON('/dataset/'+encodeURIComponent(set.id)+'/caption',
        {name:name,caption:v});
      applyCaption(name,r);
      ed.remove(); box.hidden=false;
    }catch(err){ SM.toast(err.message); }
  };
}

/* One place that absorbs a caption write, so the chips, the look flag, the
   report, the approval and the bar can never drift apart again. */
function applyCaption(name,r){
  const el=rowOf(name);
  if(el){
    const box=el.querySelector('.cap-box');
    box.textContent=r.caption||'(empty)';
    box.classList.toggle('empty',!r.caption);
  }
  const ent=[...(set.images||[]),...(set.excluded||[])].find(i=>i&&i.name===name);
  if(ent){ ent.caption=r.caption; ent.missing=r.missing;
           ent.uncertain=r.uncertain; ent.uncaptioned=r.uncaptioned; }
  set.captions=r.captions; set.approval=r.approval;
  refreshLook(name,r);
  refreshFix().then(()=>{ header(); bar(); });
}

async function applySuggestion(name){
  const row=fix.rows.find(r=>r.name===name);
  if(!row||!row.suggestion) return;
  const r=await SM.postJSON('/dataset/'+encodeURIComponent(set.id)+'/caption',
    {name:name,caption:row.suggestion.caption});
  applyCaption(name,r);
  SM.toast('caption corrected');
  fixAt++; setTimeout(gotoFix,250);
}

function gone(id,fallback){
  $('list').innerHTML='<div class=errbox><b>'+SM.esc(id)+' is gone</b>'
    +'That training set is not in the list any more.'
    +(fallback?' Opening the first one that is.':'')
    +'<div class=btn-row><button class="btn btn-primary" data-act=pick>Choose a set'
    +'</button></div></div>';
  location.hash='';
  if(fallback) setTimeout(()=>open(fallback).catch(()=>{}),1200);
}
function fail(what,why){
  $('list').innerHTML='<div class=errbox><b>'+SM.esc(what)+'</b>'+SM.esc(why||'')
    +'<div class=btn-row><button class="btn" data-act=gpu>What the card is doing'
    +'</button></div></div>';
}

loadList();
"""

PAGE = page("training set", BODY, OWN_JS, OWN_CSS)


def preview_router(cfg: dict):
    from fastapi import APIRouter, Body, HTTPException  # noqa: PLC0415
    from fastapi.responses import FileResponse, HTMLResponse  # noqa: PLC0415

    root = preview_root(cfg)
    r = APIRouter()

    @r.get("/dataset", response_class=HTMLResponse)
    def _page():
        return PAGE

    @r.get("/dataset/list")
    def _list() -> list[dict]:
        return list_previews(root)

    @r.get("/dataset/file")
    def _file(ds: str, name: str, w: int = _WEB_MAX):
        p = image_path(root, ds, name)
        if p is None:
            raise HTTPException(404)
        return FileResponse(web_copy(p, w))

    @r.get("/dataset/edits")
    def _edits(ds: str | None = None) -> dict:
        """What Jeremy has had to correct, and what crossed the follow-up threshold."""
        return edit_report(root, ds)

    @r.get("/dataset/{ds_id}")
    def _one(ds_id: str) -> dict:
        p = preview_payload(root, ds_id)
        if p is None:
            raise HTTPException(404)
        return p

    @r.post("/dataset/{ds_id}/exclude")
    def _exclude(ds_id: str, body: dict = Body(...)) -> dict:
        try:
            return exclude_image(root, ds_id, str(body.get("name", "")), bool(body.get("excluded", True)))
        except KeyError as e:
            raise HTTPException(404) from e

    @r.post("/dataset/{ds_id}/caption")
    def _caption(ds_id: str, body: dict = Body(...)) -> dict:
        try:
            return set_caption(root, ds_id, str(body.get("name", "")), str(body.get("caption", "")))
        except KeyError as e:
            raise HTTPException(404) from e

    @r.get("/dataset/{ds_id}/fixlist")
    def _fixlist(ds_id: str) -> dict:
        """The rows with something to DO, each with the one fix that fits."""
        if load_preview(root, ds_id) is None:
            raise HTTPException(404)
        return fix_rows(root, ds_id)

    @r.get("/dataset/{ds_id}/approval")
    def _approval(ds_id: str) -> dict:
        if load_preview(root, ds_id) is None:
            raise HTTPException(404)
        return approval_record(root, ds_id)

    @r.post("/dataset/{ds_id}/captions")
    def _captions(ds_id: str, body: dict = Body(...)) -> dict:
        """Several captions in one request, each logged as its own edit."""
        edits = body.get("edits") or []
        if not isinstance(edits, list):
            raise HTTPException(400, "edits must be a list")
        try:
            return set_captions(root, ds_id, edits)
        except KeyError as e:
            raise HTTPException(404) from e

    @r.post("/dataset/{ds_id}/approve")
    def _approve(ds_id: str, body: dict = Body(...)) -> dict:
        try:
            return record_approval(root, ds_id, bool(body.get("approved")))
        except KeyError as e:
            raise HTTPException(404) from e

    return r
