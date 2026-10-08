"""The Looks tab: review and confirm every character's appearance record.

    GET  /appearance                   the page
    GET  /appearance/list              every record, unconfirmed first
    GET  /appearance/ref?char=&name=   one reference photo (web-sized)
    POST /appearance/<char>/confirm    {prompt, frame, negative} -> confirmed record

Jeremy, 2026-10-06, after Bri's invented "lighter caramel ends" and Jaina's
freckles: "I need to now review all of these because they're so fucked up that
I can't trust them." Each card puts her reference photos beside the exact text
every render of her carries, with race words marked (his rule: no race in any
prompt). Confirm writes his text and binds it to a fingerprint; check() - the
pre-flight the sweep and the shoots already run - refuses anything unconfirmed.
"""

from __future__ import annotations

import re
from pathlib import Path

from .ui import page

REFS = Path("C:/Epic Games/Files/cnc info/codex/references")
EXT = (".png", ".jpg", ".jpeg", ".webp")
#: Words that name a race or ethnicity. Highlighted, never auto-removed - he edits.
RACE = re.compile(r"\b(?:white|black|latina|latino|hispanic|asian|half-asian|east asian|"
                  r"southeast asian|south asian|indian|filipina|korean|japanese|chinese|"
                  r"vietnamese|thai|irish|italian|italian-american|mediterranean|caucasian|"
                  r"african|middle eastern|arab|persian|mixed|biracial)\b", re.I)
FRAMES = ("", "tiny frame", "petite frame", "slim frame", "athletic frame", "curvy frame")


def _refs(char: str) -> list[str]:
    if not REFS.is_dir():
        return []
    return [p.name for p in sorted(REFS.iterdir())
            if p.suffix.lower() in EXT and p.stem.split("_")[0].lower() == char]


def records() -> list[dict]:
    from ..assets import appearance as A  # noqa: PLC0415

    A.reload()
    look = A._load()["look"]
    out = []
    # every record we have, plus every key character the game has that we do
    # not: she appears with empty fields, and confirming her writes the record
    names = {c for c in look if not c.startswith("_")} | set(A.key_characters())
    for c in sorted(names):
        rec = look.get(c) or {}
        g = A.game_facts(c)
        out.append({
            "character": c, "age": A.age_of(c), "own_age": rec.get("age"),
            "state_age": rec.get("age_in_prompt", True) is not False,
            "game_age": (A._load()["ages"] or {}).get(c), "prompt": rec.get("prompt", ""),
            "frame": rec.get("frame", ""), "negative": rec.get("negative", ""),
            "note": rec.get("_note", ""), "confirmed": A.confirmed(c),
            "confirmed_at": (rec.get("confirmed") or {}).get("at"),
            "race": sorted({m.group(0) for m in RACE.finditer(rec.get("prompt", ""))}),
            "game": g.get("opening", ""), "refs": _refs(c),
        })
    out.sort(key=lambda r: (r["confirmed"], r["character"]))
    return out


OWN_CSS = r"""
html,body{overflow-x:hidden}
/* one column: the shared .wrap reserves a rail this page does not have */
#app{display:block;max-width:760px;margin:0 auto;padding:0 var(--s3);box-sizing:border-box}
#app,.col-main{min-width:0;width:100%;overflow-x:hidden}
.lk{margin-bottom:var(--s4);min-width:0;max-width:100%;box-sizing:border-box}
#who{width:100%;min-height:var(--tap);margin-bottom:var(--s2);background:var(--g1);color:var(--g9);
  border:1px solid var(--g4);border-radius:var(--r2);padding:0 var(--s2);font-size:16px}
.lk .refs{display:flex;gap:var(--s2);overflow-x:auto;padding-bottom:var(--s2);
  max-width:100%;-webkit-overflow-scrolling:touch}
.lk .refs img{height:220px;border-radius:var(--r1);background:var(--photo);flex:none;cursor:zoom-in}
.lk .game{font:var(--t-small);color:var(--g6);margin:var(--s2) 0}
.lk textarea{width:100%;box-sizing:border-box;min-height:120px;padding:var(--s3);
  background:var(--g1);border:1px solid var(--g4);border-radius:var(--r2);color:var(--g9);
  font-family:inherit;font-size:16px;line-height:1.45;resize:vertical;overflow:hidden}
.lk .hl{padding:var(--s2) var(--s3);background:var(--g0);border:1px dashed var(--g4);
  border-radius:var(--r2);font:var(--t-meta);color:var(--g7);margin-top:var(--s2)}
.lk .hl mark{background:var(--stop-bg);color:var(--stop-ink);border-radius:3px;padding:0 2px}
.lk .row{display:flex;gap:var(--s2);align-items:center;flex-wrap:wrap;margin-top:var(--s2)}
.lk select,.lk input{min-height:var(--tap);background:var(--g1);color:var(--g9);
  border:1px solid var(--g4);border-radius:var(--r2);padding:0 var(--s2);font-size:16px}
.lk input{flex:1;min-width:0;width:100%}
.lk select{max-width:60%}
.lk .note{font:var(--t-small);color:var(--g6);margin-top:var(--s2)}
.lk details summary{cursor:pointer}
#big{position:fixed;inset:0;z-index:60;background:rgba(0,0,0,.92);display:none;
  align-items:center;justify-content:center}
#big.on{display:flex}
#big img{max-width:96vw;max-height:94vh}
"""

BODY = """
<div class=wrap id=app>
  <div class=col-main>
    <h2>Looks</h2>
    <select id=who aria-label="character"></select>
    <div class=card-sub id=sum>loading&hellip;</div>
    <div id=list></div>
  </div>
</div>
<div id=big><img alt=""></div>
"""

OWN_JS = r"""
const $=id=>document.getElementById(id);
let recs=[];
const refUrl=(c,n)=>'/appearance/ref?char='+encodeURIComponent(c)+'&name='+encodeURIComponent(n);
const RACE=/\b(white|black|latina|latino|hispanic|asian|half-asian|east asian|southeast asian|south asian|indian|filipina|korean|japanese|chinese|vietnamese|thai|irish|italian|italian-american|mediterranean|caucasian|african|middle eastern|arab|persian|mixed|biracial)\b/gi;
const FRAMES=['','tiny frame','petite frame','slim frame','athletic frame','curvy frame'];

async function load(){
  try{ recs=await SM.getJSON('/appearance/list'); }
  catch(e){ $('list').innerHTML='<div class=errbox><b>Could not load</b> '+SM.esc(e.message)+'</div>'; return; }
  draw();
}
function marked(t){ return SM.esc(t).replace(RACE,m=>'<mark>'+m+'</mark>'); }
/* Jeremy, 2026-10-07: "I want to be able to revisit any of the girls' looks
   from a drop down even if they are already approved" - cat's confirmed record
   rendered her old and hard. The page opens on what still needs review; the
   dropdown reaches anyone, confirmed or not. Kept in the hash so a reload or a
   Confirm stays on the same character. */
let pick=decodeURIComponent(location.hash.slice(1))||'';
function drawPicker(){
  const open=recs.filter(r=>!r.confirmed);
  const opt=(v,t)=>'<option value="'+SM.esc(v)+'"'+(v===pick?' selected':'')+'>'+SM.esc(t)+'</option>';
  $('who').innerHTML=opt('','Needs review ('+open.length+')')+opt('*','Everyone ('+recs.length+')')
    +recs.slice().sort((a,b)=>a.character.localeCompare(b.character))
      .map(r=>opt(r.character,r.character+(r.confirmed?'  ✓':'  • needs review'))).join('');
}
$('who').addEventListener('change',e=>{
  pick=e.target.value; history.replaceState(null,'','#'+encodeURIComponent(pick)); draw();
  window.scrollTo(0,0);
});
function shown(){
  if(pick==='*') return recs;
  if(pick) return recs.filter(r=>r.character===pick);
  const open=recs.filter(r=>!r.confirmed);
  return open.length?open:recs;
}
function draw(){
  drawPicker();
  const open=recs.filter(r=>!r.confirmed).length;
  $('sum').textContent=open?(open+' of '+recs.length+' still to confirm. A sweep or shoot will not render a character until her record is confirmed.')
                            :('All '+recs.length+' confirmed.');
  SM.set($('list'),null,shown().map(r=>{
    const frames=FRAMES.includes(r.frame)?FRAMES:FRAMES.concat([r.frame]);
    return '<div class="card lk '+(r.confirmed?'e-done':'e-you')+'" data-c="'+SM.esc(r.character)+'">'
      +'<div class=card-head>'+SM.pill(r.confirmed?'done':'you')
      +'<h3>'+SM.esc(r.character)+(r.age?' &middot; '+r.age:'')+'</h3>'
      +(r.confirmed?'<span class=age>confirmed '+SM.esc(SM.ago(r.confirmed_at))+'</span>':'')+'</div>'
      +(r.refs.length?'<div class=refs>'+r.refs.map(n=>'<img loading=lazy src="'+refUrl(r.character,n)+'" alt="'+SM.esc(n)+'">').join('')+'</div>'
                     :'<div class=card-sub>No reference photos.</div>')
      +(r.game?'<div class=game>Game: '+SM.esc(r.game)+'</div>':'')
      +'<textarea data-k=prompt spellcheck=false>'+SM.esc(r.prompt)+'</textarea>'
      +'<div class=hl data-hl>'+(r.race.length?marked(r.prompt):'No race words.')+'</div>'
      +'<div class=row><label><input type=checkbox data-k=state_age style="width:auto;min-height:0;flex:none"'+(r.state_age?' checked':'')+'> State age</label>'
      +'<input data-k=age inputmode=numeric style="flex:0 0 5em;width:5em" value="'
        +SM.esc(r.own_age==null?'':String(r.own_age))+'" placeholder="'+SM.esc(r.game_age==null?'':String(r.game_age))+'">'
        +'<span class=dim>'+(r.game_age!=null?'game: '+r.game_age+'; blank uses it':'not in the game')+'. Untick to leave age to the LoRA.</span></div>'
      +'<div class=row><label>Fit</label><select data-k=frame>'
        +frames.map(f=>'<option value="'+SM.esc(f)+'"'+(f===r.frame?' selected':'')+'>'+(f||'(none)')+'</option>').join('')
      +'</select><input data-k=negative placeholder="negative (optional)" value="'+SM.esc(r.negative||'')+'"></div>'
      +'<div class=row><button class="btn btn-primary" data-act=confirm>'+(r.confirmed?'Save &amp; re-confirm':'Confirm')+'</button></div>'
      +(r.note?'<details class=note><summary>notes</summary>'+SM.esc(r.note)+'</details>':'')
      +'</div>';
  }).join(''));
  for(const t of document.querySelectorAll('.lk textarea')) fit(t);
}
/* the whole prompt visible at once - no inner scrolling to read what she is */
function fit(t){ t.style.height='auto'; t.style.height=(t.scrollHeight+2)+'px'; }
document.addEventListener('input',e=>{
  if(e.target.tagName==='TEXTAREA') fit(e.target);
  if(e.target.dataset.k!=='prompt') return;
  const card=e.target.closest('.lk'), t=e.target.value, hl=card.querySelector('[data-hl]');
  hl.innerHTML=RACE.test(t)?marked(t):'No race words.'; RACE.lastIndex=0;
});
document.addEventListener('click',async e=>{
  const img=e.target.closest('.refs img');
  if(img){ $('big').querySelector('img').src=img.src; $('big').classList.add('on'); return; }
  if(e.target.closest('#big')){ $('big').classList.remove('on'); return; }
  const b=e.target.closest('[data-act=confirm]'); if(!b) return;
  const card=b.closest('.lk'), c=card.dataset.c, val=k=>card.querySelector('[data-k='+k+']').value, ticked=k=>card.querySelector('[data-k='+k+']').checked;
  b.disabled=true;
  try{
    await SM.postJSON('/appearance/'+encodeURIComponent(c)+'/confirm',
      {prompt:val('prompt'),frame:val('frame'),negative:val('negative'),age:val('age'),state_age:ticked('state_age')});
    SM.toast(c+' confirmed');
    await load();
  }catch(err){ SM.toast(err.message); b.disabled=false; }
});
load();
"""

PAGE = page("Looks", BODY, OWN_JS, OWN_CSS)


def appearance_router(cfg: dict):
    from fastapi import APIRouter, Body, HTTPException  # noqa: PLC0415
    from fastapi.responses import FileResponse, HTMLResponse  # noqa: PLC0415

    r = APIRouter()

    @r.get("/appearance", response_class=HTMLResponse)
    def _page():
        return HTMLResponse(PAGE, headers={"Cache-Control": "no-store"})

    @r.get("/appearance/list")
    def _list() -> list[dict]:
        return records()

    @r.get("/appearance/ref")
    def _ref(char: str, name: str):
        from ..train.preview import web_copy  # noqa: PLC0415

        c = char.lower()
        if "/" in name or "\\" in name or ".." in name or name not in _refs(c):
            raise HTTPException(404)
        return FileResponse(web_copy(REFS / name))

    @r.post("/appearance/{char}/confirm")
    def _confirm(char: str, body: dict = Body(...)) -> dict:
        from ..assets import appearance as A  # noqa: PLC0415

        try:
            rec = A.confirm(char, {**{k: body.get(k, "") for k in A.CONFIRM_FIELDS},
                                   "age": body.get("age", ""),
                                   "state_age": body.get("state_age", True)})
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"character": char.lower(), "confirmed": rec["confirmed"]}

    return r
