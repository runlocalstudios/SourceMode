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
from pathlib import Path

VERDICTS = ("keep", "reject")


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
        out.append({"id": s["id"], "title": s["title"], "question": s.get("question", ""),
                    "priority": s.get("priority", 50), "n": n, "judged": judged,
                    "done": judged >= n})

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
    """What the page gets: items in blind order, arms stripped."""
    s = load_set(root, set_id)
    if s is None:
        return None
    return {"id": s["id"], "title": s["title"], "question": s.get("question", ""),
            "has_reference": bool(s.get("reference")),
            "items": [{"id": i} for i in s["order"]], "verdicts": load_verdicts(root, set_id)}


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
    if item_id not in {it["id"] for it in s["items"]}:
        raise KeyError(item_id)
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


PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"><title>SourceMode judge</title>
<style>
 html,body{margin:0;height:100%;background:#111;color:#ddd;font:14px system-ui,sans-serif}
 #bar{height:44px;display:flex;align-items:center;gap:14px;padding:0 14px;background:#1b1b1b;border-bottom:1px solid #333}
 #bar select{background:#222;color:#ddd;border:1px solid #444;padding:4px 8px;font-size:14px;max-width:46vw}
 #stage{position:relative;height:calc(100% - 44px);display:flex;align-items:center;justify-content:center}
 #img{max-height:100%;max-width:100%;object-fit:contain;display:block;cursor:pointer}
 #ref{position:absolute;right:12px;bottom:12px;max-height:34vh;max-width:22vw;border:2px solid #555;border-radius:4px;background:#000}
 #badge{position:absolute;left:14px;top:12px;padding:6px 12px;border-radius:4px;font-weight:600;font-size:16px;display:none}
 .keep{background:#1f7a3a}.reject{background:#8a2a2a}
 #keys{margin-left:auto;color:#888}
 kbd{background:#2a2a2a;border:1px solid #555;border-radius:3px;padding:1px 6px;color:#eee}
 /* Phone: thumb-sized verdict buttons in the bottom corners, no keyboard needed. */
 .tap{position:fixed;bottom:18px;width:84px;height:84px;border-radius:50%;border:none;
      font-size:38px;line-height:84px;text-align:center;color:#fff;opacity:.92;
      -webkit-tap-highlight-color:transparent;touch-action:manipulation;z-index:5;padding:0;cursor:pointer}
 #no{left:18px;background:#8a2a2a}#yes{right:18px;background:#1f7a3a}
 #undo{position:fixed;bottom:36px;left:50%;transform:translateX(-50%);z-index:5;
       background:#2a2a2aE0;border:1px solid #555;color:#ccc;border-radius:20px;padding:8px 18px;font-size:15px}
 @media (max-width:820px){
   #keys{display:none}
   #bar{height:38px;gap:8px;padding:0 8px;font-size:13px}
   #bar select{font-size:13px;max-width:52vw}
   #stage{height:calc(100% - 38px)}
   #ref{max-height:20vh;max-width:30vw;right:6px;bottom:112px}
   #img{max-height:100%;object-fit:contain}
 }
 @media (min-width:821px){ .tap,#undo{display:none} }
 #done{position:absolute;inset:0;background:#111;overflow:auto;padding:30px;display:none}
 table{border-collapse:collapse;margin-top:14px}td,th{border:1px solid #333;padding:6px 12px;text-align:left}
 button{background:#2a2a2a;color:#ddd;border:1px solid #555;padding:6px 12px;cursor:pointer;border-radius:3px}
</style></head><body>
<div id="bar">
 <select id="pick"></select>
 <span id="prog"></span>
 <span id="q" style="color:#aaa"></span>
 <span id="keys"><kbd>K</kbd> keep &nbsp; <kbd>X</kbd> reject &nbsp; <kbd>&larr;</kbd><kbd>&rarr;</kbd> move &nbsp; <kbd>R</kbd> reference &nbsp; <kbd>S</kbd> tally &nbsp; click: left half reject, right half keep</span>
</div>
<div id="stage">
 <div id="badge"></div>
 <img id="img" alt="">
 <img id="ref" alt="" style="display:none">
 <div id="done"></div>
</div>
<button class="tap" id="no" aria-label="not her">&#10007;</button>
<button class="tap" id="yes" aria-label="her">&#10003;</button>
<button id="undo">&#8592; back</button>
<script>
const $=id=>document.getElementById(id);
let sets=[], cur=null, idx=0, showRef=true;
const fileUrl=(s,i)=>`/judge/file?set=${encodeURIComponent(s)}&id=${encodeURIComponent(i)}`;
async function fetchSets(){sets=await (await fetch('/judge/sets',{cache:'no-store'})).json();
  const p=$('pick'); const keep=p.value; p.innerHTML='';
  // /judge/sets returns unfinished first. Draw one disabled divider at the
  // boundary so a long list can be scanned for what still needs work.
  let split=false;
  for(const s of sets){
    if(s.done&&!split){split=true;
      const d=document.createElement('option');
      d.disabled=true;d.textContent='─'.repeat(24)+' complete '+'─'.repeat(24);
      p.appendChild(d);}
    const o=document.createElement('option');o.value=s.id;
    o.textContent=(s.done?'✓ ':'')+`${s.title}  (${s.judged}/${s.n})`;
    p.appendChild(o);}
  if(keep) p.value=keep;}
async function loadSets(){
  await fetchSets();
  const want=location.hash.slice(1)||(sets.find(s=>s.judged<s.n)||sets[0]||{}).id;
  if(want){$('pick').value=want;await openSet(want);}
}
async function openSet(id){
  cur=await (await fetch('/judge/set/'+encodeURIComponent(id),{cache:'no-store'})).json();
  location.hash=id; $('q').textContent=cur.question||'';
  $('ref').style.display='none';
  if(cur.has_reference){$('ref').src='/judge/ref?set='+encodeURIComponent(id);}
  idx=cur.items.findIndex(it=>!(it.id in cur.verdicts)); if(idx<0) idx=cur.items.length;
  show();
}
function show(){
  $('done').style.display='none';
  for(const id of ['yes','no','undo']) $(id).style.visibility='';
  if(idx>=cur.items.length){return tally();}
  const it=cur.items[idx];
  $('img').style.display=''; $('img').src=fileUrl(cur.id,it.id);
  $('ref').style.display=(showRef&&cur.has_reference)?'':'none';
  const v=cur.verdicts[it.id]; const b=$('badge');
  b.style.display=v?'':'none'; b.textContent=v||''; b.className=v||'';
  $('prog').textContent=`${idx+1} / ${cur.items.length}`;
  if(idx+1<cur.items.length){const pre=new Image();pre.src=fileUrl(cur.id,cur.items[idx+1].id);}
}
async function verdict(v){
  if(!cur||idx>=cur.items.length) return;
  const it=cur.items[idx];
  const r=await fetch(`/judge/set/${encodeURIComponent(cur.id)}/verdict`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({item:it.id,verdict:v})});
  cur.verdicts=await r.json(); idx++; show();
}
async function tally(){
  const s=await (await fetch(`/judge/set/${encodeURIComponent(cur.id)}/summary`,{cache:'no-store'})).json();
  $('img').style.display='none'; $('ref').style.display='none'; $('badge').style.display='none';
  $('prog').textContent=`${s.judged} / ${s.n} judged`;
  let h=`<h2>${s.title}</h2><p>${cur.question||''}</p><table><tr><th>arm</th><th>judged</th><th>kept</th><th>keep rate</th></tr>`;
  for(const a of s.arms) h+=`<tr><td>${a.arm}</td><td>${a.judged}/${a.n}</td><td>${a.keep}</td><td>${a.rate==null?'':Math.round(a.rate*100)+'%'}</td></tr>`;
  h+=`</table><p style="margin-top:18px"><button onclick="idx=0;show()">review from the start</button> &nbsp; <button onclick="nextSet()">next set</button></p>`;
  await fetchSets();
  const rem=sets.filter(x=>x.judged<x.n&&x.id!==cur.id); if(rem.length) h+=`<p style="color:#888">${rem.length} set(s) still to judge</p>`;
  $('done').innerHTML=h; $('done').style.display='';
  for(const id of ['yes','no','undo']) $(id).style.visibility='hidden';
}
function nextSet(){const n=sets.find(x=>x.judged<x.n&&x.id!==cur.id)||sets[0]; if(n){$('pick').value=n.id;openSet(n.id);}}
document.addEventListener('keydown',e=>{
  if(e.target.tagName==='SELECT'||!cur) return;
  const k=e.key.toLowerCase();
  if(k==='k'||k==='enter') verdict('keep');
  else if(k==='x'||k==='j') verdict('reject');
  else if(k==='arrowright'){if(idx<cur.items.length){idx++;show();}}
  else if(k==='arrowleft'||k==='z'||k==='backspace'){if(idx>0){idx--;show();}}
  else if(k==='r'){showRef=!showRef;show();}
  else if(k==='s'){idx=cur.items.length;show();}
  else return; e.preventDefault();
});
$('pick').addEventListener('change',e=>openSet(e.target.value));
$('img').addEventListener('click',e=>{
  if(window.innerWidth<=820) return;           // phone uses the buttons, not half-taps
  const x=e.offsetX/e.target.clientWidth; verdict(x<0.5?'reject':'keep');});
for(const [id,v] of [['yes','keep'],['no','reject']]){
  const b=$(id);
  b.addEventListener('click',ev=>{ev.preventDefault();verdict(v);});
}
$('undo').addEventListener('click',ev=>{ev.preventDefault(); if(idx>0){idx--;show();}});
loadSets();
</script></body></html>"""


def judge_router(cfg: dict):
    from fastapi import APIRouter, HTTPException  # noqa: PLC0415
    from fastapi.responses import FileResponse, HTMLResponse  # noqa: PLC0415

    root = judge_root(cfg)
    r = APIRouter()

    @r.get("/judge", response_class=HTMLResponse)
    def _page():
        return PAGE

    @r.get("/judge/sets")
    def _sets() -> list[dict]:
        return list_sets(root)

    @r.get("/judge/file")
    def _file(set: str, id: str):  # noqa: A002
        p = item_path(root, set, id)
        if p is None:
            raise HTTPException(404)
        return FileResponse(p)

    @r.get("/judge/ref")
    def _ref(set: str):  # noqa: A002
        s = load_set(root, set)
        if s is None or not s.get("reference") or not Path(s["reference"]).is_file():
            raise HTTPException(404)
        return FileResponse(Path(s["reference"]))

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

    @r.post("/judge/set/{set_id}/verdict")
    def _verdict(set_id: str, body: dict) -> dict:
        try:
            return record_verdict(root, set_id, str(body.get("item")), body.get("verdict"))
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        except ValueError as e:
            raise HTTPException(400, f"verdict must be one of {VERDICTS}") from e

    return r
