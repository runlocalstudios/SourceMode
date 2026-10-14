"""Video: pick her, pick a still or describe one, say what happens, queue it.

Jeremy, 2026-10-14: "We never set up the video capability to create from an
existing asset or to generate a new T2I then animate?" and, on this tab,
"design it as a world class experience". What that means here:

- her keepers are right there to tap, newest first, because the still is the
  whole identity question and he has already judged these
- the motion line is his words, with chips as starting points, and the cost
  is on the button before he commits, like the Shoots tab
- a length past one leg says so ("2 legs, chained") rather than silently
  cutting a 10-second ask to 6
- her finished clips play on this page, under the form, as they land

    GET  /video              the page
    GET  /video/catalog      characters, framings, qualities, motions, the leg cap
    GET  /video/keepers      ?character=  her judged keepers, newest first
    GET  /video/clips        ?character=  her video sets with every take
    GET  /video/thumb        ?path=       a keeper, web-sized (library and outputs only)
    GET  /video/file         ?path=       a clip or still (library only)
    POST /video/queue        the spec -> ONE queued job
"""

from __future__ import annotations

from pathlib import Path

from .ui import page

OWN_CSS = r"""
.who{display:flex;flex-wrap:wrap;gap:var(--s2);margin-bottom:var(--s4)}
.who button{min-height:var(--tap);padding:0 var(--s4);border-radius:var(--rp);
  background:var(--g2);border:1px solid var(--g4);color:var(--g8);
  font:var(--t-body);font-weight:600;cursor:pointer}
.who button.on{background:var(--act);border-color:var(--act-hi);color:var(--act-ink)}
.seg{display:flex;gap:var(--s2);flex-wrap:wrap;margin:var(--s2) 0}
.seg button{min-height:38px;padding:0 var(--s3);border-radius:var(--rp);background:var(--g1);
  border:1px solid var(--g4);color:var(--g8);font:var(--t-meta);font-weight:600;cursor:pointer}
.seg button.on{background:var(--act);border-color:var(--act-hi);color:var(--act-ink)}
.seg button .sub{display:block;font-weight:400;opacity:.8}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(96px,1fr));gap:var(--s2);margin-top:var(--s2)}
.grid button{position:relative;padding:0;border:2px solid transparent;border-radius:var(--r2);
  background:var(--g1);aspect-ratio:2/3;overflow:hidden;cursor:pointer}
.grid button img{width:100%;height:100%;object-fit:cover;display:block}
.grid button.on{border-color:var(--act-hi);box-shadow:0 0 0 2px var(--act)}
.grid button .tag{position:absolute;left:0;right:0;bottom:0;padding:2px 4px;font:var(--t-small);
  color:#fff;background:rgba(0,0,0,.55);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.field{display:flex;flex-direction:column;gap:2px;margin-top:var(--s3)}
.field span{font:var(--t-meta);font-weight:600;color:var(--g8)}
.field input,.field textarea,.field select{min-height:var(--tap);background:var(--g1);color:var(--g9);
  border:1px solid var(--g4);border-radius:var(--r2);padding:var(--s2);font-size:16px;width:100%}
.field textarea{min-height:72px;resize:vertical}
.chips{display:flex;flex-wrap:wrap;gap:var(--s1);margin-top:var(--s2)}
.chips button{min-height:30px;padding:0 var(--s3);border-radius:var(--rp);background:var(--g2);
  border:1px solid var(--g4);color:var(--g8);font:var(--t-small);cursor:pointer}
.clip{display:flex;gap:var(--s3);padding:var(--s3);margin-bottom:var(--s2);background:var(--g1);
  border:1px solid var(--g3);border-radius:var(--r2)}
.clip video{width:160px;max-width:40vw;aspect-ratio:4/5;background:#000;border-radius:var(--r1)}
.clip .t{flex:1;min-width:0}
.clip .t b{display:block;font:var(--t-lead);color:var(--g9)}
.clip .t span{display:block;font:var(--t-meta);color:var(--g7)}
.clip .takes{display:flex;flex-wrap:wrap;gap:var(--s2)}
.picks{list-style:none;margin:var(--s3) 0 0;padding:0}
.picks li{display:flex;justify-content:space-between;gap:var(--s3);
  padding:var(--s2) 0;border-top:1px solid var(--g3);font:var(--t-meta);color:var(--g7)}
.picks li b{color:var(--g9);font-variant-numeric:tabular-nums}
"""

BODY = """
<div class=wrap id=app>
  <div class=col-main>
    <h2>Character</h2>
    <div class=who id=who></div>
    <div id=form></div>
    <h2>Her clips</h2>
    <div id=clips></div>
  </div>
  <div class=col-rail><div id=rail></div></div>
</div>
<div id=bars></div>
"""

OWN_JS = r"""
const $=id=>document.getElementById(id);
let cat=null, who=null, keepers=[], clipsList=[];
let st={src:'keeper', keeper:null, outfit:'', hair:'', setting:'', framing:'waist',
        motion:'', seconds:5, quality:'medium', takes:1, name:''};

async function load(){
  try{ cat=await SM.getJSON('/video/catalog'); }
  catch(e){ $('form').innerHTML='<div class=errbox><b>Could not load</b>'+SM.esc(e.message)+'</div>'; return; }
  if(!who && cat.characters.length) who=cat.characters[0].character;
  await pick(who);
}
async function pick(c){
  who=c; st.keeper=null; keepers=[]; clipsList=[];
  draw();
  if(!who) return;
  try{ [keepers,clipsList]=await Promise.all([
      SM.getJSON('/video/keepers?character='+encodeURIComponent(who)),
      SM.getJSON('/video/clips?character='+encodeURIComponent(who))]); }
  catch(e){ SM.toast(e.message); }
  if(keepers.length && !st.keeper) st.keeper=keepers[0].path;
  draw();
}
async function refreshClips(){
  if(!who) return;
  try{ clipsList=await SM.getJSON('/video/clips?character='+encodeURIComponent(who)); }catch(e){ return; }
  SM.set($('clips'),null,clipsHtml());
}

const seg=(k,opts)=>'<div class=seg>'+opts.map(o=>'<button data-seg="'+k+'" data-v="'+SM.esc(o.v)+'"'
  +' class="'+(String(st[k])===String(o.v)?'on':'')+'">'+SM.esc(o.l)
  +(o.sub?'<span class=sub>'+SM.esc(o.sub)+'</span>':'')+'</button>').join('')+'</div>';

function legs(){ const cap=cat.leg_cap_s; const n=Math.max(1,Math.ceil(st.seconds/cap)); return n; }
function cost(){
  const q=cat.qualities.find(x=>x.id===st.quality);
  return (st.src==='still'?cat.still_s:0)+q.s_per_s*st.seconds*st.takes;
}

function draw(){
  const c=cat.characters.find(x=>x.character===who);
  SM.set($('who'),null, cat.characters.map(x=>
    '<button data-who="'+SM.esc(x.character)+'" class="'+(x.character===who?'on':'')+'">'
    +SM.esc(x.who)+'</button>').join('') || '<div class=empty><b>No approved LoRAs yet</b>'
    +'Choose an epoch on the judging tab first.</div>');
  if(!c){ SM.set($('form'),null,''); return; }
  let h='<h2>The still</h2><div class=card>'
    +seg('src',[{v:'keeper',l:'One of her keepers',sub:keepers.length+' judged keeps'},
                {v:'still',l:'Render a new one',sub:'through her LoRA, about a minute'}]);
  if(st.src==='keeper'){
    h+=keepers.length
      ? '<div class=grid>'+keepers.map(k=>'<button data-keeper="'+SM.esc(k.path)+'" class="'
          +(k.path===st.keeper?'on':'')+'"><img loading=lazy src="/video/thumb?w=300&path='
          +encodeURIComponent(k.path)+'" alt=""><span class=tag>'+SM.esc(k.title.replace(/^[^-]*- /,''))
          +'</span></button>').join('')+'</div>'
        +'<div class=basis>Newest first, from every set you judged for her. Identity lives in'
        +' this image - Wan takes no character LoRA.</div>'
      : '<div class=empty><b>No keepers yet</b>Judge a shoot of hers, or render a new still.</div>';
  } else {
    const hair=(c.hair||[]);
    h+='<label class=field><span>What she wears, and where</span>'
      +'<input data-f=outfit placeholder="a cream ribbed tank top, in her bedroom with the window behind her" value="'+SM.esc(st.outfit)+'"></label>'
      +'<label class=field><span>Setting (optional - a flat studio when blank)</span>'
      +'<input data-f=setting placeholder="soft afternoon daylight through a window" value="'+SM.esc(st.setting)+'"></label>'
      +'<label class=field><span>Hair</span><select data-f=hair>'
      +hair.map(o=>'<option value="'+SM.esc(o)+'"'+(o===st.hair?' selected':'')+'>'+SM.esc(o)+'</option>').join('')+'</select></label>'
      +'<div class=field><span>Framing</span>'+seg('framing',cat.framings.map(f=>({v:f.id,l:f.label})))+'</div>'
      +'<div class=basis>Rendered at her training size so her face keeps its pixels, then cropped'
      +' down to the video frame. Tighter framing holds identity better over a clip.</div>';
  }
  h+='</div>';
  h+='<h2>What happens</h2><div class=card>'
    +'<label class=field><span>The motion, in your words</span>'
    +'<textarea data-f=motion placeholder="she looks up into the camera and breaks into a warm smile">'+SM.esc(st.motion)+'</textarea></label>'
    +'<div class=chips>'+cat.motions.map(m=>'<button data-motion="'+SM.esc(m.text)+'">'+SM.esc(m.label)+'</button>').join('')+'</div>'
    +'<div class=basis>One pacing clause is added to every leg the same way, so a chained clip'
    +' does not speed up at the seams.</div>'
    +'<div class=field><span>Length</span>'+seg('seconds',[3,5,6,8,10,12,15].map(s=>({v:s,l:s+' s',
        sub:(Math.ceil(s/cat.leg_cap_s)>1?Math.ceil(s/cat.leg_cap_s)+' legs, chained':'one leg')})))+'</div>'
    +'<div class=field><span>Quality</span>'+seg('quality',cat.qualities.map(q=>({v:q.id,l:q.label,sub:q.note})))+'</div>'
    +'<div class=field><span>Takes</span>'+seg('takes',[1,2,3,4].map(n=>({v:n,l:n+(n===1?' take':' takes'),sub:'different seeds'})))+'</div>'
    +'<label class=field><span>Name the set (optional)</span>'
    +'<input data-f=name placeholder="from the first words of the motion when blank" value="'+SM.esc(st.name)+'"></label>'
    +'</div>';
  SM.set($('form'),null,h);
  SM.set($('clips'),null,clipsHtml());
  rail(c);
}

function clipsHtml(){
  if(!clipsList.length) return '<div class=card><div class=card-sub>Nothing yet. Her clips land here as they finish.</div></div>';
  return clipsList.map(v=>{
    const s=v.spec||{};
    const takes=v.takes.map(t=>'<video controls muted playsinline preload=metadata src="/video/file?path='
      +encodeURIComponent(t.file)+'"></video>').join('');
    return '<div class=clip><div class=t><b>'+SM.esc(v.name.slice(11).replace(/^video_/,'').replace(/-/g,' '))+'</b>'
      +'<span>'+SM.esc(v.date)+' &middot; '+(s.seconds||'?')+' s &middot; '+SM.esc(s.quality||'')
      +' &middot; '+v.takes.length+' of '+(s.takes||1)+' take'+((s.takes||1)===1?'':'s')
      +(v.done?'':' - still rendering')+'</span>'
      +(s.motion?'<span>&ldquo;'+SM.esc(s.motion)+'&rdquo;</span>':'')
      +'<div class=takes>'+takes+'</div></div></div>';
  }).join('');
}

function rail(c){
  const n=legs(), secs=cost(), ready=st.src==='keeper'?!!st.keeper:!!st.outfit.trim();
  const ok=ready&&st.motion.trim();
  SM.set($('rail'),null,'<div class=card><div class=card-head><h3>'+SM.esc(c.who)+'</h3></div>'
    +'<ul class=picks>'
    +'<li><span>still</span><b>'+(st.src==='keeper'?(st.keeper?'a keeper':'none picked'):(st.outfit.trim()?'new render':'no outfit yet'))+'</b></li>'
    +'<li><span>length</span><b>'+st.seconds+' s'+(n>1?' in '+n+' legs':'')+'</b></li>'
    +'<li><span>takes</span><b>'+st.takes+'</b></li>'
    +'<li><span>card time</span><b>about '+SM.dur(secs)+'</b></li></ul>'
    +'<div class=basis>'+(ok?'Queued as ONE job. Each take writes as it finishes.'
      :(!st.motion.trim()?'Say what happens.':st.src==='keeper'?'Tap a keeper.':'Say what she wears.'))+'</div></div>');
  SM.set($('bars'),null, ok?'<div class=actbar><button class="btn btn-primary" data-act=queue>Queue '
    +st.takes+' take'+(st.takes===1?'':'s')+' for '+SM.esc(c.who)+' &mdash; '+SM.dur(secs)+'</button></div>':'');
}

document.addEventListener('input',e=>{
  const f=e.target.closest('[data-f]'); if(!f) return;
  st[f.dataset.f]=f.value;
  const c=cat.characters.find(x=>x.character===who); if(c) rail(c);
});
document.addEventListener('change',e=>{
  const f=e.target.closest('select[data-f]'); if(!f) return;
  st[f.dataset.f]=f.value;
});
document.addEventListener('click',async e=>{
  const w=e.target.closest('[data-who]'); if(w){ pick(w.dataset.who); return; }
  const k=e.target.closest('[data-keeper]'); if(k){ st.keeper=k.dataset.keeper; draw(); return; }
  const s=e.target.closest('[data-seg]');
  if(s){ const v=s.dataset.v; st[s.dataset.seg]=isNaN(+v)?v:+v; draw(); return; }
  const m=e.target.closest('[data-motion]');
  if(m){ st.motion=m.dataset.motion; draw(); return; }
  const b=e.target.closest('[data-act]'); if(!b) return;
  if(b.dataset.act==='queue'){
    b.disabled=true;
    const c=cat.characters.find(x=>x.character===who);
    const source=st.src==='keeper'?{kind:'keeper',path:st.keeper}
      :{kind:'still',outfit:st.outfit,hair:st.hair||(c.hair||[])[0]||'',setting:st.setting,framing:st.framing};
    try{
      await SM.postJSON('/video/queue',{character:who,source:source,motion:st.motion,
        seconds:st.seconds,quality:st.quality,takes:st.takes,name:st.name});
      SM.toast('queued as one job',{label:'Open the queue',run:()=>SM.nav('gpu')});
      SM.recount();
    }catch(err){ SM.toast(err.message); }
    b.disabled=false;
  }
});

load().then(()=>SM.poll(20000,refreshClips));
"""

PAGE = page("SourceMode video", BODY, OWN_JS, OWN_CSS)


def video_router(cfg: dict):
    from fastapi import APIRouter, Body, HTTPException  # noqa: PLC0415
    from fastapi.responses import FileResponse, HTMLResponse  # noqa: PLC0415

    from ..assets.judge import judge_root  # noqa: PLC0415
    from ..config import ENGINE_ROOT, outputs_dir  # noqa: PLC0415
    from ..library import library_dir  # noqa: PLC0415
    from .. import video as V  # noqa: PLC0415

    r = APIRouter()

    def _inside(p: str, roots: list[Path]) -> Path:
        q = Path(p)
        try:
            q = q.resolve()
        except OSError as exc:
            raise HTTPException(404) from exc
        for root in roots:
            try:
                q.relative_to(root.resolve())
                if q.is_file():
                    return q
            except ValueError:
                continue
        raise HTTPException(404)

    @r.get("/video", response_class=HTMLResponse)
    def _page():
        return HTMLResponse(PAGE, headers={"Cache-Control": "no-store, max-age=0"})

    @r.get("/video/catalog")
    def _catalog() -> dict:
        from ..assets.lora import approved_characters  # noqa: PLC0415
        from ..assets.wardrobe import hair_options  # noqa: PLC0415

        chars = []
        for c in approved_characters(cfg):
            chars.append({"character": c["character"], "who": c["who"],
                          "hair": list(hair_options(c["character"]))})
        return {"characters": chars,
                "framings": [{"id": k, "label": v.replace("framed from the ", "")} for k, v in V.FRAMINGS.items()],
                "qualities": [{"id": k, "label": lab, "s_per_s": rate, "note": note}
                              for k, (lab, rate, note) in V.QUALITIES.items()],
                "motions": [{"label": lab, "text": txt} for lab, txt in V.MOTIONS],
                "leg_cap_s": V.leg_cap_seconds(cfg), "still_s": V.STILL_SECONDS,
                "fps": int(cfg["video"]["fps"])}

    @r.get("/video/keepers")
    def _keepers(character: str) -> list[dict]:
        c = character.strip().lower()
        if not c or any(x in c for x in ("/", "\\", "..")):
            raise HTTPException(400, "a character is required")
        return V.keepers(judge_root(cfg), c)

    @r.get("/video/clips")
    def _clips(character: str) -> list[dict]:
        c = character.strip().lower()
        if not c or any(x in c for x in ("/", "\\", "..")):
            raise HTTPException(400, "a character is required")
        return V.clips(library_dir(cfg), c)

    @r.get("/video/thumb")
    def _thumb(path: str, w: int = 300):
        from ..train.preview import web_copy  # noqa: PLC0415

        p = _inside(path, [library_dir(cfg), outputs_dir(cfg)])
        return FileResponse(web_copy(p, w))

    @r.get("/video/file")
    def _file(path: str):
        p = _inside(path, [library_dir(cfg)])
        media = "video/mp4" if p.suffix.lower() == ".mp4" else None
        return FileResponse(p, media_type=media)

    @r.post("/video/queue")
    def _queue(body: dict = Body(default={})) -> dict:
        from ..gpu import queue as q  # noqa: PLC0415
        from ..gpu.preflight import preflight  # noqa: PLC0415
        from ..assets.lora import resolve_lora  # noqa: PLC0415

        spec = V.VideoSpec.from_dict({**body, "character": str(body.get("character", "")).strip().lower()})
        try:
            spec.seconds = float(spec.seconds); spec.takes = int(spec.takes)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "length and takes must be numbers") from exc
        problems = V.validate(spec, leg_cap_s=V.leg_cap_seconds(cfg))
        if problems:
            raise HTTPException(400, "; ".join(problems))
        if spec.source.get("kind") == "keeper":
            _inside(spec.source["path"], [library_dir(cfg), outputs_dir(cfg)])   # ours, on disk
        if spec.source.get("kind") == "still" and not resolve_lora(cfg, spec.character):
            raise HTTPException(409, f"no approved LoRA for {spec.character} - pick a keeper instead")
        if len(V.legs_for(spec.seconds, V.leg_cap_seconds(cfg))) > 1 and not V.ffmpeg_exe(cfg):
            raise HTTPException(409, "a chained clip needs ffmpeg and there is none on this machine")
        out = outputs_dir(cfg)
        sp = V.write_spec(V.spec_path(out, spec), spec)
        py = ENGINE_ROOT / ".venv" / "Scripts" / "python.exe"
        cmd = [str(py), str(ENGINE_ROOT / "scripts" / "video" / "run_video.py"), str(sp)]
        job_like = {"cmd": cmd, "cwd": str(ENGINE_ROOT)}
        bad = preflight(job_like, out)
        if bad:
            raise HTTPException(409, "would fail at once: " + "; ".join(bad))
        label = f"{spec.character}:{(spec.name or spec.motion)[:40]}"
        doc = q.load(q.queue_path(out))
        job = q.add(doc, kind="video", label=label, cmd=cmd, cwd=str(ENGINE_ROOT),
                    note=f"{spec.takes} take(s) x {spec.seconds:g}s, {spec.quality}, from the video page")
        q.save(q.queue_path(out), doc)
        return {"queued": job["id"], "spec": str(sp)}

    return r
