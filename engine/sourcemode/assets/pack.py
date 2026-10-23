"""The wardrobe pack through text-to-image: her LoRA, a grey studio, one shot per look.

Jeremy, 2026-10-14, after judging Amanda's 28 looks both ways: "We'll just
move forward with T2I because it performs better. That way, anything rejected
gets regenerated and anything accepted goes into queue for processing and
placement into the game repo. I would like a formal approval step of that
final shift though."

So the pack is: render here -> judge (`pack_<char>`) -> rejects re-roll through
`redo.py` back into the same folders -> when every look is a keep, a CPU-lane
job cuts them out and stages them (`process_pack.py`) -> he approves on the
Characters tab, and ONLY that approval writes into the game - that, and the
profile pick on the same tab (`ship_portrait`: one reference photo becomes
`portraits/profile.webp`). Nothing else in the engine writes there.

The Edit graph (a plate re-dressed 28 times on magenta) stays in
`render.render_plan` for anything that still wants it; the pack no longer
does. A `renders/` folder left by it is set aside, never mixed in: a T2I
sidecar says `"graph": "qwen_image_t2i"`, an Edit one does not.

Layout, unchanged for cutout and place:
    outputs/game-assets/<char>/renders/<category>_<NN>_<pose>/shot_00_s<seed>.png (+ .json)
"""

from __future__ import annotations

import json
import re
import shutil
import time
from collections import Counter
from pathlib import Path

from .catalog import plan_slots, slot_dirname

GRAPH = "qwen_image_t2i"
SEED_BASE = 7100              # the per-look seed the Edit pack used too, so the two compare
STUDIO_BACKDROP = ("soft even studio lighting, a plain light grey seamless studio background "
                   "with nothing else in frame")
W, H = 1024, 1536


def seed_for(index: int) -> int:
    return SEED_BASE + index * 1000


# Jeremy, 2026-10-20: "auto-reroll ... reroll those before the queue moves on to
# the next thing when they are wrong". A fresh shot that comes back chest-up
# when mid-thigh was asked, or with her head cut off at the top edge, is drawn
# again on a new seed inside the same job. Kasia's framing A/B showed no prompt
# wording fixes a chest-up dress; a new seed does. The stride is not redo's
# 10007, so a later reject's re-roll never lands on a seed tried here.
REROLLS = 3
REROLL_STRIDE = 7919
TOP_RUN = 40         # px of unbroken non-backdrop along every one of the top 4 rows


def touches_top(path: Path) -> bool:
    """True when her head runs off the top edge of the render. The backdrop is
    keyed from the top rows' own corners (the studio darkens toward the top, so
    the frame-wide key called 96 clean shots touching), and she touches when an
    unbroken run of more than TOP_RUN px differs from it on each of the top 4
    rows. On 312 pack renders, 2026-10-20: 10 of the 11 the cutout found
    touching the top, no false alarms."""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)[:4]
    key = np.median(np.concatenate([a[:, :80].reshape(-1, 3), a[:, -80:].reshape(-1, 3)]), axis=0)
    off = np.abs(a - key).max(axis=2) > 30

    def longest(row) -> int:
        best = cur = 0
        for v in row:
            cur = cur + 1 if v else 0
            best = max(best, cur)
        return best

    return min(longest(r) for r in off) > TOP_RUN


def framing_problem(asked: dict, got: dict, path: Path) -> str | None:
    """Why a fresh shot gets re-drawn, or None when its framing is fine."""
    if asked.get("crop") in ("mid-thigh-up", "knee-up", "full-body") and got.get("crop") == "chest-up":
        return "chest-up"
    try:
        if touches_top(path):
            return "head cut off"
    except (OSError, ValueError):
        pass
    return None


def renders_root(out_root: Path, character: str) -> Path:
    return Path(out_root) / "game-assets" / character / "renders"


def is_t2i_folder(root: Path) -> bool | None:
    """True when the renders here came through T2I, False when through Edit,
    None when there is nothing to say (empty or missing)."""
    if not root.is_dir():
        return None
    for side in root.glob("*_*/shot_*.json"):
        try:
            return json.loads(side.read_text(encoding="utf-8")).get("graph") == GRAPH
        except ValueError:
            continue
    if any(root.glob("_plate*.png")):
        return False
    return None


def retire_other_renders(root: Path, log=print) -> Path | None:
    """Set aside a renders folder from the other graph so its shots are never
    taken as this pack's. Returns where it went."""
    if is_t2i_folder(root) is not False:
        return None
    dest = root.with_name(f"{root.name}_edit_{time.strftime('%Y%m%d-%H%M')}")
    shutil.move(str(root), str(dest))
    log(f"  renders from the Edit graph set aside as {dest.name}")
    return dest


def rendered_prompt(shot: Path) -> str | None:
    """The prompt a shot was rendered from, off its sidecar; None if unknown."""
    try:
        return json.loads(shot.with_suffix(".json").read_text(encoding="utf-8")).get("prompt")
    except (OSError, ValueError):
        return None


def render_pack(cfg: dict, client, character: str, plan: dict, out_root: Path, *,
                lora_path: str, negative: str, ref=None, only: set[str] | None = None,
                seed: int | None = None, backdrop: str = STUDIO_BACKDROP,
                root: Path | None = None, log=print) -> list[dict]:
    """Every look of the plan (or `only` those) through T2I. A look whose shot is
    already on disk from the same prompt is skipped; a changed look re-renders,
    and a re-roll drops the old file first. `seed`
    replaces the per-look seed, for a re-roll of one look. `backdrop` is the
    studio by default; a key-colour trial passes `render.KEY_BACKDROP` and its
    own `root` so the pack's folder is never mixed with it. Returns the
    sidecars, one per look rendered or found."""
    from ..gates.identity import cosine, embed_image  # noqa: PLC0415
    from .adherence import check, measure  # noqa: PLC0415
    from .render import pose_fields, shot_prompt, t2i_workflow  # noqa: PLC0415

    from .appearance import pack_camera  # noqa: PLC0415
    cam_neg = pack_camera(character).get("negative")
    negative = f"{negative}, {cam_neg}" if cam_neg else negative

    root = root or renders_root(out_root, character)
    retire_other_renders(root, log)
    root.mkdir(parents=True, exist_ok=True)
    out, fails = [], Counter()
    for i, slot in enumerate(plan_slots(plan)):
        if only is not None and slot["id"] not in only:
            continue
        d = root / slot_dirname(slot)
        d.mkdir(exist_ok=True)
        base = seed if seed is not None else seed_for(i)
        # a shot re-drawn for its framing sits under its re-draw seed
        s = next((base + REROLL_STRIDE * k for k in range(REROLLS + 1)
                  if (d / f"shot_00_s{base + REROLL_STRIDE * k}.png").exists()), base)
        dest = d / f"shot_00_s{s}.png"
        prompt = shot_prompt(character, slot, plan.get("trigger"), backdrop=backdrop)
        try:
            if dest.exists() and rendered_prompt(dest) != prompt:
                # winnie, 2026-10-18: her looks were rewritten off pure white and the
                # re-run skipped all 28 because the old shots were on disk
                log(f"  {slot['id']}: the look changed since its shot was rendered - re-rendering")
                dest.unlink()
                s, dest = base, d / f"shot_00_s{base}.png"

            def draw(seed: int, path: Path) -> bool:
                files = client.outputs(client.wait(client.submit(
                    t2i_workflow(cfg, prompt, seed, f"pack/{character}/{slot['id']}",
                                 lora_path=lora_path, negative=negative, width=W, height=H)),
                    timeout_s=3600))
                if files:
                    client.fetch(files[0], path)
                return bool(files)

            def adherence(path: Path) -> dict:
                try:
                    return check(asked, measure(path))
                except Exception as exc:  # noqa: BLE001 - a measurement, never a blocker
                    return {"failed": [], "soft": [], "got": {}, "error": str(exc)}

            asked = pose_fields(character, slot)["asked"]
            fresh = not dest.exists()
            if fresh and not draw(s, dest):
                log(f"  {slot['id']}: no output")
                continue
            adh = adherence(dest)
            why = framing_problem(asked, adh.get("got") or {}, dest) if fresh else None
            for k in range(1, REROLLS + 1):
                if not why:
                    break
                s2 = s + REROLL_STRIDE * k
                alt = d / f"shot_00_s{s2}.png"
                log(f"  {slot['id']}: {why} - re-drawing on seed {s2}")
                if not draw(s2, alt):
                    break
                alt_adh = adherence(alt)
                alt_why = framing_problem(asked, alt_adh.get("got") or {}, alt)
                if alt_why:
                    alt.unlink(missing_ok=True)       # the first draw stays the fallback
                    continue
                dest.unlink(missing_ok=True)
                dest, s, adh, why = alt, s2, alt_adh, None
            if why:
                log(f"  {slot['id']}: still {why} after {REROLLS} re-draws - kept the first, judge it")
            e = embed_image(dest)
            score = round(float(cosine(ref, e)), 4) if (ref is not None and e is not None) else None
            meta = {"source": str(dest),
                    "asset": {"character": character, "category": slot["category"],
                              "look": slot["look"], "pose": slot["pose"], "shot": 0},
                    "score": score, "asked": asked, "adherence": adh, "seed": s,
                    "prompt": prompt, "lora": lora_path, "graph": GRAPH}
            dest.with_suffix(".json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
            (d / "prompt.txt").write_text(prompt, encoding="utf-8")
            for f in adh.get("failed") or []:
                fails[f.split(":")[0]] += 1
            out.append(meta)
            log(f"  {slot['id']}: {score} {'OK' if not adh.get('failed') else adh['failed']}")
        except Exception as exc:  # noqa: BLE001 - one bad look never kills the run
            log(f"  {slot['id']}: ERROR {exc}")
    if fails:
        log(f"  adherence failures by kind, out of {len(out)}: {dict(fails)}")
    return out


def shots(root: Path) -> list[Path]:
    """The one T2I shot per look folder, for the cutout."""
    out = []
    for d in sorted(p for p in root.glob("*_*") if p.is_dir()):
        for png in sorted(d.glob("shot_*.png")):
            side = png.with_suffix(".json")
            try:
                if side.is_file() and json.loads(side.read_text(encoding="utf-8")).get("graph") == GRAPH:
                    out.append(png)
            except ValueError:
                continue
    return out


# --- staging and the approval ---------------------------------------------------

def staged_path(out_root: Path, character: str) -> Path:
    return Path(out_root) / "game-assets" / character / "staged.json"


def read_staged(out_root: Path, character: str) -> dict | None:
    p = staged_path(out_root, character)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def process_due(judge_root: Path, out_root: Path, set_id: str) -> str | None:
    """Why a finished pack set should be cut out and staged now - or None.
    Every look kept, and nothing staged since the last verdict changed."""
    from .judge import load_set, load_verdicts  # noqa: PLC0415

    s = load_set(judge_root, set_id)
    if not s or (s.get("meta") or {}).get("shoot") != "pack28":
        return None
    v = load_verdicts(judge_root, set_id)
    ids = [it["id"] for it in s["items"]]
    if any(i not in v for i in ids):
        return None
    if any(v[i] != "keep" for i in ids):
        return None
    c = s["meta"]["character"]
    st = read_staged(out_root, c)
    vp = judge_root / "verdicts" / f"{set_id}.json"
    if st and st.get("verdicts_mtime") and vp.is_file() and st["verdicts_mtime"] >= vp.stat().st_mtime - 1:
        return None                                  # staged from exactly these verdicts
    return f"all {len(ids)} looks kept"


def game_counterpart(slot: dict, ordinal: int, pose: str, game_outfits: Path) -> Path | None:
    """The game file a staged look is compared against. The same name when the
    game has one (the ship would overwrite it); otherwise her look in the same
    category at the same position - a plan numbers on from what she already has
    (looks.py: casual_08 when the game ships casual_01-07), so the names never
    match and the old sheet read "not in the game" for a character with a full
    wardrobe (Jeremy, 2026-10-20, on gabi: "showed completely blank for the
    current game assets ... even though there are current game assets for her")."""
    from .catalog import parse_runtime_name  # noqa: PLC0415

    same = game_outfits / slot["file"]
    if same.is_file():
        return same
    cat = re.sub(r"_\d+$", "", slot["id"])
    have = sorted((p for p in game_outfits.iterdir() if game_outfits.is_dir()
                   and (parse_runtime_name(p.name) or {}).get("category") == cat
                   and (parse_runtime_name(p.name) or {}).get("pose") == pose),
                  key=lambda p: parse_runtime_name(p.name)["look"]) if game_outfits.is_dir() else []
    return have[ordinal % len(have)] if have else None


def compare_sheet(mapping: dict, staged_outfits: Path, game_outfits: Path, out: Path, *,
                  tile: int = 240, cols: int = 4) -> tuple[Path, int]:
    """Each staged look beside what the game ships today - the file it would
    overwrite, or failing that her look in the same category at the same
    position (`game_counterpart`) - on a checker, so the approval is a
    comparison and not a leap. Returns the sheet and how many game files would
    be overwritten."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    th = int(tile * 1.5)
    slots = mapping["slots"]
    pose = mapping.get("pose", "standing")
    rows = max(1, -(-len(slots) // cols))
    sheet = Image.new("RGB", (cols * (2 * tile + 12), 24 + rows * (th + 40)), (236, 236, 236))
    draw = ImageDraw.Draw(sheet)
    overwrite = 0
    seen_in_cat: dict[str, int] = {}

    def board(p: Path | None) -> Image.Image:
        b = Image.new("RGB", (tile, th), (205, 205, 205))
        bd = ImageDraw.Draw(b)
        for y in range(0, th, 16):
            for x in range(0, tile, 16):
                if (x // 16 + y // 16) % 2:
                    bd.rectangle((x, y, x + 15, y + 15), fill=(255, 255, 255))
        if p and p.is_file():
            im = Image.open(p).convert("RGBA"); im.thumbnail((tile, th))
            b.paste(im, ((tile - im.width) // 2, th - im.height), im)
        else:
            bd.text((8, th // 2), "not in the game", fill=(90, 90, 90))
        return b

    for i, s in enumerate(slots):
        x0 = (i % cols) * (2 * tile + 12) + 6
        y0 = 24 + (i // cols) * (th + 40) + 14
        cat = re.sub(r"_\d+$", "", s["id"])
        ordinal = seen_in_cat.get(cat, 0)
        seen_in_cat[cat] = ordinal + 1
        g = game_counterpart(s, ordinal, pose, game_outfits)
        same = g is not None and g.name == s["file"]
        if same:
            overwrite += 1
        sheet.paste(board(staged_outfits / s["file"]), (x0, y0))
        sheet.paste(board(g), (x0 + tile, y0))
        right = ("overwrites " + g.stem if same else "beside " + g.stem) if g else "nothing in the game"
        draw.text((x0, y0 - 13), f"{s['id']}   new  |  {right}", fill=(30, 30, 30))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=88)
    return out, overwrite


def pairs(out_root: Path, character: str, game_root: Path) -> list[dict]:
    """Each staged look beside the game file it stands against, for the
    Characters tab to show as tiles he can pick between. Jeremy, 2026-10-22:
    approve all by default, "but I would like an option to choose which one to
    keep from the side-by-side sets". Same rule as the compare sheet: the
    file it would overwrite, else her look in the same category at the same
    position; `game` is None when the game has nothing to put beside it."""
    from .catalog import look_id, parse_runtime_name  # noqa: PLC0415

    st = read_staged(out_root, character)
    if not st or not st.get("files"):
        return []
    gdir = game_root / "src" / "assets" / "characters" / character / "outfits"
    seen: dict[str, int] = {}
    out = []
    for name in st["files"]:
        m = parse_runtime_name(name)
        sid = look_id(m["category"], m["look"]) if m else Path(name).stem
        cat = m["category"] if m else re.sub(r"_\d+$", "", sid)
        ordinal = seen.get(cat, 0)
        seen[cat] = ordinal + 1
        g = game_counterpart({"id": sid, "file": name}, ordinal, m["pose"] if m else "standing", gdir)
        out.append({"id": sid, "file": name, "game": g.name if g else None,
                    "overwrites": bool(g and g.name == name)})
    return out


def thumb(src: Path, out_root: Path, character: str, side: str, width: int = 360) -> Path:
    """A small RGBA WebP of a cutout for the tiles, cached under review/ -
    never beside the game's files, which the game counts."""
    from PIL import Image  # noqa: PLC0415

    cache = Path(out_root) / "game-assets" / character / "review" / "_thumbs" / side / f"{src.stem}_{width}.webp"
    if cache.is_file() and cache.stat().st_mtime >= src.stat().st_mtime:
        return cache
    im = Image.open(src).convert("RGBA")
    im.thumbnail((width, width * 2))
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    im.save(tmp, "WEBP", quality=80)
    tmp.replace(cache)
    return cache


def ship(out_root: Path, character: str, game_root: Path, keep: list[str] | None = None) -> dict:
    """The approval: copy the staged outfits into the game's folder for her,
    overwriting what is there under the same names, and record it. With
    `ship_portrait` below, the only place in the engine that writes into the
    game repo.

    `keep` is the files he ticked; None means every staged file (the default).
    An unticked look is skipped - the game keeps whatever it has there."""
    st = read_staged(out_root, character)
    if not st or not st.get("files"):
        raise ValueError("nothing is staged for her")
    chosen = list(st["files"]) if keep is None else [n for n in st["files"] if n in set(keep)]
    if keep is not None and set(keep) - set(st["files"]):
        raise ValueError("not staged: " + ", ".join(sorted(set(keep) - set(st["files"]))))
    if not chosen:
        raise ValueError("nothing ticked - tick at least one new look, or discard the staging")
    src = Path(out_root) / "game-assets" / character / "outfits"
    dest = game_root / "src" / "assets" / "characters" / character / "outfits"
    dest.mkdir(parents=True, exist_ok=True)
    copied, overwrote = [], 0
    for name in chosen:
        f = src / name
        if not f.is_file():
            continue
        if (dest / name).is_file():
            overwrote += 1
        shutil.copy2(f, dest / name)
        copied.append(name)
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()), "files": copied,
           "overwrote": overwrote, "to": str(dest), "from_set": st.get("set"),
           "skipped": [n for n in st["files"] if n not in chosen]}
    st["shipped"] = rec
    staged_path(out_root, character).write_text(json.dumps(st, indent=1), encoding="utf-8")
    pp = Path(out_root) / "game-assets" / character / "plan_28.json"
    if pp.is_file():
        try:
            plan = json.loads(pp.read_text(encoding="utf-8"))
            plan["shipped"] = rec
            pp.write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        except ValueError:
            pass
    return rec


def discard(out_root: Path, character: str) -> bool:
    p = staged_path(out_root, character)
    if not p.is_file():
        return False
    p.unlink()
    return True


# --- the profile portrait ----------------------------------------------------
# The game shows `<char>/portraits/profile.webp` as her profile picture: one
# file, an RGB WebP at the photo's own size (cassie's is her reference portrait
# byte for byte). Jeremy, 2026-10-23: pick it from her reference photos on the
# Characters tab - one, never several.

PORTRAIT_QUALITY = 88      # what the game's own convert-assets-webp.mjs uses


def portrait_path(game_root: Path, character: str) -> Path:
    return game_root / "src" / "assets" / "characters" / character / "portraits" / "profile.webp"


def portrait_record_path(out_root: Path, character: str) -> Path:
    return Path(out_root) / "game-assets" / character / "portrait.json"


def portrait_state(out_root: Path | None, character: str, game_root: Path) -> dict:
    """What the card shows: whether the game has a profile for her, and which
    reference it came from when it was picked here (None when the game's file
    predates the picker or was replaced some other way)."""
    gp = portrait_path(game_root, character)
    have = gp.is_file()
    rec = None
    rp = portrait_record_path(out_root, character) if out_root else None
    if have and rp and rp.is_file():
        try:
            rec = json.loads(rp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rec = None
        # a file the record did not write (newer than the pick) is not that pick
        if rec and abs(gp.stat().st_mtime - float(rec.get("mtime") or 0)) > 2:
            rec = None
    return {"game": have, "from": (rec or {}).get("from"), "at": (rec or {}).get("at")}


def ship_portrait(out_root: Path, character: str, game_root: Path, src: Path) -> dict:
    """Make `src` (one of her reference photos) the game's profile portrait:
    an RGB WebP at the photo's own size at portraits/profile.webp, replacing
    whatever is there. Records which photo it was so the card can mark it."""
    from PIL import Image  # noqa: PLC0415

    src = Path(src)
    if not src.is_file():
        raise ValueError(f"no such photo: {src.name}")
    dest = portrait_path(game_root, character)
    overwrote = dest.is_file()
    dest.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("RGB")
    tmp = dest.with_suffix(".tmp")
    im.save(tmp, "WEBP", quality=PORTRAIT_QUALITY)
    tmp.replace(dest)
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()), "from": src.name,
           "to": str(dest), "overwrote": overwrote, "size": list(im.size),
           "mtime": dest.stat().st_mtime}
    rp = portrait_record_path(out_root, character)
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec
