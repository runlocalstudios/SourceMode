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
from datetime import datetime, timezone
from pathlib import Path

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
    "lighting": ("light", "lit", "daylight", "sunlight", "shade", "lamp", "overcast"),
}


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
                  measure: bool = True) -> dict:
    """Measure the set and write the preview. `measure=False` skips InsightFace."""
    dataset_dir = Path(dataset_dir)
    ds_id = dataset_id or dataset_dir.name
    images = collect_images(dataset_dir)

    gate: dict = {}
    if measure:
        from ..gates.dataset import evaluate, measure_dataset  # noqa: PLC0415

        m = measure_dataset(dataset_dir, render_size=render_size)
        gate = evaluate(m, trigger=trigger)
        px = {f.name: (f.face_px, f.yaw_deg) for f in m.faces}
        for im in images:
            if im["name"] in px:
                im["face_px"], im["yaw_deg"] = int(px[im["name"]][0]), round(float(px[im["name"]][1]), 1)

    doc = {
        "id": ds_id,
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


def list_previews(root: Path) -> list[dict]:
    """Unapproved first: those are the ones blocking a training run."""
    out = []
    d = root / "previews"
    for p in sorted(d.glob("*.json")) if d.exists() else []:
        doc = json.loads(p.read_text(encoding="utf-8"))
        st = approval_state(root, doc["id"])
        flagged = sum(1 for im in doc["images"] if im["missing"] or im["uncaptioned"])
        out.append({"id": doc["id"], "n": doc["n"], "built_at": doc["built_at"],
                    "gate_passed": bool(doc.get("gate", {}).get("passed")),
                    "flagged": flagged, **st})
    return sorted(out, key=lambda s: (s["approved"], s["id"]))


def preview_payload(root: Path, ds_id: str) -> dict | None:
    doc = load_preview(root, ds_id)
    if doc is None:
        return None
    return {**doc, "approval": approval_state(root, ds_id),
            "images": [{k: v for k, v in im.items() if k != "path"} for im in doc["images"]]}


def image_path(root: Path, ds_id: str, name: str) -> Path | None:
    doc = load_preview(root, ds_id)
    if doc is None:
        return None
    for im in doc["images"]:
        if im["name"] == name:
            p = Path(im["path"])
            return p if p.is_file() else None
    return None


PAGE = """<!-- dataset preview -->
<title>training set</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
 body{background:#111;color:#ddd;font:14px system-ui,sans-serif;margin:0;padding:12px}
 header{position:sticky;top:0;background:#111;padding:8px 0 10px;border-bottom:1px solid #333;z-index:5}
 select,button{font:inherit;padding:8px;background:#222;color:#ddd;border:1px solid #444;border-radius:6px}
 button.ok{background:#1b5e20;border-color:#2e7d32}
 button.no{background:#5a1b1b;border-color:#7d2e2e}
 .row{display:flex;gap:14px;padding:14px 0;border-bottom:1px solid #262626;align-items:flex-start}
 .row img{max-height:46vh;max-width:42vw;border-radius:6px;background:#000}
 .cap{flex:1;min-width:0}
 .cap code{display:block;white-space:pre-wrap;word-break:break-word;background:#191919;
   border:1px solid #333;border-radius:6px;padding:10px;color:#e8e8e8;font-size:13px;line-height:1.45}
 .chip{display:inline-block;background:#3a2a00;border:1px solid #6b4e00;color:#ffd479;
   border-radius:999px;padding:2px 9px;margin:6px 6px 0 0;font-size:12px}
 .chip.bad{background:#4a0f0f;border-color:#7d2e2e;color:#ffb4b4}
 .meta{color:#888;font-size:12px;margin-top:6px}
 .finding{margin:2px 0;font-size:13px}
 .finding.f{color:#ff9d9d}
 .finding.p{color:#7fbf7f}
 #sum{margin:10px 0 0;padding:10px;background:#181818;border:1px solid #333;border-radius:6px}
 @media (max-width:820px){ .row{flex-direction:column} .row img{max-width:100%;max-height:60vh} }
</style>
<header>
 <select id=pick></select>
 <button id=yes class=ok>Approve for training</button>
 <button id=no class=no>Reject</button>
 <span id=state></span>
 <div id=sum></div>
</header>
<div id=list></div>
<script>
const $=id=>document.getElementById(id);
let cur=null;
async function loadList(){
  const ls=await (await fetch('/dataset/list',{cache:'no-store'})).json();
  const p=$('pick'); p.innerHTML='';
  for(const s of ls){const o=document.createElement('option');o.value=s.id;
    o.textContent=`${s.approved?'\\u2713 ':''}${s.id}  (${s.n} images${s.flagged?', '+s.flagged+' flagged':''})`;
    p.appendChild(o);}
  const want=location.hash.slice(1)||(ls[0]||{}).id;
  if(want){p.value=want;await open(want);}
}
async function open(id){
  cur=await (await fetch('/dataset/'+encodeURIComponent(id),{cache:'no-store'})).json();
  location.hash=id;
  const a=cur.approval;
  $('state').textContent=a.approved?('approved '+(a.at||'')):(a.stale?'approval STALE - content changed since it was approved':'not approved');
  $('state').style.color=a.approved?'#7fbf7f':'#ff9d9d';
  const g=cur.gate||{};
  let h=`<b>${cur.id}</b> - ${cur.n} images, trigger <code>${cur.trigger||'(none)'}</code>`;
  if(g.findings){h+=`<div style="margin-top:6px">gate: <b style="color:${g.passed?'#7fbf7f':'#ff9d9d'}">${g.passed?'pass':'FAIL'}</b></div>`;
    for(const f of g.findings) if(!f.passed) h+=`<div class="finding f">x ${f.check}: ${f.detail}</div>`;}
  $('sum').innerHTML=h;
  let out='';
  for(const im of cur.images){
    const chips=(im.uncaptioned?'<span class="chip bad">NO CAPTION</span>':'')
      +(im.missing||[]).map(m=>`<span class="chip">no ${m}</span>`).join('');
    const meta=[im.face_px?`face ${im.face_px}px`:null,(im.yaw_deg!==undefined)?`yaw ${im.yaw_deg}\\u00b0`:null]
      .filter(Boolean).join(' \\u00b7 ');
    out+=`<div class=row><img loading=lazy src="/dataset/file?ds=${encodeURIComponent(cur.id)}&name=${encodeURIComponent(im.name)}">
      <div class=cap><code>${(im.caption||'(empty)').replace(/</g,'&lt;')}</code>
      <div>${chips}</div><div class=meta>${im.name}${meta?' \\u00b7 '+meta:''}</div></div></div>`;
  }
  $('list').innerHTML=out;
}
async function setApproval(v){
  await fetch('/dataset/'+encodeURIComponent(cur.id)+'/approve',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({approved:v})});
  await open(cur.id); await refreshNames();
}
async function refreshNames(){const keep=$('pick').value;await loadList();$('pick').value=keep;}
$('pick').onchange=e=>open(e.target.value);
$('yes').onclick=()=>setApproval(true);
$('no').onclick=()=>setApproval(false);
loadList();
</script>
"""


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
    def _file(ds: str, name: str):
        p = image_path(root, ds, name)
        if p is None:
            raise HTTPException(404)
        return FileResponse(p)

    @r.get("/dataset/{ds_id}")
    def _one(ds_id: str) -> dict:
        p = preview_payload(root, ds_id)
        if p is None:
            raise HTTPException(404)
        return p

    @r.post("/dataset/{ds_id}/approve")
    def _approve(ds_id: str, body: dict = Body(...)) -> dict:
        try:
            return record_approval(root, ds_id, bool(body.get("approved")))
        except KeyError as e:
            raise HTTPException(404) from e

    return r
