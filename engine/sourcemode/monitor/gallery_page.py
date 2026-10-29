"""Gallery: everything made for one character - her videos first, then her photos.

Jeremy, 2026-10-29: "It's currently extremely hard to find the videos that I've
generated for characters, and it's also not really easy to find photos that I've
generated." One bubble per character (not a drop-down - his follow-up), and under
it every finished take, newest first, then every photo set in her library folder,
newest first. Read-only: nothing here judges, moves or deletes.

    GET  /gallery              the page
    GET  /gallery/characters   every character with a library folder, and her counts
    GET  /gallery/media        ?character=  her clips and her photo sets

Thumbnails and full files go through the Video tab's /video/thumb and /video/file,
which already refuse anything outside the library.
"""

from __future__ import annotations

from pathlib import Path

from .ui import page

IMAGES = {".png", ".jpg", ".jpeg", ".webp"}
# a video set's own stills are the clip's input, not something she was shot in
_VIDEO_INPUTS = {"source.png", "source_src.png"}

OWN_CSS = r"""
.who{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:var(--s3)}
.who button{min-height:26px;padding:0 8px;border-radius:var(--rp);
  background:var(--g2);border:1px solid var(--g4);color:var(--g8);
  font:600 10px/1.2 var(--font);cursor:pointer}
.who button.on{background:var(--act);border-color:var(--act-hi);color:var(--act-ink)}
.vids{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:var(--s3)}
.vid{background:var(--g1);border:1px solid var(--g3);border-radius:var(--r2);padding:var(--s2)}
.vid video{width:100%;aspect-ratio:4/5;background:#000;border-radius:var(--r1);display:block}
.vid b{display:block;font:var(--t-meta);font-weight:600;color:var(--g9);margin-top:4px}
.vid span{display:block;font:var(--t-small);color:var(--g7)}
details.set{background:var(--g1);border:1px solid var(--g3);border-radius:var(--r2);
  margin-bottom:var(--s2);padding:var(--s2) var(--s3)}
details.set summary{cursor:pointer;font:var(--t-meta);color:var(--g8)}
details.set summary b{color:var(--g9)}
.imgs{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:4px;margin-top:var(--s2)}
.imgs a{display:block;aspect-ratio:2/3;overflow:hidden;border-radius:var(--r1);background:var(--g2)}
.imgs img{width:100%;height:100%;object-fit:cover;display:block}
h2 .muted{font:var(--t-meta);color:var(--g7)}
"""

BODY = """
<div class=wrap id=app>
  <div class=col-main>
    <h2>Character</h2>
    <div class=who id=who></div>
    <div id=media><div class=empty><b>Pick a character</b></div></div>
  </div>
</div>
"""

OWN_JS = r"""
const $=id=>document.getElementById(id);
let chars=[], who=null;
try{ who=localStorage.getItem('galleryWho'); }catch(e){}
const thumb=(p,w)=>'/video/thumb?w='+w+'&path='+encodeURIComponent(p);
const file=p=>'/video/file?path='+encodeURIComponent(p);

async function load(){
  try{ chars=await SM.getJSON('/gallery/characters'); }
  catch(e){ SM.set($('who'),null,'<div class=errbox><b>Could not load</b>'+SM.esc(e.message)+'</div>'); return; }
  if(who && !chars.some(c=>c.character===who)) who=null;
  bubbles();
  if(who) pick(who);
}
function bubbles(){
  SM.set($('who'),null, chars.map(c=>'<button data-who="'+SM.esc(c.character)+'" class="'
    +(c.character===who?'on':'')+'">'+SM.esc(c.who)+'</button>').join('')
    || '<div class=empty><b>Nothing in the library yet</b></div>');
}
async function pick(c){
  who=c; try{ localStorage.setItem('galleryWho',c); }catch(e){}
  bubbles();
  SM.set($('media'),null,'<div class=empty><b>Loading&hellip;</b></div>');
  let m;
  try{ m=await SM.getJSON('/gallery/media?character='+encodeURIComponent(c)); }
  catch(e){ SM.set($('media'),null,'<div class=errbox><b>Could not load</b>'+SM.esc(e.message)+'</div>'); return; }
  if(who!==c) return;
  let h='<h2>Videos <span class=muted>'+m.videos.length+'</span></h2>';
  h+=m.videos.length?'<div class=vids>'+m.videos.map(v=>'<div class=vid><video controls preload=none playsinline'
      +(v.poster?' poster="'+thumb(v.poster,480)+'"':'')+' src="'+file(v.file)+'"></video>'
      +'<b>'+SM.esc(v.title)+'</b><span>'+SM.esc(v.date)+(v.seconds?' &middot; '+Number(v.seconds).toFixed(1)+' s':'')
      +'</span></div>').join('')+'</div>'
    :'<div class=empty><b>No videos yet</b></div>';
  h+='<h2>Photos <span class=muted>'+m.sets.reduce((n,s)=>n+s.images.length,0)+'</span></h2>';
  h+=m.sets.length?m.sets.map((s,i)=>'<details class=set'+(i<2?' open':'')+'><summary><b>'+SM.esc(s.title)
      +'</b> &middot; '+SM.esc(s.kind)+' &middot; '+SM.esc(s.date)+' &middot; '+s.images.length+'</summary>'
      +'<div class=imgs>'+s.images.map(p=>'<a href="'+file(p)+'" target=_blank rel=noopener>'
        +'<img loading=lazy src="'+thumb(p,300)+'" alt=""></a>').join('')+'</div></details>').join('')
    :'<div class=empty><b>No photos yet</b></div>';
  SM.set($('media'),null,h);
}
document.addEventListener('click',e=>{
  const w=e.target.closest('[data-who]'); if(w) pick(w.dataset.who);
});
load();
"""

PAGE = page("SourceMode gallery", BODY, OWN_JS, OWN_CSS)


def _title(folder: str) -> str:
    """'2026-10-28_shoot_office-officeslutty-desk' -> 'office officeslutty desk'."""
    parts = folder.split("_", 2)
    return (parts[2] if len(parts) == 3 else folder).replace("-", " ")


def photo_sets(home: Path) -> list[dict]:
    """Every set in her folder with an image in it, newest first. Subfolders count
    (a sweep keeps its renders in ep19/), but not the underscore ones - _web
    thumbnails, _superseded shots, a clip's _legs."""
    out = []
    for d in sorted((p for p in home.iterdir() if p.is_dir() and not p.name.startswith("_")),
                    key=lambda p: p.name, reverse=True) if home.is_dir() else []:
        parts = d.name.split("_", 2)
        kind = parts[1] if len(parts) == 3 else ""
        if kind == "voice":
            continue
        imgs = []
        for f in sorted(d.rglob("*")):
            rel = f.relative_to(d).parts
            if (f.suffix.lower() not in IMAGES or any(x.startswith("_") for x in rel[:-1])
                    or (kind == "video" and f.name in _VIDEO_INPUTS)):
                continue
            imgs.append(str(f))
        if imgs:
            out.append({"name": d.name, "title": _title(d.name), "kind": kind,
                        "date": d.name[:10], "images": imgs})
    return out


def gallery_router(cfg: dict):
    from fastapi import APIRouter, HTTPException  # noqa: PLC0415
    from fastapi.responses import HTMLResponse  # noqa: PLC0415

    from .. import video as V  # noqa: PLC0415
    from ..library import library_dir  # noqa: PLC0415

    r = APIRouter()

    @r.get("/gallery", response_class=HTMLResponse)
    def _page():
        return HTMLResponse(PAGE, headers={"Cache-Control": "no-store, max-age=0"})

    @r.get("/gallery/characters")
    def _characters() -> list[dict]:
        lib = library_dir(cfg)
        out = []
        for d in sorted(lib.iterdir()) if lib.is_dir() else []:
            if not d.is_dir() or d.name.startswith("_") or d.name == "loras":
                continue
            if not any(p.is_dir() and p.name[:4].isdigit() for p in d.iterdir()):
                continue
            out.append({"character": d.name, "who": d.name.capitalize()})
        return out

    @r.get("/gallery/media")
    def _media(character: str) -> dict:
        c = character.strip().lower()
        if not c or any(x in c for x in ("/", "\\", "..")):
            raise HTTPException(400, "a character is required")
        lib = library_dir(cfg)
        videos = []
        for s in V.clips(lib, c):
            for t in s["takes"]:
                videos.append({"file": t["file"], "seconds": t["seconds"], "date": s["date"],
                               "title": _title(s["name"]) + (f" - {Path(t['file']).stem}" if len(s["takes"]) > 1 else ""),
                               "poster": s["source"]})
        return {"videos": videos, "sets": photo_sets(lib / c)}

    return r
