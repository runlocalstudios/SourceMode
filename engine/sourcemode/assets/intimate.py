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

Two steps, like the wardrobe pack: `stage` writes the WebPs and a record
under outputs/game-assets/<char>/intimate/ and never touches the game;
`ship` copies the staged files into the game repo and is his call - the
Characters-tab approval and `ship_portrait` were the only writers before it,
and this one runs only from `sourcemode assets lingerie <char> --ship`.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

SHOOT = "lingerie"
OUTFIT = "lingerie"
BASE_FILE = "lingerie_01.webp"
QUALITY = 88          # the game's own convert-assets-webp.mjs setting


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


def stage(cfg: dict, out_root: Path, character: str) -> dict:
    """Write her keepers as the game's files under outputs - RGB WebP at the
    render's own size, one per pose by its chat name, and the standing one
    (else the first) again as the base file - with a record and the
    registration line. Replaces an earlier staging; never touches the game."""
    from PIL import Image  # noqa: PLC0415

    c = character.lower()
    kept = keepers(cfg, c)
    if not kept:
        raise ValueError(f"no kept lingerie shots for {c} - render the Lingerie pack and judge it first")
    d = staging_dir(out_root, c)
    if d.is_dir():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    files: dict[str, str] = {}

    def put(name: str, src: Path) -> None:
        im = Image.open(src).convert("RGB")
        tmp = d / (name + ".tmp")
        im.save(tmp, "WEBP", quality=QUALITY)
        tmp.replace(d / name)
        files[name] = str(src)

    for k in kept:
        put(chat_name(c, k["tag"]), k["path"])
    base = next((k for k in kept if k["tag"] == "standing"), kept[0])
    put(BASE_FILE, base["path"])
    (d / "registration.js").write_text(registration(c) + "\n", encoding="utf-8")
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()), "character": c,
           "set": str(kept[0]["path"].parent), "files": files, "base_from": base["tag"],
           "poses": [k["tag"] for k in kept], "registration": registration(c)}
    record_path(out_root, c).write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec


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
