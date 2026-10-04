"""Blind judging of candidate renders, served by the engine monitor.

The identity metric does not track Jeremy's eye (his keepers scored the same as
his rejects), so every experiment that asks "which lever raises the hit rate"
has to be scored by him. Contact sheets are too small to judge from and typing
numbers back is error-prone, so: one image at a time, full height, arm hidden,
one key to keep or reject. The tally per arm falls out of the verdicts.

    outputs/judge/sets/<set>.json       manifest: items with their (hidden) arm, a fixed shuffled order
    outputs/judge/verdicts/<set>.json   {item_id: "keep" | "reject"}

    GET  /judge                          the page
    GET  /judge/sets                     [{id, title, n, judged}]
    GET  /judge/set/{set}                items in blind order + saved verdicts (no arms)
    GET  /judge/file?set=&id=            an item image (paths come from the manifest, never the query)
    GET  /judge/ref?set=                 the set's reference photo, if any
    POST /judge/set/{set}/verdict        {item, verdict} -> saved
    GET  /judge/set/{set}/summary        per-arm keep rate (this one reveals the arms)
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

from ..monitor.ui import page

VERDICTS = ("keep", "reject")

#: `"ash_v2 epoch 16"` -> 16. Anchored at the END, which is what makes
#: `"rank32 epoch 10 (current best)"` (gabi_r64_stage2) NOT an epoch arm: a
#: set that does not follow the convention falls back to the generic arm
#: table rather than being guessed at.
EPOCH_RE = re.compile(r"(?:^|\s)epoch\s+(\d+)\s*$")

#: Within this of the top Wilson lower bound is a TIE, and the earlier epoch is
#: the safer pick (less overfit) - the same rule and the same reason as
#: train/select.py's tie-break and its Bianca note. The NUMBER is not borrowed:
#: select.py's SCORE_TOLERANCE = 0.01 is a noise floor on an IDENTITY SCORE, and
#: this is a lower bound on a KEEP RATE - a different quantity on a different
#: scale. 0.05 is set against this project's own recorded finding that a
#: 24-epoch keep-rate scan puts its entire spread inside ~0.038, so a low-bound
#: separation under 0.05 is not a result.
TIE_LOW = 0.05


def content_hash(path: Path) -> str | None:
    """Short content digest of an item image, or None if it is not readable.

    Verdicts are keyed by item id, so regenerating a set under the same ids used
    to silently inherit judgements made on different pixels. That happened three
    times in one session - once on a jojo epoch sweep where verdicts recorded at
    17:44 were still attached to images rewritten at 19:09.
    """
    try:
        h = hashlib.sha1(usedforsecurity=False)
        with Path(path).open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except OSError:
        return None


def judge_root(cfg: dict) -> Path:
    from ..config import ENGINE_ROOT  # noqa: PLC0415

    root = Path(cfg.get("assets", {}).get("judge", "outputs/judge"))
    return root if root.is_absolute() else ENGINE_ROOT / root


def make_set(root: Path, set_id: str, title: str, items: list[dict], *, question: str = "",
             reference: str | Path | None = None, seed: int = 0, priority: int = 50) -> Path:
    """Write a manifest. items: [{id, path, arm, group}]; ids unique within the set.

    The blind order is shuffled once here and stored, so revisits show the same
    sequence and the arm never leaks through position.
    """
    ids = [it["id"] for it in items]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{set_id}: duplicate item ids")
    order = list(ids); random.Random(seed).shuffle(order)
    prior = {it["id"]: it.get("hash") for it in (load_set(root, set_id) or {}).get("items", [])}
    rows = [{**it, "path": str(it["path"]), "hash": content_hash(it["path"])} for it in items]
    d = root / "sets"; d.mkdir(parents=True, exist_ok=True)
    out = d / f"{set_id}.json"
    out.write_text(json.dumps({
        "id": set_id, "title": title, "question": question, "priority": priority,
        "reference": str(reference) if reference else None,
        "items": rows, "order": order,
    }, indent=1), encoding="utf-8")
    drop_stale_verdicts(root, set_id, {r["id"]: r["hash"] for r in rows}, prior)
    return out


def drop_stale_verdicts(root: Path, set_id: str, now: dict, prior: dict) -> list[str]:
    """Forget verdicts whose image changed content since they were recorded.

    Only acts where both digests are known: a manifest written before hashing
    existed carries no prior hash, and an unreadable file yields none, so those
    verdicts are left alone rather than thrown away on a guess.
    """
    v = load_verdicts(root, set_id)
    stale = [i for i, h in prior.items()
             if h and now.get(i) and now[i] != h and i in v]
    if stale:
        # The tally is appended BEFORE the verdicts are dropped: this is the only
        # place a judged result can vanish, and nothing used to keep it.
        append_result(root, set_id, reason=f"{len(stale)} images re-rendered")
        for i in stale:
            v.pop(i, None)
        d = root / "verdicts"; d.mkdir(parents=True, exist_ok=True)
        (d / f"{set_id}.json").write_text(json.dumps(v, indent=1), encoding="utf-8")
    return stale


def load_set(root: Path, set_id: str) -> dict | None:
    if not set_id or "/" in set_id or "\\" in set_id or set_id.startswith("."):
        return None
    p = root / "sets" / f"{set_id}.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_verdicts(root: Path, set_id: str) -> dict:
    p = root / "verdicts" / f"{set_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def list_sets(root: Path) -> list[dict]:
    """Unfinished sets first, then finished ones.

    The list grows with every experiment and became hard to scan, so ordering is
    by what still needs work: partially judged sets lead (closest to done first),
    then untouched ones, then everything complete. `done` lets the page draw a
    divider at the boundary.
    """
    out = []
    for p in sorted((root / "sets").glob("*.json")) if (root / "sets").exists() else []:
        s = json.loads(p.read_text(encoding="utf-8"))
        v = load_verdicts(root, s["id"])
        n = len(s["items"])
        judged = sum(1 for it in s["items"] if it["id"] in v)
        # `sub`, `status` and `group` are what the picker shows instead of a bare
        # count, and they come from one place so both review pages read alike.
        left = n - judged
        if judged >= n:
            status, group = "done", "done"
            sub = f"{n} judged"
        elif judged:
            status, group = "you", "progress"
            sub = f"{judged} of {n} judged · {left} left"
        else:
            status, group = "you", "needs"
            sub = f"{n} to judge"
        out.append({"id": s["id"], "title": s["title"], "question": s.get("question", ""),
                    "priority": s.get("priority", 50), "n": n, "judged": judged,
                    "done": judged >= n,
                    "sub": sub, "status": status, "group": group})

    def order(s):
        if s["done"]:
            return (2, s["priority"], s["id"])
        started = s["judged"] > 0
        # started-but-unfinished first, most-complete leading; then untouched
        return (0 if started else 1,
                -(s["judged"] / s["n"]) if started else 0,
                s["priority"], s["id"])

    return sorted(out, key=order)


def set_payload(root: Path, set_id: str) -> dict | None:
    """What the page gets: items in blind order, arms stripped.

    An item whose image is not on disk is LEFT OUT and counted instead. A
    re-roll deletes the rejected file before it renders the replacement, so
    there is always a window where the manifest names a file that is not
    there; on 2026-10-04 that window was held open by hand and the page served
    ten broken images, every one of which he dutifully rejected. A verdict is a
    record of what he saw, so an item he cannot see must not be judgeable.
    """
    s = load_set(root, set_id)
    if s is None:
        return None
    here = {it["id"] for it in s["items"] if Path(it["path"]).is_file()}
    pending = [i for i in s["order"] if i not in here]
    return {"id": s["id"], "title": s["title"], "question": s.get("question", ""),
            "has_reference": bool(s.get("reference")),
            "items": [{"id": i} for i in s["order"] if i in here],
            "pending": len(pending),
            "verdicts": {k: v for k, v in load_verdicts(root, set_id).items() if k in here}}


def item_path(root: Path, set_id: str, item_id: str) -> Path | None:
    s = load_set(root, set_id)
    if s is None:
        return None
    for it in s["items"]:
        if it["id"] == item_id:
            p = Path(it["path"])
            return p if p.is_file() else None
    return None


def record_verdict(root: Path, set_id: str, item_id: str, verdict: str | None) -> dict:
    """verdict None clears the item (undo). Returns the set's verdicts."""
    s = load_set(root, set_id)
    if s is None:
        raise KeyError(set_id)
    row = next((it for it in s["items"] if it["id"] == item_id), None)
    if row is None:
        raise KeyError(item_id)
    # The hard guard, under every client: no verdict on an image that is not
    # there. Clearing one (verdict=None) stays allowed, because undoing a
    # verdict recorded before the file went missing has to keep working.
    if verdict is not None and not Path(row["path"]).is_file():
        raise FileNotFoundError(f"{item_id}: image is not on disk - it is "
                                f"probably mid re-render")
    if verdict is not None and verdict not in VERDICTS:
        raise ValueError(verdict)
    v = load_verdicts(root, set_id)
    if verdict is None:
        v.pop(item_id, None)
    else:
        v[item_id] = verdict
    d = root / "verdicts"; d.mkdir(parents=True, exist_ok=True)
    (d / f"{set_id}.json").write_text(json.dumps(v, indent=1, sort_keys=True), encoding="utf-8")
    return v


def summary(root: Path, set_id: str) -> dict | None:
    """Keep rate per arm, plus the per-group cross-tab so paired designs can be
    read as "same seed, which arm won"."""
    s = load_set(root, set_id)
    if s is None:
        return None
    v = load_verdicts(root, set_id)
    arms: dict[str, dict] = {}
    groups: dict[str, dict[str, str]] = {}
    for it in s["items"]:
        a = arms.setdefault(it["arm"], {"arm": it["arm"], "n": 0, "judged": 0, "keep": 0})
        a["n"] += 1
        if it["id"] in v:
            a["judged"] += 1; a["keep"] += v[it["id"]] == "keep"
            groups.setdefault(str(it.get("group", "")), {})[it["arm"]] = v[it["id"]]
    for a in arms.values():
        a["rate"] = round(a["keep"] / a["judged"], 3) if a["judged"] else None
    return {"id": s["id"], "title": s["title"], "judged": len(v), "n": len(s["items"]),
            "arms": sorted(arms.values(), key=lambda a: a["arm"]), "groups": groups}



# --- the sweep as a decision -------------------------------------------------
# Everything below is pure over the manifest and the verdicts, so it is testable
# with no GPU and no renders on disk.


def epoch_arm(arm: str) -> tuple[str, int] | None:
    """`"ash_v2 epoch 16"` -> `("ash_v2", 16)`. None when an arm is not an epoch.

    The prefix is the musubi output_name, which is what names the checkpoint
    directory - and it is NOT always the dataset (`bianca_lr2b epoch 25` lives
    under bianca_v2/lora_bianca_lr2b/).

    The prefix may be EMPTY: epochs_priyanka.json uses a bare `epoch 12`, and
    there the filename supplies the identity. So callers must test
    `is not None`, never truthiness.

    Digits are not assumed to be padded, because t2i_epochs_sunny writes
    `epoch 5` while coarse_sunny_r32 writes `epoch 04`.
    """
    m = EPOCH_RE.search(arm or "")
    if not m:
        return None
    return arm[: m.start()].strip(), int(m.group(1))


def epoch_sweep_name(doc: dict) -> str | None:
    """The single output_name this manifest sweeps, or None if it is not an
    epoch sweep. Every arm must parse as an epoch AND agree on one prefix."""
    items = doc.get("items") or []
    if not items:
        return None
    names = set()
    for it in items:
        parsed = epoch_arm(it.get("arm", ""))
        if parsed is None:
            return None
        names.add(parsed[0])
    return names.pop() if len(names) == 1 else None


def sweep_sets_for(root: Path, dataset: str) -> list[dict]:
    """Every epoch sweep for `dataset`, newest first.

    PATTERN to narrow, ARM GRAMMAR to decide. Resolving on
    `dense_<ds>_asset.json` alone - which is what queue_page._rate() does - is
    wrong on the real disk: of 29 `dense_*` sets only 6 carry `_asset`, and
    `dense_ash_v2.json`, `dense_geena_v2.json` and `dense_trina_v2.json` are
    full 90-item epoch sweeps with no suffix at all. So the filename is used
    only to avoid opening all 88 manifests on a poll, and the decision is the
    arm grammar, which is exact.

    A manifest that will not parse is skipped, never fatal - unlike
    `list_sets()`, which reads `s["items"]` unguarded.
    """
    d = Path(root) / "sets"
    if not d.is_dir():
        return []
    cands: dict[str, Path] = {}
    for p in [d / f"dense_{dataset}.json", d / f"dense_{dataset}_asset.json",
              d / f"dense_{dataset}_fav.json", *sorted(d.glob(f"*{dataset}*.json"))]:
        if p.is_file():
            cands.setdefault(p.name, p)
    out = []
    for p in cands.values():
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        name = epoch_sweep_name(doc)
        if name is None:
            continue
        out.append({"id": doc.get("id") or p.stem,
                    "output_name": name or dataset,
                    "title": doc.get("title") or p.stem,
                    "mtime": p.stat().st_mtime,
                    "epochs": sorted({epoch_arm(i["arm"])[1] for i in doc["items"]})})
    out.sort(key=lambda r: -r["mtime"])
    return out


def sweep_set_for(root: Path, dataset: str) -> dict | None:
    """The newest epoch sweep for `dataset`, or None."""
    rows = sweep_sets_for(root, dataset)
    return rows[0] if rows else None


def wilson_low(keep: int, n: int, z: float = 1.0) -> float:
    """Lower bound of the keep rate at ~68% (z=1).

    Ten scenes per epoch is thin enough that ranking on the raw rate ranks
    noise: 8/10 and 7/10 are a coin flip. This penalises the thin arms honestly
    and puts the number in its own column, rather than letting the sort order
    assert a winner the data does not support.
    """
    import math  # noqa: PLC0415

    if n <= 0:
        return 0.0
    p, z2 = keep / n, z * z
    num = p + z2 / (2 * n) - z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return max(0.0, num / (1 + z2 / n))


def _dataset_of_set(doc: dict, output_name: str) -> str:
    """Which lora-dataset this sweep belongs to.

    The set id is `dense_<ds>[_asset|_fav]`, which is the only place the DATASET
    appears; the arm carries the OUTPUT_NAME, and they differ (bianca_v2 vs
    bianca_lr2b). Falls back to the output_name when the id does not follow the
    convention.
    """
    sid = str(doc.get("id") or "")
    for pre in ("dense_", "coarse_"):
        if sid.startswith(pre):
            body = sid[len(pre):]
            for suf in ("_asset", "_fav"):
                if body.endswith(suf):
                    body = body[: -len(suf)]
            return body or output_name
    return output_name


def _character_of(dataset: str) -> str:
    """`ash_v2` -> `ash`. The same rule queue_page.character_of() uses."""
    from ..monitor.queue_page import character_of  # noqa: PLC0415

    return character_of(dataset)


def epoch_board(root: Path, set_id: str, *, outputs: Path | None = None) -> dict | None:
    """The sweep as a decision: epochs ranked by low bound, with the scene grid.

    Returns None when the arms are not epochs, which is how a wardrobe or an A/B
    set falls back to the generic per-arm bars instead of being rendered as
    something it is not.

    `outputs` is used only to resolve checkpoint paths and to read the existing
    choice; a missing checkpoint never changes a row's rank.
    """
    from ..train.epochs import checkpoint_for, load_choice  # noqa: PLC0415

    s = summary(root, set_id)
    if s is None:
        return None
    doc = load_set(root, set_id) or {}
    out_name = epoch_sweep_name(doc)
    if out_name is None:
        return None
    parsed = [(epoch_arm(a["arm"]), a) for a in s["arms"]]
    if any(pr is None for pr, _ in parsed):
        return None
    dataset = _dataset_of_set(doc, out_name)
    rows = []
    for pr, a in parsed:
        epoch = pr[1]
        rows.append({
            "epoch": epoch, "arm": a["arm"], "keep": a["keep"],
            "judged": a["judged"], "n": a["n"], "rate": a["rate"],
            "low": round(wilson_low(a["keep"], a["judged"]), 3),
            # summary()["groups"] is {scene: {arm: verdict}} and is populated
            # only from JUDGED items, so a half-judged sweep has holes, not zeros
            "grid": {g: v[a["arm"]] for g, v in s["groups"].items() if a["arm"] in v},
            "lora": (checkpoint_for(outputs, dataset, out_name, epoch)
                     if outputs else None),
            "tied": False, "safer": False,
        })
    # Ranked by the LOW BOUND, not the rate. Ties break toward the earlier
    # epoch, which is also the numeric ordering summary() cannot give us: its
    # arms are sorted lexicographically, so an unpadded sweep arrives as
    # epoch 10, 15, 20, 5.
    rows.sort(key=lambda r: (-r["low"], r["epoch"]))
    if rows:
        top = rows[0]["low"]
        for r in rows:
            r["tied"] = (top - r["low"]) <= TIE_LOW
        tied = [r for r in rows if r["tied"]]
        min(tied, key=lambda r: r["epoch"])["safer"] = True
    character = _character_of(dataset)
    choice = load_choice(outputs, character) if outputs else None
    return {"set": set_id, "title": s["title"], "output_name": out_name,
            "dataset": dataset, "character": character,
            "judged": s["judged"], "n": s["n"], "tie_low": TIE_LOW,
            "scenes": sorted(s["groups"], key=lambda g: (len(g), g)),
            "chosen": ({"epoch": choice["epoch"], "at": choice["at"]}
                       if choice and choice.get("from_set") == set_id else None),
            "arms": rows}


# --- a judged set keeps its result -------------------------------------------


def results_path(root: Path, set_id: str) -> Path:
    return Path(root) / "results" / f"{set_id}.jsonl"


def append_result(root: Path, set_id: str, *, reason: str) -> dict | None:
    """Append the CURRENT tally to outputs/judge/results/<set>.jsonl.

    Called from drop_stale_verdicts() BEFORE it clears anything - the one place
    in the product where a judged result can vanish, and the place that already
    knows it is about to.
    """
    s = summary(root, set_id)
    if s is None or not s["judged"]:
        return None
    rec = {"closed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "reason": reason, "n": s["n"], "judged": s["judged"],
           "arms": [{k: a[k] for k in ("arm", "n", "judged", "keep", "rate")}
                    for a in s["arms"]]}
    p = results_path(root, set_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + chr(10))
    return rec


def history(root: Path, set_id: str) -> dict:
    """Past tallies for this set id, newest first. This is what makes a
    re-rendered set comparable to the thing it replaced."""
    p = results_path(root, set_id)
    runs = []
    if p.is_file():
        with p.open(encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    runs.append(json.loads(line))
                except ValueError:
                    continue
    return {"set": set_id, "runs": list(reversed(runs))}

OWN_CSS = r"""
html,body{height:100%;margin:0;padding:0;overflow:hidden;background:var(--photo)}
#hair{position:absolute;left:0;right:0;top:0;z-index:12}
#pick{position:absolute;z-index:12;top:var(--s3);left:var(--s3);
  display:flex;align-items:center;gap:7px;min-height:30px;padding:0 10px;
  max-width:min(62vw,380px);background:var(--g1);opacity:.92;
  border:1px solid var(--g4);border-radius:var(--rp);color:var(--g7);
  font:var(--t-small);font-weight:600;font-variant-numeric:tabular-nums;
  cursor:pointer;-webkit-tap-highlight-color:transparent;
  transition:opacity var(--m-base) var(--ease)}
#pick .num{color:var(--g9)}
#pick #setname{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#pick.dim{opacity:.25}
#stage{position:absolute;inset:0;display:flex;align-items:center;
  justify-content:center;touch-action:none;background:var(--photo)}
#imgA,#imgB{position:absolute;max-width:100%;max-height:100%;object-fit:contain;
  will-change:opacity,transform;transition:opacity var(--m-fade) linear;
  transform-origin:50% 50%}
#imgB{opacity:0}
#stage[data-z="1"] #imgA,#stage[data-z="1"] #imgB{
  transition:transform var(--m-base) var(--ease)}
#ref{position:absolute;z-index:14;max-height:22vh;max-width:30vw;cursor:pointer;
  border:1px solid var(--g5);border-radius:var(--r1);opacity:.94;
  transition:max-height var(--m-base) var(--ease),max-width var(--m-base) var(--ease)}
#ref.c0{right:var(--s3);bottom:calc(var(--thumb) + var(--s5) + var(--safe-b))}
#ref.c1{left:var(--s3);bottom:calc(var(--thumb) + var(--s5) + var(--safe-b))}
#ref.c2{left:var(--s3);top:var(--s7)}
#ref.c3{right:var(--s3);top:var(--s7)}
#ref.peek{inset:0;margin:auto;max-height:100%;max-width:100%;z-index:16;
  border-radius:0;border-color:transparent;opacity:1}
.tap{position:fixed;z-index:15;bottom:calc(18px + var(--safe-b));
  width:var(--thumb);height:var(--thumb);border-radius:50%;border:1px solid;
  font-size:34px;line-height:1;display:flex;align-items:center;
  justify-content:center;-webkit-tap-highlight-color:transparent;
  touch-action:manipulation;cursor:pointer;
  transition:transform var(--m-fast) var(--ease)}
.tap:active{transform:scale(.9)}
#no{left:18px;background:var(--stop-bg);border-color:var(--stop-line);color:var(--stop-ink)}
#yes{right:18px;background:var(--done-bg);border-color:var(--done-line);color:var(--done-ink)}
#hint{position:fixed;z-index:13;left:50%;transform:translateX(-50%);
  bottom:var(--s4);padding:7px 14px;background:var(--g1);opacity:.9;
  border:1px solid var(--g4);border-radius:var(--rp)}
/* #results is a SIBLING of #stage, not a child: a tap on the results screen
   must never reach the stage's verdict handler. */
#results{position:fixed;inset:0;z-index:20;background:var(--g0);
  overflow:auto;display:none}
#results.on{display:block}
@media (min-width:821px){
  .tap{display:none}
  #stage{cursor:pointer}
  #ref{max-height:30vh;max-width:22vw}
  #ref.c0,#ref.c1{bottom:var(--s5)}
}
"""

BODY = """
<div class="meter meter-hair" id=hair><i style="width:0"></i></div>

<button id=pick aria-haspopup=dialog>
  <span class=num id=prog></span>
  <span id=setname>loading&hellip;</span>
  <span class=chev aria-hidden=true>&#9662;</span></button>

<div id=stage>
  <img id=imgA alt="candidate render" draggable=false>
  <img id=imgB alt="" aria-hidden=true draggable=false>
  <img id=ref class=c0 draggable=false
       alt="reference photo" aria-label="reference photo: tap to move, hold to compare" hidden>
</div>
<div id=results></div>

<button class=tap id=no data-v=reject aria-label="reject">&#10007;</button>
<button class=tap id=yes data-v=keep aria-label="keep">&#10003;</button>

<div id=hint class=keys>
  <span><kbd>K</kbd> keep</span><span><kbd>X</kbd> reject</span>
  <span><kbd>&larr;</kbd><kbd>&rarr;</kbd> move</span><span><kbd>U</kbd> undo</span>
  <span><kbd>R</kbd> reference</span><span><kbd>0</kbd> reset zoom</span>
  <span><kbd>/</kbd> sets</span><span>click: left reject, right keep</span></div>
"""

OWN_JS = r"""
const $=id=>document.getElementById(id);
let cur=null, idx=0, sets=[], last=null, front='A', zoom=1, zx=0, zy=0, dimT=null;
let showRef=true, refCorner=0;
try{ refCorner=+(localStorage.getItem('refCorner')||0);
     if(localStorage.getItem('showRef')==='0') showRef=false; }catch(e){}

/* The stage gets the whole viewport: the shell hides its bottom bar rather than
   compressing a 100vh stage by 56px. */
SM.chrome('immersive');
SM.on('shown',()=>SM.chrome('immersive'));

const fileUrl=(set,id,w)=>'/judge/file?set='+encodeURIComponent(set)
  +'&id='+encodeURIComponent(id)+(w?'&w='+w:'');

/* --- the set list and the one picker ------------------------------------- */
async function loadSets(){
  try{ sets=await SM.getJSON('/judge/sets'); }
  catch(e){ return fail('Could not load the set list',e.message); }
  const firstOpen=(sets.find(s=>s.judged<s.n)||{}).id;
  /* A hash is a deep link, not a trap: honour it while that set still has work,
     otherwise fall through. With nothing left, open nothing - a completed
     104-image set must not re-open on every visit. */
  const hashed=location.hash.slice(1);
  const hs=hashed?sets.find(s=>s.id===hashed):null;
  if(hashed&&!hs) return gone(hashed,firstOpen);
  const want=(hashed&&hs&&hs.judged<hs.n)?hashed:firstOpen;
  if(!want) return nothingLeft();
  try{ await openSet(want); }
  catch(e){ fail('Could not open '+want,e.message); }
}
function openPicker(){
  SM.sheet({title:'Judge set',current:cur&&cur.id,
    items:sets.map(s=>({id:s.id,title:s.title,sub:s.sub,status:s.status,
      group:s.group,progress:s.n?s.judged/s.n:null})),
    onPick:id=>openSet(id).catch(e=>SM.toast(e.message))});
}
$('pick').onclick=openPicker;

async function openSet(id){
  const r=await fetch('/judge/set/'+encodeURIComponent(id),{cache:'no-store'});
  if(!r.ok) throw new Error('HTTP '+r.status);
  cur=await r.json();
  location.hash=id;
  $('results').classList.remove('on');
  $('setname').textContent=cur.title||cur.id;
  if(cur.pending) SM.toast(cur.pending+' shot'+(cur.pending===1?'':'s')
    +' still rendering - not shown yet');
  const ref=$('ref');
  ref.hidden=true;
  if(cur.has_reference) ref.src='/judge/ref?set='+encodeURIComponent(id);
  idx=cur.items.findIndex(it=>!(it.id in cur.verdicts));
  if(idx<0) idx=cur.items.length;
  show();
}

/* --- the stage ----------------------------------------------------------- */
async function show(){
  if(!cur) return;
  if(idx>=cur.items.length) return results();
  $('results').classList.remove('on');
  for(const id of ['yes','no','pick','hair']) $(id).style.visibility='';
  const it=cur.items[idx];
  const back=$('img'+(front==='A'?'B':'A')), fore=$('img'+front);
  back.dataset.big='';
  back.src=fileUrl(cur.id,it.id);
  try{ await back.decode(); }catch(e){}   /* never show a half-painted frame */
  back.style.opacity=1; fore.style.opacity=0;
  front=front==='A'?'B':'A';
  resetZoom();
  $('prog').textContent=(idx+1)+'/'+cur.items.length;
  $('hair').firstElementChild.style.width=(idx/cur.items.length*100)+'%';
  const ref=$('ref');
  ref.className='c'+refCorner;
  ref.hidden=!(showRef&&cur.has_reference);
  SM.ctx({title:cur.title,sub:(idx+1)+' of '+cur.items.length,
          status:'live',progress:idx/cur.items.length});
  for(const n of [1,2]){            /* two ahead, so a tap never stalls */
    const nx=cur.items[idx+n];
    if(nx){ const p=new Image(); p.src=fileUrl(cur.id,nx.id); }
  }
  dim();
}
/* the picker fades out of the way while judging, and comes back on any move */
function dim(){
  $('pick').classList.remove('dim');
  clearTimeout(dimT);
  dimT=setTimeout(()=>$('pick').classList.add('dim'),2500);
}

async function verdict(v){
  if(!cur||idx>=cur.items.length||zoom>1) return;   /* zoomed = looking, not judging */
  const it=cur.items[idx];
  last={item:it.id,at:idx,prev:cur.verdicts[it.id]||null};
  cur.verdicts[it.id]=v; idx++; show();              /* the thumb never waits */
  if(navigator.vibrate) navigator.vibrate(8);
  SM.toast(v==='keep'?'kept':'rejected',{label:'Undo',run:undo});
  try{
    cur.verdicts=await SM.postJSON(
      '/judge/set/'+encodeURIComponent(cur.id)+'/verdict',{item:it.id,verdict:v});
    checkRedo();
  }catch(e){
    /* Never let a lost write look like a recorded one. */
    delete cur.verdicts[it.id]; idx=last.at; last=null; show();
    SM.toast('That verdict did not save - '+e.message);
  }
}

/* The re-roll is queued server-side on the last verdict, not per keystroke -
   Jeremy, 2026-10-04: "wait until the whole set has been judged until you
   determine which shots need to be regenerated." This only SAYS so. */
async function checkRedo(){
  if(!cur||Object.keys(cur.verdicts).length<cur.items.length) return;
  let d; try{ d=await SM.getJSON('/judge/set/'+encodeURIComponent(cur.id)+'/redo'); }
  catch(e){ return; }
  if(d.advanced){
    /* Candidates that already existed: nothing was queued, and the set now has
       unjudged items again. Reload rather than telling him to wait. */
    SM.toast(d.advanced+' reject'+(d.advanced===1?'':'s')+' swapped for the next'
      +' candidate'+(d.queued?' - '+d.n_render+' out of candidates, queued':''));
    return openSet(cur.id);
  }
  if(!d.queued||!d.n) return;
  SM.toast(d.n+' reject'+(d.n===1?'':'s')+' queued to re-roll',
    {label:'Open the queue',run:()=>SM.nav('gpu')});
  SM.recount();
}

async function undo(){
  if(!last) return;
  const at=last.at, item=last.item, prev=last.prev; last=null;
  SM.hideToast();
  idx=at;
  /* `verdict: null` CLEARS it. record_verdict() has supported that since it was
     written and nothing ever called it: the old back button was idx--, which
     stepped the index and left the verdict standing. */
  const snapshot=cur.verdicts[item]||null;
  if(prev===null) delete cur.verdicts[item]; else cur.verdicts[item]=prev;
  show();
  try{
    cur.verdicts=await SM.postJSON(
      '/judge/set/'+encodeURIComponent(cur.id)+'/verdict',{item:item,verdict:prev});
  }catch(e){
    if(snapshot) cur.verdicts[item]=snapshot; else delete cur.verdicts[item];
    show(); SM.toast('Could not undo - '+e.message);
  }
}

/* --- zoom: the tool whose job is "is this her" can finally show her face ---
   2.5x anchored on the tap, the w=1600 copy swapped in, one-finger pan.
   web_copy() caches per width and PIL's thumbnail() never upscales, so on the
   real 1024x1536 renders this is full native resolution. */
const Z=2.5;
function setZoom(z,px,py){
  const s=$('stage'); zoom=z;
  if(z>1){
    const img=$('img'+(front==='A'?'B':'A'));
    if(!img.dataset.big){ img.dataset.big='1';
      img.src=fileUrl(cur.id,cur.items[idx].id,1600); }
    if(px!=null){ const r=s.getBoundingClientRect();
      zx=(r.width/2-px)*(z-1)/z; zy=(r.height/2-py)*(z-1)/z; }
  } else { zx=zy=0; }
  s.dataset.z=z>1?1:0;
  for(const id of ['imgA','imgB'])
    $(id).style.transform='translate('+zx+'px,'+zy+'px) scale('+z+')';
}
function resetZoom(){ setZoom(1); }

let lastTap=0, panFrom=null;
$('stage').addEventListener('pointerdown',e=>{
  dim();
  const t=Date.now();
  if(t-lastTap<300){ lastTap=0; return setZoom(zoom>1?1:Z,e.clientX,e.clientY); }
  lastTap=t;
  if(zoom>1){ panFrom={x:e.clientX,y:e.clientY,zx:zx,zy:zy};
    $('stage').setPointerCapture(e.pointerId); }
});
$('stage').addEventListener('pointermove',e=>{
  if(!panFrom) return;
  zx=panFrom.zx+(e.clientX-panFrom.x); zy=panFrom.zy+(e.clientY-panFrom.y);
  for(const id of ['imgA','imgB'])
    $(id).style.transform='translate('+zx+'px,'+zy+'px) scale('+zoom+')';
});
$('stage').addEventListener('pointerup',e=>{
  if(panFrom){ panFrom=null; return; }
  if(zoom>1) return;                        /* a tap while zoomed never judges */
  if(window.matchMedia('(min-width:821px)').matches)
    verdict(e.clientX < window.innerWidth/2 ? 'reject' : 'keep');
});

/* --- reference: tap = corner, press = compare --------------------------- */
function toggleRef(){
  showRef=!showRef;
  try{ localStorage.setItem('showRef',showRef?'1':'0'); }catch(e){}
  show();
}
(function(){
  const r=$('ref'); let t=null, peeked=false;
  const peek=on=>{ r.classList.toggle('peek',on); };
  r.addEventListener('click',e=>{
    e.stopPropagation();
    if(peeked){ peeked=false; return; }
    refCorner=(refCorner+1)%4;
    try{ localStorage.setItem('refCorner',refCorner); }catch(e){}
    show();
  });
  const down=()=>{ t=setTimeout(()=>{ peeked=true; peek(true); },450); };
  const up=()=>{ clearTimeout(t); peek(false); };
  r.addEventListener('pointerdown',e=>{ e.stopPropagation(); down(); });
  r.addEventListener('pointerup',up);
  r.addEventListener('pointercancel',up);
  r.addEventListener('pointerleave',up);
})();

addEventListener('keydown',e=>{
  if(e.target.tagName==='INPUT') return;
  const k=e.key.toLowerCase();
  if(k==='k'||k==='enter') verdict('keep');
  else if(k==='x'||k==='j') verdict('reject');
  else if(k==='u'||k==='z') undo();
  else if(k==='0') resetZoom();
  else if(k==='arrowleft'||k==='backspace'){ if(idx>0){ idx--; show(); } }
  else if(k==='arrowright'){ if(idx<cur.items.length){ idx++; show(); } }
  else if(k==='s'){ idx=cur.items.length; show(); }
  else if(k==='/'){ e.preventDefault(); openPicker(); }
  else if(k==='r') toggleRef();
  else return;
  e.preventDefault();
});
$('no').onclick=e=>{ e.preventDefault(); verdict('reject'); };
$('yes').onclick=e=>{ e.preventDefault(); verdict('keep'); };

/* --- the finish screen: the sweep as a decision ------------------------- */
function hideStage(){
  for(const id of ['yes','no']) $(id).style.visibility='hidden';
  $('ref').hidden=true;
}
async function results(){
  hideStage();
  const box=$('results'); box.classList.add('on');
  let board=null;
  try{ board=await SM.getJSON('/judge/set/'+encodeURIComponent(cur.id)+'/epochs'); }
  catch(e){ board=null; }        /* a 404 means "not an epoch sweep", not an error */
  const s=await SM.getJSON('/judge/set/'+encodeURIComponent(cur.id)+'/summary');
  const hist=await SM.getJSON('/judge/set/'+encodeURIComponent(cur.id)+'/history')
    .catch(()=>({runs:[]}));
  sets=await SM.getJSON('/judge/sets').catch(()=>sets);
  const left=sets.filter(x=>x.judged<x.n&&x.id!==cur.id).length;
  box.innerHTML=board?epochScreen(board,hist,left):armScreen(s,hist,left);
  SM.ctx({title:cur.title,sub:s.judged+' of '+s.n+' judged',status:'done',progress:1});
}

function epochScreen(b,hist,left){
  const lead=b.arms[0];
  let rows='';
  for(const a of b.arms){
    const note=[];
    if(a.judged) note.push(a.keep+' of '+a.judged+' kept');
    const tiedWith=b.arms.filter(x=>x.tied&&x.epoch!==a.epoch).map(x=>x.epoch);
    if(a.tied&&tiedWith.length) note.push('tied with '+tiedWith.join(', '));
    if(a.safer) note.push('the earlier checkpoint, so the safer pick (less overfit)');
    rows+='<div class="arow'+(a.safer?' lead':'')+'">'
      +'<span class=ep>'+a.epoch+'</span>'
      +'<span class=track><i style="width:'+Math.round((a.rate||0)*100)+'%"></i></span>'
      +'<span class=rate>'+(a.rate==null?'&mdash;':Math.round(a.rate*100)+'%')+'</span>'
      +'<span class=low>'+a.low.toFixed(2)+'</span>'
      +(note.length?'<span class=note>'+SM.esc(note.join(' &middot; ')).replace(/&amp;middot;/g,'&middot;')+'</span>':'')
      +'</div>';
  }
  /* the cross-tab: same seed down each column */
  let head='<tr><th scope=col></th>';
  for(const sc of b.scenes) head+='<th scope=col>'+SM.esc(sc)+'</th>';
  head+='</tr>';
  let body='';
  for(const a of b.arms){
    body+='<tr'+(a.safer?' class=lead':'')+'><th scope=row>'+a.epoch+'</th>';
    for(const sc of b.scenes){
      const v=a.grid[sc];
      body+=v==='keep'?'<td class=k>&#10003;</td>'
           :v==='reject'?'<td class=r>&#10007;</td>'
           :'<td class=u>&middot;</td>';
    }
    body+='</tr>';
  }
  const dead=b.scenes.filter(sc=>b.arms.every(a=>a.grid[sc]!=='keep')
                                 &&b.arms.some(a=>a.grid[sc]));
  const chosen=b.chosen;
  const pick=chosen?b.arms.find(a=>a.epoch===chosen.epoch):null;
  const decision=chosen
    ? '<div class="card e-'+((pick&&pick.lora)?'done':'you')+'">'
      +'<div class=card-head>'+SM.pill((pick&&pick.lora)?'done':'you')
      +'<h3>Epoch '+chosen.epoch+' &mdash; chosen'+((pick&&pick.lora)?'':', checkpoint missing')+'</h3></div>'
      +'<div class=card-sub>recorded '+SM.esc(SM.ago(chosen.at))+' &middot; from '
      +SM.esc(b.set)+'</div>'
      +((pick&&pick.lora)
         ? '<div class=basis>'+SM.esc(pick.lora)+'</div>'
         : '<div class=card-sub>The record is saved with <code>"lora": null</code>.'
           +' The file is not on disk &mdash; most likely pruned.</div>')
      +'</div>'
    : '<div class="card e-done">'
      +'<div class=card-head>'+SM.pill('done')+'<h3>Epoch '+lead.epoch+'</h3></div>'
      +'<div class=card-sub>'+lead.keep+' of '+lead.judged+' kept &middot; low est. '
      +lead.low.toFixed(2)+'</div>'
      +(lead.lora?'<div class=basis>'+SM.esc(lead.lora)+'</div>'
                 :'<div class=card-sub>No checkpoint on disk for this epoch.</div>')
      +'<div class=card-foot><button class="btn btn-primary btn-lg" data-act=use'
      +' data-ep="'+lead.epoch+'">Use epoch '+lead.epoch+'</button></div>'
      +'<div class=basis>Recorded in outputs/epoch-choices/'+SM.esc(b.character)
      +'.json with the evidence it was chosen on. Nothing starts; nothing is copied.</div>'
      +'</div>';
  return '<div class=wrap><div class=col-main>'
    +'<h2>Epoch sweep &mdash; '+SM.esc(b.character||b.dataset)+'</h2>'
    +'<div class=card><div class=card-head>'+SM.pill(b.judged>=b.n?'done':'you')
    +'<h3>'+b.judged+' of '+b.n+' judged</h3></div>'
    +'<div class=board>'+rows+'</div>'
    +'<div class=basis>Ranked by <b>low est.</b> &mdash; the Wilson lower bound of the'
    +' keep rate at n='+(lead.judged||0)+' per arm, not the raw rate. Within '
    +b.tie_low+' of the top is a tie, and the earlier epoch is the safer pick.</div>'
    +'</div>'
    +'<h2>Same seed, scene by scene</h2>'
    +'<div class=card><div class=gwrap><table class=sgrid>'
    +'<caption class=sr-only>keep or reject per scene, per epoch</caption>'
    +'<thead>'+head+'</thead><tbody>'+body+'</tbody></table></div>'
    +'<div class=basis>Same seed down each column.'
    +(dead.length?(' Scene'+(dead.length===1?' ':'s ')+dead.join(', ')
        +' fail'+(dead.length===1?'s':'')+' at every epoch, so that is the scene,'
        +' not the LoRA &mdash; which is the question a keep rate cannot answer.'):'')
    +'</div></div>'
    +'</div><div class=col-rail><h2>The decision</h2>'+decision
    +foot(hist,left)+'</div></div>';
}

function armScreen(s,hist,left){
  /* Not an epoch sweep: the generic per-arm bars, no board, no Use-epoch. */
  let bars='';
  const top=Math.max(...s.arms.map(a=>a.rate==null?0:a.rate));
  for(const a of s.arms)
    bars+='<div class="bar'+(a.rate!=null&&a.rate===top?' lead':'')+'">'
      +'<span class=lab>'+SM.esc(a.arm)+'</span>'
      +'<span class=track><i style="width:'+Math.round((a.rate||0)*100)+'%"></i></span>'
      +'<span class=val>'+(a.rate==null?'&mdash;':Math.round(a.rate*100)+'%')
      +' <span class=dim>'+a.keep+'/'+a.judged+'</span></span></div>';
  return '<div class=wrap><div class=col-main>'
    +'<h2>'+SM.esc(s.title)+'</h2>'
    +'<div class=card><div class=card-head>'+SM.pill(s.judged>=s.n?'done':'you')
    +'<h3>'+s.judged+' of '+s.n+' judged</h3></div>'
    +'<div class=bars>'+bars+'</div>'
    +'<div class=basis>Keep rate per arm. This set&#39;s arms are not epochs, so'
    +' there is no epoch board and nothing to record as a checkpoint choice.</div>'
    +'</div></div><div class=col-rail>'+foot(hist,left)+'</div></div>';
}

function foot(hist,left){
  const runs=(hist&&hist.runs)||[];
  let h='<div class=card-foot>'
    +(left?'<button class="btn btn-primary" data-act=nextset>Next set &middot; '
           +left+' left</button>':'')
    +'<button class="btn" data-act=restart>Review from the start</button></div>';
  if(runs.length){
    h+='<details class=report><summary>Earlier runs ('+runs.length+')</summary>';
    for(const r of runs)
      h+='<div class=basis>'+SM.esc((r.closed_at||'').slice(0,16).replace('T',' '))
        +' &middot; '+r.judged+'/'+r.n+' judged &middot; '+SM.esc(r.reason)+'</div>';
    h+='</details>';
  }
  return h;
}

$('results').addEventListener('click',async e=>{
  const b=e.target.closest('[data-act]'); if(!b) return;
  const a=b.dataset.act;
  if(a==='restart'){ idx=0; show(); return; }
  if(a==='nextset'){
    const n=sets.find(x=>x.judged<x.n&&x.id!==cur.id);
    if(n) openSet(n.id).catch(err=>SM.toast(err.message));
    else nothingLeft();
    return;
  }
  if(a==='pick'){ openPicker(); return; }
  if(a==='gpu'){ SM.nav('gpu'); return; }
  if(a==='use'){
    b.disabled=true;
    try{
      const board=await SM.getJSON('/judge/set/'+encodeURIComponent(cur.id)+'/epochs');
      const arm=board.arms.find(x=>String(x.epoch)===b.dataset.ep);
      await SM.postJSON('/epochs/'+encodeURIComponent(board.character),
        {dataset:board.dataset,output_name:board.output_name,epoch:+b.dataset.ep,
         from_set:board.set,keep:arm?arm.keep:null,n:arm?arm.judged:null,
         low:arm?arm.low:null});
      SM.toast('epoch '+b.dataset.ep+' recorded');
      results();
    }catch(err){ b.disabled=false; SM.toast(err.message); }
  }
});

/* --- the three dead ends, each of them deliberate ----------------------- */
function nothingLeft(){
  hideStage();
  $('setname').textContent='nothing to judge';
  $('prog').textContent='';
  $('results').classList.add('on');
  $('results').innerHTML='<div class=wrap><div class=col-main><div class=empty>'
    +'<b>Nothing left to judge</b>Every set is complete. Pick one from the list to'
    +' review it, or go and see what finished overnight.'
    +'<div class=btn-row><button class="btn" data-act=pick>Browse completed sets</button>'
    +'<button class="btn btn-ghost" data-act=gpu>What the card is doing</button>'
    +'</div></div></div></div>';
}
function gone(id,fallback){
  hideStage();
  $('results').classList.add('on');
  $('results').innerHTML='<div class=wrap><div class=col-main><div class=errbox>'
    +'<b>'+SM.esc(id)+' is gone</b>That set is not in the list any more.'
    +(fallback?' Opening the first set that still has work.':'')
    +'<div class=btn-row><button class="btn btn-primary" data-act=pick>Choose a set</button>'
    +'</div></div></div></div>';
  location.hash='';
  if(fallback) setTimeout(()=>openSet(fallback).catch(()=>{}),1200);
}
function fail(what,why){
  hideStage();
  $('results').classList.add('on');
  $('results').innerHTML='<div class=wrap><div class=col-main><div class=errbox>'
    +'<b>'+SM.esc(what)+'</b>'+SM.esc(why||'')
    +'<div class=btn-row><button class="btn btn-primary" data-act=pick>Choose a set</button>'
    +'</div></div></div></div>';
}

loadSets();
"""

PAGE = page("SourceMode judge", BODY, OWN_JS, OWN_CSS,
            viewport="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no")


def judge_router(cfg: dict):
    from fastapi import APIRouter, HTTPException  # noqa: PLC0415
    from fastapi.responses import FileResponse, HTMLResponse  # noqa: PLC0415
    from sourcemode.train.preview import web_copy  # noqa: PLC0415

    root = judge_root(cfg)
    r = APIRouter()

    @r.get("/judge", response_class=HTMLResponse)
    def _page():
        # no-store: a phone that cached this page across a monitor restart showed an
        # empty set list with a perfectly healthy server behind it.
        return HTMLResponse(PAGE, headers={"Cache-Control": "no-store, max-age=0"})

    @r.get("/judge/sets")
    def _sets() -> list[dict]:
        return list_sets(root)

    @r.get("/judge/file")
    def _file(set: str, id: str, w: int = 900):  # noqa: A002
        # Judging is full-height on a phone, so a 900px long edge is already more
        # than the screen resolves; the 1024x1536 PNG was ~2 MB a frame.
        p = item_path(root, set, id)
        if p is None:
            raise HTTPException(404)
        return FileResponse(web_copy(p, w))

    @r.get("/judge/ref")
    def _ref(set: str):  # noqa: A002
        s = load_set(root, set)
        if s is None or not s.get("reference") or not Path(s["reference"]).is_file():
            raise HTTPException(404)
        return FileResponse(web_copy(Path(s["reference"]), 600))

    @r.get("/judge/set/{set_id}")
    def _set(set_id: str) -> dict:
        p = set_payload(root, set_id)
        if p is None:
            raise HTTPException(404)
        return p

    @r.get("/judge/set/{set_id}/summary")
    def _summary(set_id: str) -> dict:
        s = summary(root, set_id)
        if s is None:
            raise HTTPException(404)
        return s

    @r.get("/judge/set/{set_id}/epochs")
    def _epochs(set_id: str) -> dict:
        """The sweep as a ranked decision, or 404 when the arms are not epochs.

        A 404 here is not an error: it is how the page knows to draw the generic
        per-arm bars for a wardrobe or A/B set instead of an epoch board.
        """
        from ..config import outputs_dir  # noqa: PLC0415

        b = epoch_board(root, set_id, outputs=outputs_dir(cfg))
        if b is None:
            raise HTTPException(404, f"{set_id} is not an epoch sweep")
        return b

    @r.get("/judge/set/{set_id}/redo")
    def _redo(set_id: str) -> dict:
        """What a re-roll of this set would cover, and whether it is queued.

        The queueing itself happens on the last verdict, server-side, so it
        still happens if the tab is closed before this is ever called.
        """
        from ..assets.redo import redoable  # noqa: PLC0415
        from ..gpu import queue as q  # noqa: PLC0415
        from ..config import outputs_dir  # noqa: PLC0415

        info = redoable(root, set_id)
        try:
            doc = q.load(q.queue_path(outputs_dir(cfg)))
            dup = q.duplicate_of(doc, "redo", set_id)
        except OSError:
            dup = None
        # The advancement itself happened on the last verdict, server-side, so
        # it cannot be reported from there. Derive it instead: a pool item past
        # its first candidate and not yet judged IS one that just advanced.
        # Stateless, and correct after a reload or on a second device.
        v = load_verdicts(root, set_id)
        doc_set = load_set(root, set_id) or {"items": []}
        advanced = sum(1 for it in doc_set["items"]
                       if (it.get("redo") or {}).get("kind") == "pool"
                       and int((it.get("redo") or {}).get("at", 0)) > 0
                       and it["id"] not in v)
        return {**info, "queued": dup["id"] if dup else None, "advanced": advanced}

    @r.get("/judge/set/{set_id}/history")
    def _history(set_id: str) -> dict:
        """Past tallies for this set id. Makes a re-render comparable."""
        return history(root, set_id)

    @r.post("/judge/set/{set_id}/verdict")
    def _verdict(set_id: str, body: dict) -> dict:
        try:
            out = record_verdict(root, set_id, str(body.get("item")), body.get("verdict"))
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        except ValueError as e:
            raise HTTPException(400, f"verdict must be one of {VERDICTS}") from e
        except FileNotFoundError as e:
            raise HTTPException(409, str(e)) from e
        # The last verdict in a set is what decides which shots get re-rolled.
        # Queueing per keystroke would mean a job for reject #1 and another for
        # reject #2; waiting for the set means one job that knows the whole
        # answer. Never allowed to break judging - a queue that cannot be
        # written is a queue problem, not a reason to lose a verdict.
        # NOTE: record_verdict returns the verdicts dict keyed by ITEM ID, and
        # the page assigns it straight to cur.verdicts. Nothing else may be put
        # in it - an extra key here would count as a judged item and throw the
        # completion test off by one. The page asks /redo separately.
        try:
            from ..monitor.queue_page import queue_redo_if_complete  # noqa: PLC0415

            queue_redo_if_complete(cfg, set_id)
        except Exception:  # noqa: BLE001
            pass
        return out

    return r
