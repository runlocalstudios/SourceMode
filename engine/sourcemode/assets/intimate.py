"""The intimate gifts' art: her kept Lingerie-pack and Pajama-pack shots, staged
and shipped into the game's intimate folder - one pipeline per pack.

Jeremy, 2026-10-29: "scaffold the process to copy the keepers into the game's
intimate folder." The game's contract (chillafterdark cd95d04, 2026-11-03):

- Both packs ship into the same folder, src/assets/characters/<char>/intimate/.
- `<outfit>_01.webp` (lingerie_01.webp, pajamas_01.webp) is her "base" picture
  in the chat: the standing keeper, else the first keeper.
- `<char>_<outfit>_<pose>.webp` for every kept pose: the chat looks a picture
  up by that bare file name when the pose detector (src/systems/pose.js) hears
  "kneel", "crawl", "turn around"... (`getCharacterImage` indexes every file
  under assets/characters by its stem, wherever it sits).
- No characterAppearance.js line any more. The game registers packs from
  src/data/intimatePacks.js, which `npm run sync:intimate` regenerates by
  scanning for the base files - so a ship runs that sync and records its
  output; a failed sync is written down, never swallowed.

Two steps, like the wardrobe pack. Jeremy, 2026-11-01: "They are cutout sets
... We will need the approval and pipeline to move the approved cutouts into
the game." So: every pose kept in the judge -> ONE CPU-lane job
(`scripts/eval/process_intimate.py <char> <outfit>`) cuts the keepers out with
the pack's matte and `stage`s them as RGBA WebPs with a record under
outputs/game-assets/<char>/intimate/, never touching the game -> he approves
on the Characters tab (or `sourcemode assets intimate <char> <outfit> --ship`),
and `ship` copies the ticked files into the game repo. Every function takes
`outfit`, "lingerie" by default, so the lingerie callers never changed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

# one row per pack: the shoot that renders it, the game's base file, and the
# staging record beside the files. The lingerie record keeps its old name so
# every staging made before the pajama pack is still found.
PACKS: dict[str, dict] = {
    "lingerie": {"shoot": "lingerie", "base": "lingerie_01.webp", "record": "intimate.json"},
    "pajamas": {"shoot": "pajamas", "base": "pajamas_01.webp", "record": "pajamas.json"},
}
SYNC_CMD = ("npm", "run", "sync:intimate")


def _pack(outfit: str) -> dict:
    try:
        return PACKS[outfit]
    except KeyError:
        raise ValueError(f"no intimate pack called {outfit!r}; one of {', '.join(PACKS)}") from None


def keepers(cfg: dict, character: str, outfit: str = "lingerie") -> list[dict]:
    """Her kept shots of the pack: [{id, tag, path}] in pose order. Empty when
    the shoot has not rendered or nothing is judged keep yet."""
    from ..library import find_set, shoot_kind  # noqa: PLC0415
    from .judge import judge_root  # noqa: PLC0415
    from .shoots import BY_ID  # noqa: PLC0415

    shoot = _pack(outfit)["shoot"]
    c = character.lower()
    d = find_set(cfg, c, shoot_kind(shoot), shoot)
    vp = judge_root(cfg) / "verdicts" / f"shoot_{c}_{shoot}.json"
    if not d.is_dir() or not vp.is_file():
        return []
    verdicts = json.loads(vp.read_text(encoding="utf-8"))
    out = []
    for slot in BY_ID[shoot].plan(character=c):
        p = d / f"{slot['id']}.png"
        if verdicts.get(slot["id"]) == "keep" and p.is_file():
            out.append({"id": slot["id"], "tag": slot["tag"], "path": p})
    return out


def staging_dir(out_root: Path, character: str) -> Path:
    """Shared by every pack, like the game's intimate folder."""
    return Path(out_root) / "game-assets" / character.lower() / "intimate"


def record_path(out_root: Path, character: str, outfit: str = "lingerie") -> Path:
    return staging_dir(out_root, character) / _pack(outfit)["record"]


def read_staged(out_root: Path, character: str, outfit: str = "lingerie") -> dict | None:
    p = record_path(out_root, character, outfit)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    except ValueError:
        return None


def chat_name(character: str, tag: str, outfit: str = "lingerie") -> str:
    return f"{character.lower()}_{outfit}_{tag}.webp"


def process_due(judge_root: Path, out_root: Path, set_id: str, outfit: str = "lingerie") -> str | None:
    """Why this pack's set should be cut out and staged now - or None. Every
    pose kept, and nothing staged since the last verdict changed: the pack's
    rule (pack.process_due), for the pack's own shoot's judge set."""
    from .judge import load_set, load_verdicts  # noqa: PLC0415

    s = load_set(judge_root, set_id)
    if not s or (s.get("meta") or {}).get("shoot") != _pack(outfit)["shoot"]:
        return None
    v = load_verdicts(judge_root, set_id)
    ids = [it["id"] for it in s["items"]]
    if not ids or any(v.get(i) != "keep" for i in ids):
        return None
    st = read_staged(out_root, s["meta"]["character"], outfit)
    vp = judge_root / "verdicts" / f"{set_id}.json"
    if st and st.get("verdicts_mtime") and vp.is_file() and st["verdicts_mtime"] >= vp.stat().st_mtime - 1:
        return None
    return f"all {len(ids)} poses kept"


def _clear_own(d: Path, out_root: Path, c: str, outfit: str) -> None:
    """Drop this pack's earlier staging only: the files its record lists, its
    base, and its own cutout and thumb folders. The other pack's staging in
    the same folder stays (a pajama staging must never erase the lingerie one)."""
    old = read_staged(out_root, c, outfit) or {}
    for name in list(old.get("files") or {}) + [_pack(outfit)["base"]]:
        p = d / name
        if p.is_file():
            p.unlink()
    for sub in (f"_cutouts_{outfit}", f"_thumbs_{outfit}"):
        if (d / sub).is_dir():
            shutil.rmtree(d / sub)


def stage(cfg: dict, out_root: Path, character: str, outfit: str = "lingerie", *, remover=None,
          log=print) -> dict:
    """Cut her keepers out - the pack's hybrid matte on the game canvas - and
    write them as the game's files under outputs: an RGBA WebP per pose by its
    chat name, and the standing one (else the first) again as the base file,
    with a record. Replaces this pack's earlier staging and no other's; never
    touches the game. Loads the matte model: run it from the queue."""
    from .cutout import cutout_batch, hybrid_remover  # noqa: PLC0415
    from .judge import judge_root  # noqa: PLC0415

    pk = _pack(outfit)
    c = character.lower()
    kept = keepers(cfg, c, outfit)
    if not kept:
        raise ValueError(f"no kept {outfit} shots for {c} - render the {outfit} pack and judge it first")
    d = staging_dir(out_root, c)
    d.mkdir(parents=True, exist_ok=True)
    _clear_own(d, out_root, c, outfit)
    size = tuple((cfg.get("assets") or {}).get("game_size", (1024, 1536)))
    cuts = cutout_batch([k["path"] for k in kept], d / f"_cutouts_{outfit}", remover=remover or hybrid_remover(),
                        model="hybrid", size=size, webp=True, log=log)
    files: dict[str, str] = {}
    flagged: dict[str, list] = {}

    def put(name: str, k: dict, cut: dict) -> None:
        shutil.copy2(cut["outputs"]["webp"], d / name)
        files[name] = str(k["path"])
        if cut["report"]["flags"]:
            flagged[name] = cut["report"]["flags"]

    for k, cut in zip(kept, cuts):
        put(chat_name(c, k["tag"], outfit), k, cut)
    bi = next((i for i, k in enumerate(kept) if k["tag"] == "standing"), 0)
    put(pk["base"], kept[bi], cuts[bi])
    vp = judge_root(cfg) / "verdicts" / f"shoot_{c}_{pk['shoot']}.json"
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()), "character": c, "outfit": outfit,
           "set": str(kept[0]["path"].parent), "files": files, "base_from": kept[bi]["tag"],
           "poses": [k["tag"] for k in kept], "flagged": flagged, "cutout": True,
           "verdicts_mtime": vp.stat().st_mtime if vp.is_file() else None}
    record_path(out_root, c, outfit).write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec


def tile(out_root: Path, character: str, name: str, width: int = 360, outfit: str = "lingerie") -> Path | None:
    """A small RGBA WebP of one staged file for the Characters tab, cached
    beside the staging (never in the game)."""
    from PIL import Image  # noqa: PLC0415

    st = read_staged(out_root, character, outfit)
    if not st or name not in (st.get("files") or {}):
        return None
    src = staging_dir(out_root, character) / name
    if not src.is_file():
        return None
    cache = staging_dir(out_root, character) / f"_thumbs_{outfit}" / f"{src.stem}_{width}.webp"
    if cache.is_file() and cache.stat().st_mtime >= src.stat().st_mtime:
        return cache
    im = Image.open(src).convert("RGBA")
    im.thumbnail((width, width * 2))
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    im.save(tmp, "WEBP", quality=80)
    tmp.replace(cache)
    return cache


def discard(out_root: Path, character: str, outfit: str = "lingerie") -> bool:
    """Drop the staging record; the files stay on disk, nothing in the game changes."""
    p = record_path(out_root, character, outfit)
    if not p.is_file():
        return False
    p.unlink()
    return True


def run_sync(game_root: Path) -> dict:
    """`npm run sync:intimate` in the game repo, which rewrites
    src/data/intimatePacks.js from the base files on disk. Never raises: a
    missing npm or a non-zero exit comes back as {ok: False, output}, for the
    ship record to carry. Windows ships npm as npm.cmd, hence `which`."""
    exe = shutil.which(SYNC_CMD[0])
    cmd = [exe or SYNC_CMD[0], *SYNC_CMD[1:]]
    shown = " ".join(SYNC_CMD)
    if not exe:
        return {"ok": False, "cmd": shown, "output": f"{SYNC_CMD[0]} not found on PATH - run `{shown}` in {game_root}"}
    try:
        r = subprocess.run(cmd, cwd=str(game_root), capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "cmd": shown, "output": f"{type(exc).__name__}: {exc}"}
    out = "\n".join(x.strip() for x in (r.stdout or "", r.stderr or "") if x and x.strip())
    return {"ok": r.returncode == 0, "cmd": shown, "output": out or f"exit {r.returncode}"}


def ship(out_root: Path, character: str, game_root: Path, keep: list[str] | None = None,
         outfit: str = "lingerie") -> dict:
    """His approval: copy the staged files into the game's intimate folder for
    her, overwriting same-named files, run the game's sync so the pack is
    registered, and record both. `keep` is the file names to ship; None is all
    of them."""
    c = character.lower()
    st = read_staged(out_root, c, outfit)
    if not st or not st.get("files"):
        raise ValueError(f"nothing staged for {c} - stage her {outfit} keepers first")
    names = list(st["files"])
    chosen = names if keep is None else [n for n in names if n in set(keep)]
    if keep is not None and set(keep) - set(names):
        raise ValueError("not staged: " + ", ".join(sorted(set(keep) - set(names))))
    if not chosen:
        raise ValueError("nothing chosen to ship")
    src = staging_dir(out_root, c)
    dest = Path(game_root) / "src" / "assets" / "characters" / c / "intimate"
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
           "overwrote": overwrote, "to": str(dest), "skipped": [n for n in names if n not in chosen],
           "sync": run_sync(game_root)}
    st["shipped"] = rec
    record_path(out_root, c, outfit).write_text(json.dumps(st, indent=1), encoding="utf-8")
    return rec
