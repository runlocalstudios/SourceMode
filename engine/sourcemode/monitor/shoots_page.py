"""Pick a character, tick shoots, queue them as ONE job.

Jeremy, 2026-10-04: "a tab where I could select any of the models that we have
an approved LoRA for and to run the game asset generation or the other shot
plans... if there are maybe 10 or 12 different small shot plans, check as many
off as I want and then queue them to run for a single model... tracked as one
job, not like 10 different jobs."

Only characters with an APPROVED LoRA are offered - an epoch chosen on the judge
page, or a lora dir pruned to one checkpoint, which is the same decision made by
hand. Nine checkpoints and no choice is undecided, not approved, and picking one
silently would be guessing at the decision the whole sweep exists to make.

The cost is stated before he commits: every shoot carries its shot count, and
the bar totals the ticked ones at the measured render rate.

    GET  /shoots          the page
    GET  /queue/shoots    characters + catalog + the measured rate
    POST /queue/shoot     {character, shoots:[ids]} -> ONE queued job
"""

from __future__ import annotations

from .ui import page

OWN_CSS = r"""
.who{display:flex;flex-wrap:wrap;gap:var(--s2);margin-bottom:var(--s4)}
.who button{min-height:var(--tap);padding:0 var(--s4);border-radius:var(--rp);
  background:var(--g2);border:1px solid var(--g4);color:var(--g8);
  font:var(--t-body);font-weight:600;cursor:pointer}
.who button.on{background:var(--act);border-color:var(--act-hi);color:var(--act-ink)}
.who button[disabled]{opacity:.4;cursor:default}
.who .sub{display:block;font:var(--t-small);font-weight:400;opacity:.8}
.sh{display:flex;align-items:flex-start;gap:var(--s3);width:100%;
  padding:var(--s3);margin-bottom:var(--s2);background:var(--g1);
  border:1px solid var(--g3);border-left:3px solid var(--g3);
  border-radius:var(--r2);color:var(--g8);text-align:left;cursor:pointer}
.sh.on{border-left-color:var(--act);background:var(--g2)}
.sh .box{flex:none;width:22px;height:22px;border-radius:var(--r1);
  border:2px solid var(--g5);display:flex;align-items:center;justify-content:center;
  font-size:14px;color:transparent;margin-top:2px}
.sh.on .box{background:var(--act);border-color:var(--act-hi);color:var(--act-ink)}
.sh .t{flex:1;min-width:0}
.sh .t b{display:block;font:var(--t-lead);color:var(--g9)}
.sh .t span{display:block;font:var(--t-meta);color:var(--g7)}
.sh .n{flex:none;font:var(--t-small);color:var(--g7);font-variant-numeric:tabular-nums}
"""

BODY = """
<div class=wrap id=app>
  <div class=col-main>
    <h2>Character</h2>
    <div class=who id=who></div>
    <div id=warn></div>
    <h2>Shoots</h2>
    <div id=list></div>
  </div>
  <div class=col-rail><div id=rail></div></div>
</div>
<div id=bars></div>
"""

OWN_JS = r"""
const $=id=>document.getElementById(id);
let data=null, who=null, picked=new Set();

async function load(){
  try{ data=await SM.getJSON('/queue/shoots'); }
  catch(e){ $('list').innerHTML='<div class=errbox><b>Could not load</b>'+SM.esc(e.message)+'</div>'; return; }
  if(!who && data.characters.length) who=data.characters[0].character;
  draw();
}

function draw(){
  SM.set($('who'),null, data.characters.map(c=>
    '<button data-who="'+SM.esc(c.character)+'" class="'+(c.character===who?'on':'')+'">'
    +SM.esc(c.who)+'<span class=sub>'+(c.appearance_ok?'ready':'no appearance record')+'</span>'
    +'</button>').join('') || '<div class=empty><b>No approved LoRAs yet</b>'
    +'Choose an epoch on the judging tab, or prune a character to the one you keep.</div>');

  const c=data.characters.find(x=>x.character===who);
  SM.set($('warn'),null, (c&&!c.appearance_ok)
    ? '<div class="banner you"><span class=msg><b>'+SM.esc(c.who)+' has no appearance record.</b>'
      +'<span class=why>She will render from the trigger alone - every trait the LoRA did not'
      +' learn will be missing. Add '+SM.esc(c.appearance_missing.join(', '))
      +' to characters/appearance.json first.</span></span></div>'
    : '');

  let h='';
  for(const b of data.buckets){
    h+='<h2>'+SM.esc(b.bucket)+'</h2>';
    for(const s of b.shoots)
      h+='<button class="sh'+(picked.has(s.id)?' on':'')+'" data-shoot="'+SM.esc(s.id)+'">'
        +'<span class=box>&#10003;</span><span class=t><b>'+SM.esc(s.label)+'</b>'
        +'<span>'+SM.esc(s.setting)+'</span></span>'
        +'<span class=n>'+s.shots+' shots</span></button>';
  }
  SM.set($('list'),null,h);
  bar();
}

function bar(){
  const n=[...picked].reduce((a,id)=>{
    for(const b of data.buckets) for(const s of b.shoots) if(s.id===id) return a+s.shots;
    return a;},0);
  const secs=n*data.s_per_shot;
  const c=data.characters.find(x=>x.character===who);
  if(!picked.size){
    SM.set($('bars'),null,'');
    SM.set($('rail'),null,'<div class=card><div class=card-sub>Tick a shoot to see what it costs.</div></div>');
    return;
  }
  SM.set($('rail'),null,'<div class=card><div class=card-head><h3>'+picked.size
    +' shoot'+(picked.size===1?'':'s')+'</h3></div>'
    +'<div class=card-sub><b>'+n+'</b> shots &middot; about <b>'+SM.dur(secs)
    +'</b> of GPU time</div>'
    +'<div class=basis>Queued as ONE job. Each shoot writes its own judge set as it'
    +' finishes, so a run that stops part-way still leaves the rest judgeable.</div></div>');
  SM.set($('bars'),null,'<div class=actbar>'
    +'<button class="btn btn-primary" data-act=queue>Queue '+picked.size+' shoot'
    +(picked.size===1?'':'s')+' for '+SM.esc(c?c.who:who)+' &mdash; '+SM.dur(secs)+'</button>'
    +'<button class="btn btn-ghost" data-act=clear>Clear</button></div>');
}

document.addEventListener('click',async e=>{
  const w=e.target.closest('[data-who]');
  if(w){ who=w.dataset.who; picked.clear(); draw(); return; }
  const s=e.target.closest('[data-shoot]');
  if(s){ const id=s.dataset.shoot;
    picked.has(id)?picked.delete(id):picked.add(id); draw(); return; }
  const b=e.target.closest('[data-act]'); if(!b) return;
  if(b.dataset.act==='clear'){ picked.clear(); draw(); return; }
  if(b.dataset.act==='queue'){
    b.disabled=true;
    try{
      await SM.postJSON('/queue/shoot',{character:who,shoots:[...picked]});
      SM.toast('queued as one job',{label:'Open the queue',run:()=>SM.nav('gpu')});
      picked.clear(); draw(); SM.recount();
    }catch(err){ SM.toast(err.message); b.disabled=false; }
  }
});

load();
"""

PAGE = page("SourceMode shoots", BODY, OWN_JS, OWN_CSS)


def shoots_router(cfg: dict):
    from fastapi import APIRouter  # noqa: PLC0415
    from fastapi.responses import HTMLResponse  # noqa: PLC0415

    r = APIRouter()

    @r.get("/shoots", response_class=HTMLResponse)
    def _page():
        return PAGE

    return r
