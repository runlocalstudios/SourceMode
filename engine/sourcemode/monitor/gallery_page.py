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

Jeremy, 2026-10-29: "make it easier on me in the gallery tab to see the in-game
assets - the 28 photos, selfies, intimate, etc ... a separate set of buttons and if
i click them the photos show up sort of near the top". So above the videos sits a
row of buttons, one per kind of game art she has - the 28-look pack, selfies,
intimate, home, portrait - each showing what the GAME has for her, or, when
nothing is shipped yet, what is staged or rendered, and saying which.

    GET  /gallery/game         ?character=  her game-asset groups, with counts
    GET  /gallery/game-file    ?path=       a file from the game repo or the staging (read-only)

Game files are served as they are, never thumbnailed: the thumbnailer caches
beside the original, and nothing here may write into the game repo.
"""

from __future__ import annotations

from pathlib import Path

from ..assets.looks import GAME_ROOT
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
.ga{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:var(--s2)}
.ga button{min-height:36px;padding:0 var(--s3);border-radius:var(--r2);background:var(--g1);
  border:1px solid var(--g4);color:var(--g9);font:600 12px/1.2 var(--font);cursor:pointer;text-align:left}
.ga button small{display:block;font:var(--t-small);font-weight:400;color:var(--g7)}
.ga button.on{background:var(--act);border-color:var(--act-hi);color:var(--act-ink)}
.ga button.on small{color:var(--act-ink)}
.gagrid{margin-bottom:var(--s3)}
.gagrid .src{font:var(--t-small);color:var(--g7);margin-bottom:4px}
.gagrid .imgs{grid-template-columns:repeat(auto-fill,minmax(130px,1fr))}
.gagrid .imgs a{position:relative}
.gagrid .imgs a span{position:absolute;left:0;right:0;bottom:0;padding:2px 4px;background:rgba(0,0,0,.55);
  color:#fff;font:10px/1.2 var(--mono);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
"""

BODY = """
<div class=wrap id=app>
  <div class=col-main>
    <h2>Character</h2>
    <div class=who id=who></div>
    <div id=game></div>
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
let groups=[], ga=null;
function gameHtml(){
  if(!groups.length) return '<h2>Game assets <span class=muted>none yet</span></h2>';
  let h='<h2>Game assets</h2><div class=ga>'+groups.map(g=>'<button data-ga="'+SM.esc(g.key)+'" class="'
    +(g.key===ga?'on':'')+'">'+SM.esc(g.label)+' &middot; '+g.images.length+'<small>'+SM.esc(g.source)+'</small></button>').join('')+'</div>';
  const g=groups.find(x=>x.key===ga);
  if(g) h+='<div class=gagrid><div class=src>'+SM.esc(g.label)+': '+SM.esc(g.source)+'</div><div class=imgs>'
    +g.images.map(i=>'<a href="'+SM.esc(i.full)+'" target=_blank rel=noopener><img loading=lazy src="'+SM.esc(i.thumb)
    +'" alt=""><span>'+SM.esc(i.name)+'</span></a>').join('')+'</div></div>';
  return h;
}
async function gameAssets(c){
  groups=[]; ga=null;
  SM.set($('game'),null,'');
  let g;
  try{ g=await SM.getJSON('/gallery/game?character='+encodeURIComponent(c)); }
  catch(e){ SM.set($('game'),null,'<div class=errbox><b>Could not load her game assets</b>'+SM.esc(e.message)+'</div>'); return; }
  if(who!==c) return;
  groups=g.groups; SM.set($('game'),null,gameHtml());
}
async function pick(c){
  who=c; try{ localStorage.setItem('galleryWho',c); }catch(e){}
  bubbles();
  SM.set($('media'),null,'<div class=empty><b>Loading&hellip;</b></div>');
  gameAssets(c);
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
  const w=e.target.closest('[data-who]'); if(w){ pick(w.dataset.who); return; }
  const g=e.target.closest('[data-ga]'); if(g){ ga=(ga===g.dataset.ga?null:g.dataset.ga); SM.set($('game'),null,gameHtml()); }
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


def _newest_png(folder: Path) -> Path | None:
    hits = [f for f in folder.glob("*.png") if not f.name.startswith("_")]
    return max(hits, key=lambda f: f.stat().st_mtime) if hits else None


def _images(folder: Path) -> list[Path]:
    return sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in IMAGES) if folder.is_dir() else []


def _urls(f: Path, lib: Path) -> dict:
    """Library files get the Video tab's thumbnail; game and staging files are
    served as they are (no cache may be written beside a game file)."""
    try:
        f.resolve().relative_to(lib.resolve())
        return {"thumb": f"/video/thumb?w=300&path={f}", "full": f"/video/file?path={f}"}
    except ValueError:
        return {"thumb": f"/gallery/game-file?path={f}", "full": f"/gallery/game-file?path={f}"}


def game_groups(character: str, game_root: Path, out_root: Path, lib: Path) -> list[dict]:
    """Her game art by kind, each from the first place that has any: the game
    itself, else the staging under outputs, else the renders or the library
    shoot it would come from - and `source` says which. Only kinds with
    something to show are returned."""
    c = character.lower()
    game = game_root / "src" / "assets" / "characters" / c
    staged = out_root / "game-assets" / c
    sets = photo_sets(lib / c) if (lib / c).is_dir() else []

    def latest_set(kind: str, name: str | None = None) -> list[Path]:
        for s in sets:
            if s["kind"] == kind and (name is None or s["name"].endswith(name)):
                return [Path(p) for p in s["images"]]
        return []

    def render_shots() -> list[Path]:
        r = staged / "renders"
        out = []
        for d in sorted(r.iterdir()) if r.is_dir() else []:
            if d.is_dir() and not d.name.startswith("_"):
                hit = _newest_png(d)
                if hit:
                    out.append(hit)
        return out

    wants = (
        ("pack", "Pack 28", ((game / "outfits", "in the game"), (staged / "outfits", "staged, not shipped"),
                             (render_shots, "rendered, not staged"))),
        ("selfies", "Selfies", ((game / "selfies", "in the game"),
                                (lambda: latest_set("selfies"), "rendered, not shipped"))),
        ("intimate", "Intimate", ((game / "intimate", "in the game"), (staged / "intimate", "staged, not shipped"),
                                  (lambda: latest_set("shoot", "_shoot_lingerie"), "rendered, not staged"))),
        ("home", "Home", ((game / "home", "in the game"),)),
        ("portrait", "Portrait", ((game / "portraits", "in the game"),)),
    )
    groups = []
    for key, label, places in wants:
        for place, source in places:
            files = place() if callable(place) else _images(place)
            if files:
                groups.append({"key": key, "label": label, "source": source,
                               "images": [{"name": f.name, "path": str(f), **_urls(f, lib)} for f in files]})
                break
    return groups


def gallery_router(cfg: dict):
    from fastapi import APIRouter, HTTPException  # noqa: PLC0415
    from fastapi.responses import FileResponse, HTMLResponse  # noqa: PLC0415

    from .. import config as C  # noqa: PLC0415
    from .. import video as V  # noqa: PLC0415
    from ..library import library_dir  # noqa: PLC0415

    r = APIRouter()

    def _char(character: str) -> str:
        c = character.strip().lower()
        if not c or any(x in c for x in ("/", "\\", "..")):
            raise HTTPException(400, "a character is required")
        return c

    def _game_roots() -> list[Path]:
        return [GAME_ROOT / "src" / "assets" / "characters", C.outputs_dir(cfg) / "game-assets"]

    @r.get("/gallery/game")
    def _game(character: str) -> dict:
        c = _char(character)
        return {"groups": game_groups(c, GAME_ROOT, C.outputs_dir(cfg), library_dir(cfg))}

    @r.get("/gallery/game-file")
    def _game_file(path: str):
        try:
            q = Path(path).resolve()
        except OSError as exc:
            raise HTTPException(404) from exc
        for root in _game_roots():
            try:
                q.relative_to(root.resolve())
            except ValueError:
                continue
            if q.is_file() and q.suffix.lower() in IMAGES:
                return FileResponse(q, headers={"Cache-Control": "no-store, max-age=0"})
        raise HTTPException(404)

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
