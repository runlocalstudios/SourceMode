"""The wardrobe pack through text-to-image: her LoRA, a grey studio, one shot per look.

Jeremy, 2026-10-14, after judging Amanda's 28 looks both ways: "We'll just
move forward with T2I because it performs better. That way, anything rejected
gets regenerated and anything accepted goes into queue for processing and
placement into the game repo. I would like a formal approval step of that
final shift though."

So the pack is: render here -> judge (`pack_<char>`) -> rejects re-roll through
`redo.py` back into the same folders -> when every look is a keep, a CPU-lane
job cuts them out and stages them (`process_pack.py`) -> he approves on the
Characters tab, and ONLY that approval writes into the game.

The Edit graph (a plate re-dressed 28 times on magenta) stays in
`render.render_plan` for anything that still wants it; the pack no longer
does. A `renders/` folder left by it is set aside, never mixed in: a T2I
sidecar says `"graph": "qwen_image_t2i"`, an Edit one does not.

Layout, unchanged for cutout and place:
    outputs/game-assets/<char>/renders/<category>_<NN>_<pose>/shot_00_s<seed>.png (+ .json)
"""

from __future__ import annotations

import json
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


def render_pack(cfg: dict, client, character: str, plan: dict, out_root: Path, *,
                lora_path: str, negative: str, ref=None, only: set[str] | None = None,
                seed: int | None = None, log=print) -> list[dict]:
    """Every look of the plan (or `only` those) through T2I. A look whose shot is
    already on disk is skipped - a re-roll drops the old file first. `seed`
    replaces the per-look seed, for a re-roll of one look. Returns the
    sidecars, one per look rendered or found."""
    from ..gates.identity import cosine, embed_image  # noqa: PLC0415
    from .adherence import check, measure  # noqa: PLC0415
    from .render import pose_fields, shot_prompt, t2i_workflow  # noqa: PLC0415

    root = renders_root(out_root, character)
    retire_other_renders(root, log)
    root.mkdir(parents=True, exist_ok=True)
    out, fails = [], Counter()
    for i, slot in enumerate(plan_slots(plan)):
        if only is not None and slot["id"] not in only:
            continue
        d = root / slot_dirname(slot)
        d.mkdir(exist_ok=True)
        s = seed if seed is not None else seed_for(i)
        dest = d / f"shot_00_s{s}.png"
        prompt = shot_prompt(character, slot, plan.get("trigger"), backdrop=STUDIO_BACKDROP)
        try:
            if not dest.exists():
                files = client.outputs(client.wait(client.submit(
                    t2i_workflow(cfg, prompt, s, f"pack/{character}/{slot['id']}",
                                 lora_path=lora_path, negative=negative, width=W, height=H)),
                    timeout_s=3600))
                if not files:
                    log(f"  {slot['id']}: no output")
                    continue
                client.fetch(files[0], dest)
            asked = pose_fields(character, slot)["asked"]
            try:
                adh = check(asked, measure(dest))
            except Exception as exc:  # noqa: BLE001 - a measurement, never a blocker
                adh = {"failed": [], "soft": [], "got": {}, "error": str(exc)}
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


def compare_sheet(mapping: dict, staged_outfits: Path, game_outfits: Path, out: Path, *,
                  tile: int = 240, cols: int = 4) -> tuple[Path, int]:
    """Each staged look beside what the game ships under that name today, on a
    checker, so the approval is a comparison and not a leap. Returns the sheet
    and how many game files would be overwritten."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    th = int(tile * 1.5)
    slots = mapping["slots"]
    rows = max(1, -(-len(slots) // cols))
    sheet = Image.new("RGB", (cols * (2 * tile + 12), 24 + rows * (th + 40)), (236, 236, 236))
    draw = ImageDraw.Draw(sheet)
    overwrite = 0

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
        g = game_outfits / s["file"]
        if g.is_file():
            overwrite += 1
        sheet.paste(board(staged_outfits / s["file"]), (x0, y0))
        sheet.paste(board(g if g.is_file() else None), (x0 + tile, y0))
        draw.text((x0, y0 - 13), f"{s['id']}   new  |  in the game now", fill=(30, 30, 30))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=88)
    return out, overwrite


def ship(out_root: Path, character: str, game_root: Path) -> dict:
    """The approval: copy the staged outfits into the game's folder for her,
    overwriting what is there under the same names, and record it. The ONLY
    place in the engine that writes into the game repo."""
    st = read_staged(out_root, character)
    if not st or not st.get("files"):
        raise ValueError("nothing is staged for her")
    src = Path(out_root) / "game-assets" / character / "outfits"
    dest = game_root / "src" / "assets" / "characters" / character / "outfits"
    dest.mkdir(parents=True, exist_ok=True)
    copied, overwrote = [], 0
    for name in st["files"]:
        f = src / name
        if not f.is_file():
            continue
        if (dest / name).is_file():
            overwrote += 1
        shutil.copy2(f, dest / name)
        copied.append(name)
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()), "files": copied,
           "overwrote": overwrote, "to": str(dest), "from_set": st.get("set")}
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
