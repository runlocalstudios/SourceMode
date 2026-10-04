"""What happens when you reject a shot: take the next one, or render a new one.

Jeremy, 2026-10-04: "Why don't we just drop the selfies in the judge tab? And
same with the game assets. And if I reject them, you queue an item to regenerate
a replacement for that. single or multiple rejected photos."

It is the cheaper shape and it is not close. The wardrobe pack rendered FOUR
candidates for every look and kept one - 112 shots to ship 28, every time,
whether or not the first draw was fine. Rendering one and re-rolling the misses
costs 28 shots plus the reject rate: at the ~20% we actually see on asset
prompts that is ~34 shots against 112, and the second round is six minutes.

What makes it work was already here. `make_set` hashes every image and
`drop_stale_verdicts` forgets any verdict whose image changed content - built
after a jojo sweep inherited 17:44 judgements onto images rewritten at 19:09.
So a replacement rendered under the SAME item id automatically re-opens just
that item, keeps every other verdict, and `append_result` preserves the old
tally first. The retry loop is three lines on top of that.

There are two ways to answer a reject, and the cheap one comes first.

**A POOL, when other candidates already exist.** Jeremy, 2026-10-04: "if I
reject something instead of regenerating you can just show me the next
selection of the other four that were generated unless they've already been
deleted." Zara's pack was rendered at four candidates a look - 112 images, all
still on disk - so a reject there costs nothing at all: advance to the next
candidate, rewrite the set, done in milliseconds with the card untouched.

**A RE-RENDER, when the pool is empty.** Either the pack was rendered one-deep
(everything from 2026-10-04 on) or all four candidates have been rejected. Only
then is GPU time spent.

Candidates are ranked by `rank_candidates` - fewest broken asks against what
the prompt asked for, then identity - so "the next one" means the next best
one, not the next filename.

Two rules this file holds:

1. **The rejected file is deleted, not kept.** One image per slot, always.
   A reject left on disk is a candidate `assets place` can still pick, which
   would quietly undo the judgement that rejected it.
2. **A retry is a NEW draw, not the same one.** The seed is offset by the
   attempt number, so re-queueing twice cannot hand back the same picture.
"""

from __future__ import annotations

from pathlib import Path

#: Co-prime-ish stride between attempts; large enough that attempt 1 and
#: attempt 2 of neighbouring slots cannot collide on one seed.
ATTEMPT_STRIDE = 10_007


def retry_seed(base: int, attempt: int) -> int:
    """The seed for attempt N of a slot. Attempt 0 is the original draw."""
    return int(base) + ATTEMPT_STRIDE * int(attempt)


def pool_item(slot: dict, cands: list[dict], *, character: str, source: str,
              at: int = 0) -> dict:
    """A judge item backed by candidates that ALREADY EXIST on disk.

    `cands` are sidecar dicts in rank order; `at` is which one is on show. A
    reject advances `at` rather than spending GPU time.
    """
    cur = cands[at]
    return {"id": slot["id"], "arm": slot.get("category") or source,
            "group": str(slot.get("look", slot["id"])),
            "path": cur["source"], "score": cur.get("score"),
            "redo": {"kind": "pool", "character": character, "source": source,
                     "slot_id": slot["id"], "seed": cur.get("seed", 0), "attempt": 0,
                     "at": at, "candidates": [c["source"] for c in cands],
                     "scores": [c.get("score") for c in cands]}}


def advance_pool(root: Path, set_id: str) -> dict:
    """Show the next candidate for every rejected pool item. No GPU, no queue.

    Returns `{advanced, exhausted}` - `exhausted` are the slots that have run
    out of candidates and now genuinely need a re-render.
    """
    from .judge import load_set, make_set  # noqa: PLC0415

    doc = load_set(root, set_id)
    rows = {it["id"]: dict(it) for it in doc["items"]} if doc else {}
    advanced, exhausted = [], []
    for it in rejected(root, set_id):
        info = it["redo"]
        if info.get("kind") != "pool":
            continue
        cands = info.get("candidates") or []
        nxt = int(info.get("at", 0)) + 1
        if nxt >= len(cands) or not Path(cands[nxt]).is_file():
            exhausted.append(it["id"])
            continue
        row = rows[it["id"]]
        row["path"] = cands[nxt]
        row["score"] = (info.get("scores") or [None] * len(cands))[nxt]
        row["redo"] = {**info, "at": nxt}
        advanced.append(it["id"])
    if advanced:
        # Same ids, different pixels: drop_stale_verdicts re-opens exactly these.
        make_set(root, set_id, doc["title"], list(rows.values()),
                 question=doc.get("question", ""), reference=doc.get("reference"),
                 priority=doc.get("priority", 50))
    return {"advanced": advanced, "exhausted": exhausted}


def rejected(root: Path, set_id: str) -> list[dict]:
    """The items this set's verdicts reject, each with its redo instructions.

    An item with no `redo` block cannot be regenerated - an epoch sweep arm is
    a checkpoint comparison, not a shot to re-roll - so it is left out rather
    than guessed at.
    """
    from .judge import load_set, load_verdicts  # noqa: PLC0415

    doc = load_set(root, set_id)
    if not doc:
        return []
    v = load_verdicts(root, set_id)
    return [it for it in doc["items"]
            if v.get(it["id"]) == "reject" and it.get("redo")]


def complete(root: Path, set_id: str) -> bool:
    """Has every item in the set been judged?

    Jeremy, 2026-10-04: "I want you to queue and wait until the whole set has
    been judged until you determine which shots need to be regenerated." So a
    half-judged set has no rejects worth acting on yet - the re-roll is one
    job at the end, not a job per keystroke.
    """
    from .judge import load_set, load_verdicts  # noqa: PLC0415

    doc = load_set(root, set_id)
    if not doc or not doc["items"]:
        return False
    v = load_verdicts(root, set_id)
    return all(v.get(it["id"]) in ("keep", "reject") for it in doc["items"])


def redoable(root: Path, set_id: str) -> dict:
    """What a re-roll of this set would do: `{n, character, kind, complete}`.

    `n` is zero until the whole set is judged, so the page can say "finish
    judging" rather than offering a job that would re-roll the first two
    rejects and then have to run again for the rest.
    """
    done = complete(root, set_id)
    rows = rejected(root, set_id) if done else []
    if not rows:
        return {"n": 0, "n_pool": 0, "n_render": 0, "character": None,
                "kind": None, "complete": done}
    # A pool reject is free and instant; only the rest costs card time, and the
    # page should say which is which rather than implying a queue wait for work
    # that never touches the GPU.
    n_pool = sum(1 for r in rows
                 if r["redo"].get("kind") == "pool"
                 and int(r["redo"].get("at", 0)) + 1 < len(r["redo"].get("candidates") or []))
    first = rows[0]["redo"]
    return {"n": len(rows), "n_pool": n_pool, "n_render": len(rows) - n_pool,
            "character": first.get("character"), "kind": first.get("kind"),
            "complete": True}


def judge_item(slot: dict, path: Path, *, kind: str, character: str, source: str,
               seed: int, attempt: int = 0, score: float | None = None,
               arm: str | None = None) -> dict:
    """One judge-set item that knows how to regenerate itself.

    `source` is the shoot id or the plan filename - a REFERENCE, not a copy of
    the slot. The slot is rebuilt from the catalog or the plan at redo time, so
    a fixed prompt reaches the retry instead of a snapshot of the old one.
    """
    return {"id": slot["id"], "path": path, "arm": arm or slot.get("tone") or source,
            "group": str(slot.get("look", slot["id"])), "score": score,
            "redo": {"kind": kind, "character": character, "source": source,
                     "slot_id": slot["id"], "seed": int(seed), "attempt": int(attempt)}}
