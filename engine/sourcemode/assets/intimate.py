"""The lingerie gift's art: her kept lingerie-pack shots, staged and shipped
into the game's intimate folder.

Jeremy, 2026-10-29: "scaffold the process to copy the keepers into the game's
intimate folder." The game needs two things for the gift to work (read from
chillafterdark 2026-10-29):

- `intimate/lingerie_01.webp`, the one file the wardrobe button checks for
  (`hasExactCharacterAppearance`), registered in characterAppearance.js as
  `organized(<char>, 'lingerie', 'intimate/lingerie_01.webp', ['intimate'], ...)`
  - the standing keeper, since it is her "base" picture in the chat.
- `<char>_lingerie_<pose>.webp` for every kept pose: the chat looks a picture
  up by that bare file name when the pose detector (src/systems/pose.js) hears
  "kneel", "crawl", "spread your legs"... (`getCharacterImage` indexes every
  file under assets/characters by its stem, wherever it sits). They go in the
  same intimate folder.

Two steps, like the wardrobe pack. Jeremy, 2026-11-01: "They are cutout sets
... We will need the approval and pipeline to move the approved cutouts into
the game." So: every pose kept in the judge -> ONE CPU-lane job
(`scripts/eval/process_lingerie.py`) cuts the keepers out with the pack's
matte and `stage`s them as RGBA WebPs with a record under
outputs/game-assets/<char>/intimate/, never touching the game -> he approves
on the Characters tab (or `sourcemode assets lingerie <char> --ship`), and
`ship` copies the ticked files into the game repo.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

SHOOT = "lingerie"
OUTFIT = "lingerie"
BASE_FILE = "lingerie_01.webp"


def keepers(cfg: dict, character: str) -> list[dict]:
    """Her kept lingerie shots: [{id, tag, path}] in pose order. Empty when the
    shoot has not rendered or nothing is judged keep yet."""
    from ..library import find_set, shoot_kind  # noqa: PLC0415
    from .judge import judge_root  # noqa: PLC0415
    from .shoots import BY_ID  # noqa: PLC0415

    c = character.lower()
    d = find_set(cfg, c, shoot_kind(SHOOT), SHOOT)
    vp = judge_root(cfg) / "verdicts" / f"shoot_{c}_{SHOOT}.json"
    if not d.is_dir() or not vp.is_file():
        return []
    verdicts = json.loads(vp.read_text(encoding="utf-8"))
    out = []
    for slot in BY_ID[SHOOT].plan(character=c):
        p = d / f"{slot['id']}.png"
        if verdicts.get(slot["id"]) == "keep" and p.is_file():
            out.append({"id": slot["id"], "tag": slot["tag"], "path": p})
    return out


def staging_dir(out_root: Path, character: str) -> Path:
    return Path(out_root) / "game-assets" / character.lower() / "intimate"


def record_path(out_root: Path, character: str) -> Path:
    return staging_dir(out_root, character) / "intimate.json"


def read_staged(out_root: Path, character: str) -> dict | None:
    p = record_path(out_root, character)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    except ValueError:
        return None


def chat_name(character: str, tag: str) -> str:
    return f"{character.lower()}_{OUTFIT}_{tag}.webp"


def registration(character: str) -> str:
    """The characterAppearance.js row the base file needs, on Aya's pattern."""
    return (f"      organized('{character.lower()}', '{OUTFIT}', 'intimate/{BASE_FILE}', ['intimate'], "
            "{ minRelationship: 80, weight: 40 }),")


def process_due(judge_root: Path, out_root: Path, set_id: str) -> str | None:
    """Why a lingerie set should be cut out and staged now - or None. Every
    pose kept, and nothing staged since the last verdict changed: the pack's
    rule (pack.process_due), for the lingerie shoot's judge set."""
    from .judge import load_set, load_verdicts  # noqa: PLC0415

    s = load_set(judge_root, set_id)
    if not s or (s.get("meta") or {}).get("shoot") != SHOOT:
        return None
    v = load_verdicts(judge_root, set_id)
    ids = [it["id"] for it in s["items"]]
    if not ids or any(v.get(i) != "keep" for i in ids):
        return None
    st = read_staged(out_root, s["meta"]["character"])
    vp = judge_root / "verdicts" / f"{set_id}.json"
    if st and st.get("verdicts_mtime") and vp.is_file() and st["verdicts_mtime"] >= vp.stat().st_mtime - 1:
        return None
    return f"all {len(ids)} poses kept"


def stage(cfg: dict, out_root: Path, character: str, *, remover=None, log=print) -> dict:
    """Cut her keepers out - the pack's hybrid matte on the game canvas - and
    write them as the game's files under outputs: an RGBA WebP per pose by its
    chat name, and the standing one (else the first) again as the base file,
    with a record and the registration line. Replaces an earlier staging;
    never touches the game. Loads the matte model: run it from the queue."""
    from .cutout import cutout_batch, hybrid_remover  # noqa: PLC0415
    from .judge import judge_root  # noqa: PLC0415

    c = character.lower()
    kept = keepers(cfg, c)
    if not kept:
        raise ValueError(f"no kept lingerie shots for {c} - render the Lingerie pack and judge it first")
    d = staging_dir(out_root, c)
    if d.is_dir():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    size = tuple((cfg.get("assets") or {}).get("game_size", (1024, 1536)))
    cuts = cutout_batch([k["path"] for k in kept], d / "_cutouts", remover=remover or hybrid_remover(),
                        model="hybrid", size=size, webp=True, log=log)
    files: dict[str, str] = {}
    flagged: dict[str, list] = {}

    def put(name: str, k: dict, cut: dict) -> None:
        shutil.copy2(cut["outputs"]["webp"], d / name)
        files[name] = str(k["path"])
        if cut["report"]["flags"]:
            flagged[name] = cut["report"]["flags"]

    for k, cut in zip(kept, cuts):
        put(chat_name(c, k["tag"]), k, cut)
    bi = next((i for i, k in enumerate(kept) if k["tag"] == "standing"), 0)
    put(BASE_FILE, kept[bi], cuts[bi])
    (d / "registration.js").write_text(registration(c) + "\n", encoding="utf-8")
    vp = judge_root(cfg) / "verdicts" / f"shoot_{c}_{SHOOT}.json"
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()), "character": c,
           "set": str(kept[0]["path"].parent), "files": files, "base_from": kept[bi]["tag"],
           "poses": [k["tag"] for k in kept], "flagged": flagged, "cutout": True,
           "verdicts_mtime": vp.stat().st_mtime if vp.is_file() else None,
           "registration": registration(c)}
    record_path(out_root, c).write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec


def tile(out_root: Path, character: str, name: str, width: int = 360) -> Path | None:
    """A small RGBA WebP of one staged file for the Characters tab, cached
    beside the staging (never in the game)."""
    from PIL import Image  # noqa: PLC0415

    st = read_staged(out_root, character)
    if not st or name not in (st.get("files") or {}):
        return None
    src = staging_dir(out_root, character) / name
    if not src.is_file():
        return None
    cache = staging_dir(out_root, character) / "_thumbs" / f"{src.stem}_{width}.webp"
    if cache.is_file() and cache.stat().st_mtime >= src.stat().st_mtime:
        return cache
    im = Image.open(src).convert("RGBA")
    im.thumbnail((width, width * 2))
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    im.save(tmp, "WEBP", quality=80)
    tmp.replace(cache)
    return cache


def discard(out_root: Path, character: str) -> bool:
    """Drop the staging record; the files stay on disk, nothing in the game changes."""
    p = record_path(out_root, character)
    if not p.is_file():
        return False
    p.unlink()
    return True


def ship(out_root: Path, character: str, game_root: Path, keep: list[str] | None = None) -> dict:
    """His approval: copy the staged files into the game's intimate folder for
    her, overwriting same-named files, and record it. `keep` is the file names
    to ship; None is all of them."""
    c = character.lower()
    st = read_staged(out_root, c)
    if not st or not st.get("files"):
        raise ValueError(f"nothing staged for {c} - stage her lingerie keepers first")
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
           "overwrote": overwrote, "to": str(dest), "skipped": [n for n in names if n not in chosen]}
    st["shipped"] = rec
    record_path(out_root, c).write_text(json.dumps(st, indent=1), encoding="utf-8")
    return rec
