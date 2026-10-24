"""Naming, categorising and placing game assets — the game's own contract.

    src/assets/characters/<character-id>/outfits/<category>_<look-number>_<pose>.webp

`<category>_<look-number>` is the persistent LOOK IDENTITY (one outfit + hair
pairing); `<pose>` is presentation. So look numbers are assigned in a PLAN
before anything renders, and every render, cutout and placed file carries
{character, category, look, pose} in its sidecar. Placement never guesses a
category from pixels.

Source: C:/dev/chillafterdark/docs/character-asset-organization.md and
src/data/wardrobePacks.js (read 2026-09-11).
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

# The standard 28-file pack, in the order the game's docs list them.
PACK_28 = {"casual": 7, "workout": 4, "fancy_dining_gallery": 4, "fancy_town": 4, "casual_date": 4, "work": 5}
CATEGORY_ALIASES = {"weekly_casual": "casual"}      # the art-source folder name for `casual`
POSES = ("standing", "sitting")
DEFAULT_POSE = "standing"
_NAME_RE = re.compile(r"^(?P<category>[a-z][a-z_]*?)_(?P<look>\d{2})_(?P<pose>[a-z]+)$")


def category_id(name: str) -> str:
    return CATEGORY_ALIASES.get(name, name)


def look_id(category: str, look: int) -> str:
    return f"{category_id(category)}_{look:02d}"


def runtime_name(category: str, look: int, pose: str = DEFAULT_POSE, ext: str = "webp") -> str:
    if pose not in POSES:
        raise ValueError(f"pose {pose!r} not in {POSES}")
    return f"{look_id(category, look)}_{pose}.{ext}"


def parse_runtime_name(name: str) -> dict | None:
    """'fancy_dining_gallery_02_standing.webp' -> {category, look, pose}. None if not the contract."""
    m = _NAME_RE.match(Path(name).stem)
    if not m or m["pose"] not in POSES:
        return None
    return {"category": m["category"], "look": int(m["look"]), "pose": m["pose"]}


def existing_looks(outfits_dir: Path) -> dict[str, int]:
    """Highest look number already shipped per category (so a plan can extend, not collide)."""
    out: dict[str, int] = {}
    if not outfits_dir.exists():
        return out
    for p in outfits_dir.iterdir():
        meta = parse_runtime_name(p.name)
        if meta:
            out[meta["category"]] = max(out.get(meta["category"], 0), meta["look"])
    return out


# ------------------------------------------------------------------- plan

def make_plan(character: str, *, counts: dict[str, int] | None = None, pose: str = DEFAULT_POSE,
              lora: str | None = None, source_asset: str | None = None, reference: str | None = None,
              looks: dict[str, list[dict]] | None = None) -> dict:
    """A plan is the single place look numbers are decided, and they start at 1:
    a pack REPLACES what the game ships for her. Plans used to number on from
    her shipped looks (casual_08 after casual_01-07), which put 28 files in the
    game that nothing could show - the game draws looks 1..lookCount per
    category (Jeremy, 2026-10-21: "the new assets are supposed to replace the
    existing").

    looks: {category: [{"outfit": ..., "hair": ...}, ...]} — one pairing per look,
    in look-number order. Missing pairings are left blank for the author to
    fill; rendering refuses blank ones."""
    counts = counts or PACK_28
    cats = {}
    for cat, n in counts.items():
        given = (looks or {}).get(cat, [])
        entries = []
        for i in range(n):
            look = 1 + i
            pair = given[i] if i < len(given) else {}
            entries.append({"look": look, "id": look_id(cat, look),
                            "outfit": pair.get("outfit", ""), "hair": pair.get("hair", "")})
        cats[cat] = {"lookCount": n, "looks": entries}
    return {"character": character, "pose": pose, "lora": lora, "source_asset": source_asset,
            "reference": reference, "categories": cats,
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def plan_slots(plan: dict) -> list[dict]:
    """Every (category, look) the plan defines, flattened, with its runtime name.

    The runtime name is POSITIONAL - the first casual look ships as casual_01
    whatever the plan calls it - so a plan approved under the old numbering
    (nisha's and kasia's say casual_08.., with renders, judge items and queued
    re-rolls under those ids) still replaces her looks in the game rather than
    landing beside them. The id and folder keep the plan's own number."""
    out = []
    pose = plan.get("pose", DEFAULT_POSE)
    for cat, block in plan["categories"].items():
        for i, entry in enumerate(block["looks"]):
            # `n` is the look's place in the WHOLE plan (1..28): the pose
            # rotation walks it so the four pose families land seven each,
            # where `look` restarts per category and would give casual two
            # fronts for every relaxed pose
            out.append({"category": cat, "look": entry["look"], "n": len(out) + 1, "id": entry["id"],
                        "outfit": entry["outfit"], "hair": entry["hair"],
                        "pose": pose, "filename": runtime_name(cat, i + 1, pose)})
    return out


def slot_dirname(slot: dict) -> str:
    """Folder a slot's renders/cutouts live in: the look id plus pose, e.g. casual_03_standing."""
    return f"{slot['id']}_{slot['pose']}"


# --------------------------------------------------------------- placement

def rank_candidates(cands: list[dict]) -> list[dict]:
    """Best first: unflagged before flagged, then FEWEST BROKEN ASKS (crop, body turn,
    head turn, neutral-vs-smile from `adherence.check`, measured against what the
    prompt asked), then soft expression misses, then identity score, then fewest
    partial pixels. Relative to the ask on purpose - Jeremy, 2026-10-02: a face-size
    threshold "is not the right generalized rule"; a full-body look must still win
    when full body was asked for."""
    def key(c):
        rep = c.get("report") or {}
        adh = c.get("adherence") or {}
        return (bool(rep.get("flags")), len(adh.get("failed") or []), len(adh.get("soft") or []),
                -(c.get("score") or 0.0), rep.get("partial", 1.0))
    return sorted(cands, key=key)


def place(cutouts: list[dict], plan: dict, staging: Path, *, pick: dict[str, str] | None = None) -> dict:
    """Copy the winning cutout of every slot to staging/<char>/outfits/<runtime name>.

    cutouts: sidecars from assets.cutout (each carrying an `asset` block with
    category/look/pose, a `score`, and `outputs.webp`). pick: {look_id: filename}
    human overrides that beat the ranking. Returns the mapping."""
    pick = pick or {}
    char = plan["character"]
    outfits = staging / char / "outfits"
    outfits.mkdir(parents=True, exist_ok=True)
    by_slot: dict[str, list[dict]] = {}
    for c in cutouts:
        a = c.get("asset") or {}
        if not a.get("category") or a.get("look") is None:
            continue
        by_slot.setdefault(look_id(a["category"], int(a["look"])), []).append(c)

    mapping = {"character": char, "pose": plan.get("pose", DEFAULT_POSE), "slots": [], "missing": [],
               "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    for slot in plan_slots(plan):
        cands = rank_candidates(by_slot.get(slot["id"], []))
        chosen = None
        if slot["id"] in pick:
            wanted = pick[slot["id"]]
            chosen = next((c for c in cands
                           if wanted in {Path(v).name for v in c["outputs"].values()} | {Path(c["source"]).name}),
                          None)
        chosen = chosen or (cands[0] if cands else None)
        if chosen is None:
            mapping["missing"].append(slot["id"])
            continue
        src = Path(chosen["outputs"].get("webp") or chosen["outputs"]["png"])
        dest = outfits / slot["filename"]
        if src.suffix.lower() == ".webp":
            shutil.copy2(src, dest)
        else:
            Image.open(src).convert("RGBA").save(dest, "WEBP", quality=92, method=6, exact=True)
        mapping["slots"].append({"id": slot["id"], "file": slot["filename"], "from": chosen["source"],
                                 "score": chosen.get("score"), "flags": (chosen.get("report") or {}).get("flags", []),
                                 "candidates": len(cands), "overridden": slot["id"] in pick,
                                 "outfit": slot["outfit"], "hair": slot["hair"]})
    (staging / char / "mapping.json").write_text(json.dumps(mapping, indent=1), encoding="utf-8")
    return mapping


def pack_registration(plan: dict, *, work_locations: list[str] | None = None) -> str:
    """The one line wardrobePacks.js needs for this character."""
    wl = ", ".join(f"'{w}'" for w in (work_locations or []))
    return f"  {plan['character']}: {{ id: '{plan['character']}', workLocations: [{wl}] }},"


def mapping_sheet(mapping: dict, staging: Path, out: Path, *, cols: int = 4, tile: int = 300) -> Path:
    """Runtime slot <- source shot, on a checkerboard — same review the codex step produced."""
    char = mapping["character"]
    items = mapping["slots"]
    th = int(tile * 1.5)
    rows = max(1, -(-len(items) // cols))
    sheet = Image.new("RGB", (cols * tile, 40 + rows * (th + 44)), (216, 216, 216))
    d = ImageDraw.Draw(sheet)
    d.text((12, 10), f"{char.upper()}  |  {len(items)} slots placed, {len(mapping['missing'])} missing  |  slot <- source", fill=(30, 30, 30))
    for i, s in enumerate(items):
        x, y = (i % cols) * tile, 40 + (i // cols) * (th + 44)
        im = Image.open(staging / char / "outfits" / s["file"]).convert("RGBA")
        im.thumbnail((tile - 10, th))
        board = Image.new("RGB", im.size, (238, 238, 238))
        bd = ImageDraw.Draw(board)
        for yy in range(0, im.height, 24):
            for xx in range(0, im.width, 24):
                if (xx // 24 + yy // 24) % 2:
                    bd.rectangle((xx, yy, xx + 23, yy + 23), fill=(200, 200, 200))
        board.paste(im, (0, 0), im)
        sheet.paste(board, (x + (tile - board.width) // 2, y))
        sc = f"  {s['score']:.3f}" if s.get("score") is not None else ""
        fl = f"  [{', '.join(s['flags'])}]" if s.get("flags") else ""
        d.text((x + 6, y + th + 4), f"{s['file']}{sc}{fl}", fill=(30, 30, 30))
        d.text((x + 6, y + th + 20), f"<- {Path(s['from']).parent.name}/{Path(s['from']).name}"[:46], fill=(70, 70, 70))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=95)
    return out
