"""Music: one looping track per place in the game - make takes, hear them, ship one.

Jeremy, 2026-11-02: one right song for each district and venue, looping, no
silence between. Each place's prompt lives in `music/places.json`; a batch of
takes is ONE queue job (ACE-Step 1.5 XL through ComfyUI); each take gets a
player, keep/reject, "Hear the loop" and Ship.

"Hear the loop" plays the last eight seconds of the take fading into its first
eight, with the same four-second crossfade the game uses when the track comes
round again - the join he will hear every few minutes. Ship trims, evens the
loudness and writes `src/assets/music/<place>.mp3` into the game; nothing else
on this page writes there.

    GET  /music                    the page
    GET  /music/places             every place, its takes, what the game has
    POST /music/place/{id}         {tags?, bpm?, keyscale?, seconds?} -> the place
    POST /music/{id}/make          {count, model} -> ONE queued job
    POST /music/{id}/verdict       {name, verdict: keep|reject|null}
    POST /music/{id}/ship          {name} -> the shipped record
    GET  /music/file               ?place=&name=  a take
    GET  /music/game-file          ?place=        the track the game has now
"""

from __future__ import annotations

from .ui import page

#: seconds of crossfade where the track meets its own start; the game uses the same
LOOP_FADE_S = 4

OWN_CSS = r"""
.who{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:var(--s3)}
.who button{min-height:30px;padding:0 10px;border-radius:var(--rp);background:var(--g2);
  border:1px solid var(--g4);color:var(--g8);font:600 12px/1.2 var(--font);cursor:pointer}
.who button small{font-weight:400;color:var(--g7);margin-left:4px}
.who button.on{background:var(--act);border-color:var(--act-hi);color:var(--act-ink)}
.who button.on small{color:var(--act-ink)}
.prompt textarea{width:100%;min-height:96px;background:var(--g2);color:var(--g9);
  border:1px solid var(--g4);border-radius:var(--r1);padding:var(--s2);font:var(--t-meta)}
.knobs{display:flex;flex-wrap:wrap;gap:var(--s3);margin:var(--s2) 0}
.knobs label{display:flex;flex-direction:column;gap:2px;font:var(--t-small);color:var(--g7)}
.knobs input,.knobs select{min-height:36px;background:var(--g2);color:var(--g9);
  border:1px solid var(--g4);border-radius:var(--r1);padding:0 var(--s2);font:var(--t-meta)}
.knobs input{width:90px}
.ingame{font:var(--t-meta);color:var(--g8);margin:var(--s2) 0}
.ingame audio{display:block;width:100%;margin-top:4px}
.take audio{display:block;width:100%;margin:var(--s2) 0}
.take .meta{font:var(--t-small);color:var(--g7)}
.take.kept{border-left:3px solid var(--done)}
.take.rejected{opacity:.55}
.take .tagline{font:var(--t-small);color:var(--g7);margin-top:2px;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.btn.on{background:var(--act);border-color:var(--act-hi);color:var(--act-ink)}
h2 .muted{font:var(--t-meta);color:var(--g7)}
"""

BODY = """
<div class=wrap id=app>
  <div class=col-main>
    <h2>Place</h2>
    <div class=who id=who></div>
    <div id=place><div class=empty><b>Pick a place</b>Each one gets one track that loops.</div></div>
    <div id=takes></div>
  </div>
</div>
"""

OWN_JS = r"""
const $=id=>document.getElementById(id);
const FADE=__FADE__;
let places=[], models={}, keys=[], cur=null, showRejected=false;
try{ cur=localStorage.getItem('musicPlace'); }catch(e){}
const takeUrl=(p,n)=>'/music/file?place='+encodeURIComponent(p)+'&name='+encodeURIComponent(n);

async function load(){
  let d;
  try{ d=await SM.getJSON('/music/places'); }
  catch(e){ SM.set($('who'),null,'<div class=errbox><b>Could not load</b>'+SM.esc(e.message)+'</div>'); return; }
  places=d.places; models=d.models; keys=d.keys;
  if(cur && !places.some(p=>p.id===cur)) cur=null;
  bubbles(); render();
}
function bubbles(){
  SM.set($('who'),null,places.map(p=>{
    const kept=p.takes.filter(t=>t.verdict==='keep').length;
    const note=p.shipped?'in game':(kept?kept+' kept':(p.takes.length?p.takes.length+' takes':''));
    return '<button data-who="'+SM.esc(p.id)+'" class="'+(p.id===cur?'on':'')+'">'+SM.esc(p.label)
      +(note?'<small>'+SM.esc(note)+'</small>':'')+'</button>';
  }).join(''));
}
function opt(v,label,sel){ return '<option value="'+SM.esc(v)+'"'+(v===sel?' selected':'')+'>'+SM.esc(label)+'</option>'; }
function render(){
  const p=places.find(x=>x.id===cur);
  if(!p){ SM.set($('takes'),null,''); return; }
  const editing=document.activeElement && $('place').contains(document.activeElement);
  if(!editing){
    let h='<div class="card prompt"><div class=card-head><h3>'+SM.esc(p.label)+'</h3>'
      +'<span class=card-sub>'+SM.esc(p.kind)+' &middot; plays as '+SM.esc(p.id)+'.mp3</span></div>'
      +'<textarea id=tags spellcheck=false>'+SM.esc(p.tags)+'</textarea>'
      +'<div class=knobs>'
      +'<label>Tempo (bpm)<input id=bpm type=number min=40 max=200 value="'+p.bpm+'"></label>'
      +'<label>Key<select id=key>'+keys.map(k=>opt(k,k,p.keyscale)).join('')+'</select></label>'
      +'<label>Length (s)<input id=secs type=number min=30 max=360 value="'+p.seconds+'"></label>'
      +'<label>Takes<select id=count>'+[1,2,3,4,5,6,8].map(n=>opt(String(n),String(n),'4')).join('')+'</select></label>'
      +'<label>Model<select id=model>'+Object.keys(models).map(m=>opt(m,models[m].label,'turbo')).join('')+'</select></label>'
      +'</div><div class=btn-row>'
      +'<button class="btn btn-sm" id=save>Save prompt</button>'
      +'<button class="btn btn-sm btn-primary" id=make>Queue takes</button>'
      +'<span class=push></span></div>';
    if(p.shipped) h+='<div class=ingame>In the game: <b>'+SM.esc(p.shipped.take)+'</b>, shipped '+SM.esc(SM.ago(p.shipped.at))
      +'<audio controls preload=none src="/music/game-file?place='+encodeURIComponent(p.id)+'&v='+encodeURIComponent(p.shipped.at)+'"></audio></div>';
    else h+='<div class=ingame>Nothing in the game yet - it plays silence here.</div>';
    h+='</div>';
    SM.set($('place'),null,h);
  }
  const all=p.takes, shown=showRejected?all:all.filter(t=>t.verdict!=='reject');
  const hidden=all.length-shown.length;
  let t='<h2>Takes <span class=muted>'+all.length+(hidden?' &middot; '+hidden+' rejected hidden':'')+'</span></h2>';
  if(hidden||showRejected) t+='<div class=btn-row style="margin-bottom:var(--s2)"><button class="btn btn-sm btn-ghost" id=rej>'
    +(showRejected?'Hide rejected':'Show rejected')+'</button></div>';
  if(!shown.length) t+='<div class=empty><b>No takes yet</b>Queue a few - turbo makes a three-minute take in well under a minute once it starts.</div>';
  t+=shown.map(k=>{
    const inGame=p.shipped && p.shipped.take===k.name;
    return '<div class="card take'+(k.verdict==='keep'?' kept':'')+(k.verdict==='reject'?' rejected':'')+'" data-take="'+SM.esc(k.name)+'">'
      +'<div class=card-head><h3>'+SM.esc(k.name)+(inGame?' &middot; in the game':'')+'</h3>'
      +'<span class=meta>'+SM.esc(k.model||'')+' &middot; seed '+SM.esc(k.seed)+' &middot; '+SM.esc(k.bpm)+' bpm &middot; '+SM.esc(k.keyscale||'')
      +' &middot; '+SM.esc(SM.ago(k.made))+'</span></div>'
      +(k.tags && k.tags!==p.tags?'<div class=tagline title="'+SM.esc(k.tags)+'">'+SM.esc(k.tags)+'</div>':'')
      +'<audio controls preload=none src="'+takeUrl(p.id,k.name)+'"></audio>'
      +'<div class=btn-row>'
      +'<button class="btn btn-sm'+(k.verdict==='keep'?' on':'')+'" data-act=keep>Keep</button>'
      +'<button class="btn btn-sm'+(k.verdict==='reject'?' on':'')+'" data-act=reject>Reject</button>'
      +'<button class="btn btn-sm btn-ghost" data-act=loop>Hear the loop</button>'
      +'<span class=push></span>'
      +'<button class="btn btn-sm btn-primary" data-act=ship>'+(inGame?'Ship again':'Ship to game')+'</button>'
      +'</div></div>';
  }).join('');
  SM.set($('takes'),null,t);
}

/* ---- the loop preview: last 8 s fading into the first 8 s, FADE s of overlap ---- */
let actx=null, playing=[];
function stopLoop(){ for(const s of playing){ try{ s.stop(); }catch(e){} } playing=[]; }
async function hearLoop(url){
  stopLoop();
  for(const a of document.querySelectorAll('audio')) a.pause();
  actx=actx||new (window.AudioContext||window.webkitAudioContext)();
  await actx.resume();
  SM.toast('Loading the take');
  const buf=await actx.decodeAudioData(await (await fetch(url)).arrayBuffer());
  const W=8, from=Math.max(0,buf.duration-W), tail=buf.duration-from;
  const t0=actx.currentTime+0.15, seam=t0+tail-FADE;
  const end=actx.createBufferSource(), ge=actx.createGain();
  end.buffer=buf; end.connect(ge); ge.connect(actx.destination);
  ge.gain.setValueAtTime(1,seam); ge.gain.linearRampToValueAtTime(0,seam+FADE);
  end.start(t0,from);
  const head=actx.createBufferSource(), gh=actx.createGain();
  head.buffer=buf; head.connect(gh); gh.connect(actx.destination);
  gh.gain.setValueAtTime(0,seam); gh.gain.linearRampToValueAtTime(1,seam+FADE);
  head.start(seam,0); head.stop(seam+FADE+W);
  playing=[end,head];
  SM.toast('Playing the join', {label:'Stop', run:stopLoop});
}

$('who').addEventListener('click',e=>{
  const b=e.target.closest('button[data-who]'); if(!b) return;
  cur=b.dataset.who; try{ localStorage.setItem('musicPlace',cur); }catch(err){}
  if(document.activeElement) document.activeElement.blur();
  bubbles(); render();
});
function knobs(){
  return {tags:$('tags').value, bpm:Number($('bpm').value), keyscale:$('key').value, seconds:Number($('secs').value)};
}
$('place').addEventListener('click',async e=>{
  const b=e.target.closest('button'); if(!b) return;
  try{
    if(b.id==='save'){
      await SM.postJSON('/music/place/'+encodeURIComponent(cur),knobs());
      SM.toast('Prompt saved');
    } else if(b.id==='make'){
      await SM.postJSON('/music/place/'+encodeURIComponent(cur),knobs());
      const r=await SM.postJSON('/music/'+encodeURIComponent(cur)+'/make',{count:Number($('count').value),model:$('model').value});
      SM.toast('Queued '+r.queued, {label:'Queue', run:()=>SM.nav('gpu')});
    }
    b.blur(); await load();
  }catch(err){ SM.toast(err.message); }
});
$('takes').addEventListener('click',async e=>{
  const b=e.target.closest('button'); if(!b) return;
  if(b.id==='rej'){ showRejected=!showRejected; render(); return; }
  const card=b.closest('[data-take]'); if(!card) return;
  const name=card.dataset.take, act=b.dataset.act;
  try{
    if(act==='loop'){ await hearLoop(takeUrl(cur,name)); return; }
    if(act==='keep'||act==='reject'){
      const t=places.find(x=>x.id===cur).takes.find(x=>x.name===name);
      await SM.postJSON('/music/'+encodeURIComponent(cur)+'/verdict',{name:name,verdict:t.verdict===act?null:act});
    } else if(act==='ship'){
      b.disabled=true; b.textContent='Shipping';
      const r=await SM.postJSON('/music/'+encodeURIComponent(cur)+'/ship',{name:name});
      SM.toast((r.replaced?'Replaced the game track with ':'Shipped ')+name);
    }
    await load();
  }catch(err){ SM.toast(err.message); b.disabled=false; }
});
load();
/* a refresh rewrites the take list, which would cut off a take he is listening to */
const busy=()=>playing.length>0||[...document.querySelectorAll('audio')].some(a=>!a.paused);
SM.poll(20000,async()=>{ if(!busy()) await load(); });
""".replace("__FADE__", str(LOOP_FADE_S))

PAGE = page("Music", BODY, OWN_JS, OWN_CSS)


def music_router(cfg: dict):
    from fastapi import APIRouter, Body, HTTPException  # noqa: PLC0415
    from fastapi.responses import FileResponse, HTMLResponse  # noqa: PLC0415

    from ..music import core as M  # noqa: PLC0415

    r = APIRouter()

    def _pid(place_id: str) -> str:
        try:
            M.check_place_id(place_id)
            M.place(place_id)
        except (ValueError, KeyError) as exc:
            raise HTTPException(404, str(exc)) from exc
        return place_id

    @r.get("/music", response_class=HTMLResponse)
    def _page():
        return HTMLResponse(PAGE, headers={"Cache-Control": "no-store"})

    @r.get("/music/places")
    def _places() -> dict:
        shipped = M.shipped(cfg)
        out = []
        for p in M.places():
            out.append({**p, "takes": M.takes(cfg, p["id"]), "shipped": shipped.get(p["id"])})
        return {"places": out, "keys": M.KEYS,
                "models": {k: {"label": v["label"]} for k, v in M.MODELS.items()}}

    @r.get("/music/file")
    def _file(place: str, name: str):
        try:
            f = M.take_path(cfg, _pid(place), name)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        return FileResponse(f, media_type="audio/mpeg")

    @r.get("/music/game-file")
    def _game_file(place: str):
        f = M.game_music_dir() / f"{_pid(place)}.mp3"
        if not f.is_file():
            raise HTTPException(404, "the game has no track for this place")
        return FileResponse(f, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})

    @r.post("/music/place/{place_id}")
    def _edit(place_id: str, body: dict = Body(default={})) -> dict:
        try:
            return M.update_place(_pid(place_id), body)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @r.post("/music/{place_id}/make")
    def _make(place_id: str, body: dict = Body(default={})) -> dict:
        from ..config import ENGINE_ROOT, outputs_dir  # noqa: PLC0415
        from ..gpu import queue as q  # noqa: PLC0415
        from ..gpu.preflight import preflight  # noqa: PLC0415

        pid = _pid(place_id)
        try:
            count = int(body.get("count") or 4)
            spec = M.write_spec(cfg, pid, count=count, model=str(body.get("model") or "turbo"))
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        cmd = M.make_command(spec)
        out = outputs_dir(cfg)
        bad = preflight({"cmd": cmd, "cwd": str(ENGINE_ROOT)}, out)
        if bad:
            raise HTTPException(409, "would fail at once: " + "; ".join(bad))
        doc = q.load(q.queue_path(out))
        label = f"music:{pid}:{spec.stem[6:]}"
        job = q.add(doc, kind="music", label=label, cmd=cmd, cwd=str(ENGINE_ROOT),
                    note=f"{count} {body.get('model') or 'turbo'} take(s) for {pid}, from the Music tab",
                    expect={"total": count, "what": f"{count} take{'s' if count != 1 else ''}"})
        q.save(q.queue_path(out), doc)
        return {"queued": job["id"], "spec": str(spec)}

    @r.post("/music/{place_id}/verdict")
    def _verdict(place_id: str, body: dict = Body(default={})) -> dict:
        try:
            return M.set_verdict(cfg, _pid(place_id), str(body.get("name") or ""), body.get("verdict"))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @r.post("/music/{place_id}/ship")
    def _ship(place_id: str, body: dict = Body(default={})) -> dict:
        try:
            return M.ship(cfg, _pid(place_id), str(body.get("name") or ""))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(500, str(exc)) from exc

    return r
