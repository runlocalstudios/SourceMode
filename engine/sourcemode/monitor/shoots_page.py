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
/* Jeremy, 2026-10-14: 36 names filled his whole phone screen - 10px chips, tight. */
.who{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:var(--s3)}
.who button{min-height:26px;padding:0 8px;border-radius:var(--rp);
  background:var(--g2);border:1px solid var(--g4);color:var(--g8);
  font:600 10px/1.2 var(--font);cursor:pointer}
.who button.on{background:var(--act);border-color:var(--act-hi);color:var(--act-ink)}
.who button[disabled]{opacity:.4;cursor:default}
.who .sub{display:block;font:400 9px/1.2 var(--font);opacity:.8}
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
.sh .t em{display:block;font:var(--t-small);font-style:normal;color:var(--g6);margin-top:2px}
.sh.ship{border-color:var(--g4);background:var(--g2)}
.sh.ship.on{border-left-color:var(--act)}
.sh.off{opacity:.55;cursor:default}
.sh.off .box{border-style:dashed}
.sh .blocked{display:block;font:var(--t-small);color:var(--you-ink);margin-top:2px}
/* Mix your own: three pickers, one combo */
.mix .mixrow{display:flex;gap:var(--s2);flex-wrap:wrap}
.mixf{flex:1;min-width:150px;display:flex;flex-direction:column;gap:2px}
.mixf span{font:var(--t-meta);font-weight:600;color:var(--g8)}
.mix select{min-height:var(--tap);background:var(--g1);color:var(--g9);border:1px solid var(--g4);
  border-radius:var(--r2);padding:0 var(--s2);font-size:16px;width:100%}
.mix .row{display:flex;gap:var(--s2);margin-top:var(--s2)}
.mix .blocked{color:var(--you-ink)}
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
    <div id=warn></div>
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
  /* Jeremy, 2026-10-23: the Characters tab's "Shoots" button after approving
     her 28 hands her name over in the hash; select her, once, then drop the
     hash so a later manual pick is not pulled back to her on every reload */
  const asked=decodeURIComponent(location.hash.slice(1));
  if(asked){
    if(data.characters.some(x=>x.character===asked) && asked!==who){ who=asked; picked.clear(); }
    history.replaceState(null,'',location.pathname);
  }
  if(!who && data.characters.length) who=data.characters[0].character;
  draw();
}
window.addEventListener('hashchange',()=>load());

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
      +' learn will be missing. Missing: '+SM.esc(c.appearance_missing.join(', '))
      +'.</span></span>'
      +'<button class="btn btn-sm" data-act=newchar>Document her</button></div>'
    : '');

  const blocked=(c&&c.blocked)||{};
  let h=mixCard(c);
  for(const b of data.buckets){
    h+='<h2>'+SM.esc(b.label||b.bucket)+'</h2>';
    for(const s of b.shoots){
      const why=blocked[s.id];
      h+='<button class="sh'+(b.bucket==='game'?' ship':'')
        +(picked.has(s.id)?' on':'')+(why?' off':'')+'" data-shoot="'+SM.esc(s.id)+'"'
        +(why?' disabled':'')+'>'
        +'<span class=box>&#10003;</span><span class=t><b>'+SM.esc(s.label)+'</b>'
        +'<span>'+SM.esc(s.setting)+'</span>'
        +(s.note?'<em>'+SM.esc(s.note)+'</em>':'')
        +(why?'<span class=blocked>'+SM.esc(why)+'</span>':'')+'</span>'
        +'<span class=n>'+s.shots+' shots<br>'+SM.dur(cost(s))+'</span></button>';
    }
  }
  SM.set($('list'),null,h);
  bar();
}

function find(id){
  for(const b of data.buckets) for(const s of b.shoots) if(s.id===id) return s;
  return comboOf(id);
}

/* --- mix your own --------------------------------------------------------
   Jeremy, 2026-10-12: "the shot type (club, boudoir) as one option, clothing
   as another option (club outfit, lingerie, casual)... a picture of her at
   the club but wearing work outfit? No problem." Three pickers; the combo
   id <scene>-<wardrobe>-<poses> is a shoot like any other once added. */
let mixPick={scene:'bedroom',wardrobe:'lingerie',poses:'submissive'};
const byId=(list,id)=>list.find(x=>x.id===id);
function comboOf(id){
  const p=(id||'').split('-'); if(p.length!==3||!data.mix) return null;
  const sc=byId(data.mix.scenes,p[0]), w=byId(data.mix.wardrobes,p[1]), pp=byId(data.mix.poses,p[2]);
  if(!sc||!w||!pp) return null;
  return {id, label:sc.label+' / '+w.label+' / '+pp.label, shots:pp.n, kind:'shoot',
          setting:'', note:pp.note};
}
/* same rule as the server's combo_problem, so the greyed option and the 409 agree */
function mixWhy(c,sc,w,pp){
  const miss=pp.needs.filter(n=>!sc.has.includes(n));
  if(miss.length) return 'needs a '+miss.join(' and a ');
  if(w.record==='job' && !(c&&c.job_outfits)) return 'no job outfit in her record';
  return '';
}
function mixCard(c){
  if(!data.mix) return '';
  const m=data.mix;
  if(!byId(m.scenes,mixPick.scene)) mixPick.scene=m.scenes[0].id;
  if(!byId(m.wardrobes,mixPick.wardrobe)) mixPick.wardrobe=m.wardrobes[0].id;
  if(!byId(m.poses,mixPick.poses)) mixPick.poses=m.poses[0].id;
  const sc=byId(m.scenes,mixPick.scene), w=byId(m.wardrobes,mixPick.wardrobe), pp=byId(m.poses,mixPick.poses);
  const opt=(o,sel,why)=>'<option value="'+SM.esc(o.id)+'"'+(o.id===sel?' selected':'')+(why?' disabled':'')+'>'
    +SM.esc(o.label)+(why?' - '+SM.esc(why):'')+'</option>';
  const sel=(k,label,opts)=>'<label class=mixf><span>'+label+'</span><select data-mix="'+k+'">'+opts+'</select></label>';
  const why=mixWhy(c,sc,w,pp);
  const id=sc.id+'-'+w.id+'-'+pp.id;
  const s=comboOf(id);
  return '<h2>Mix your own</h2><div class="card mix">'
    +'<div class=mixrow>'
    +sel('scene','Scene',m.scenes.map(o=>opt(o,mixPick.scene,pp.needs.some(n=>!o.has.includes(n))?'needs a '+pp.needs.filter(n=>!o.has.includes(n)).join(' and a '):'')).join(''))
    +sel('wardrobe','Wardrobe',m.wardrobes.map(o=>opt(o,mixPick.wardrobe,o.record==='job'&&!(c&&c.job_outfits)?'no job outfit in her record':'')).join(''))
    +sel('poses','Poses',m.poses.map(o=>opt(o,mixPick.poses,o.needs.some(n=>!sc.has.includes(n))?'needs a '+o.needs.filter(n=>!sc.has.includes(n)).join(' and a '):'')).join(''))
    +'</div>'
    +'<div class=card-sub>'+(why?'<span class=blocked>'+SM.esc(why)+'</span>'
      :'<b>'+s.shots+'</b> shots &middot; '+SM.dur(cost(s))+(pp.note?' &middot; '+SM.esc(pp.note):''))+'</div>'
    +'<div class=row><button class="btn btn-sm btn-primary" data-act=mixadd'+(why||picked.has(id)?' disabled':'')+'>'
    +(picked.has(id)?'Added':'Add to the selection')+'</button></div></div>';
}
document.addEventListener('change',e=>{
  const s=e.target.closest('[data-mix]'); if(!s) return;
  mixPick[s.dataset.mix]=s.value; draw();
});
/* An asset-pack shot costs ~116s and a sweep render ~75s. One rate across a
   mixed selection understated the 112-shot pack by over an hour. */
function cost(s){ return s.shots*(s.kind==='pack'?data.s_per_pack_shot:data.s_per_shot); }

function bar(){
  const sel=[...picked].map(find).filter(Boolean);
  const n=sel.reduce((a,s)=>a+s.shots,0);
  const secs=sel.reduce((a,s)=>a+cost(s),0);
  const c=data.characters.find(x=>x.character===who);
  if(!sel.length){
    SM.set($('bars'),null,'');
    SM.set($('rail'),null,'<div class=card><div class=card-sub>Tick anything to see what it costs.</div></div>');
    return;
  }
  const word=s=>s+(sel.length===1?'':'s');
  SM.set($('rail'),null,'<div class=card><div class=card-head><h3>'+sel.length
    +' '+word('selection')+'</h3></div>'
    +'<div class=card-sub><b>'+n+'</b> shots &middot; about <b>'+SM.dur(secs)
    +'</b> of GPU time</div>'
    +'<ul class=picks>'+sel.map(s=>'<li><span>'+SM.esc(s.label)+'</span><b>'
      +SM.dur(cost(s))+'</b></li>').join('')+'</ul>'
    +'<div class=basis>Queued as ONE job. Each one writes its own output as it'
    +' finishes, so a run that stops part-way still leaves the rest usable.</div></div>');
  SM.set($('bars'),null,'<div class=actbar>'
    +'<button class="btn btn-primary" data-act=queue>Queue '+sel.length+' '
    +word('selection')+' for '+SM.esc(c?c.who:who)+' &mdash; '+SM.dur(secs)+'</button>'
    +'<button class="btn btn-ghost" data-act=clear>Clear</button></div>');
}

document.addEventListener('click',async e=>{
  const w=e.target.closest('[data-who]');
  if(w){ who=w.dataset.who; picked.clear(); draw(); return; }  /* blocked set differs per character */
  const s=e.target.closest('[data-shoot]');
  if(s){ if(s.disabled) return;
    const id=s.dataset.shoot;
    picked.has(id)?picked.delete(id):picked.add(id); draw(); return; }
  const b=e.target.closest('[data-act]'); if(!b) return;
  /* New character lives on the Characters tab now (2026-10-11) */
  if(b.dataset.act==='newchar'){ SM.nav('characters',who||''); return; }
  if(b.dataset.act==='clear'){ picked.clear(); draw(); return; }
  if(b.dataset.act==='mixadd'){ picked.add(mixPick.scene+'-'+mixPick.wardrobe+'-'+mixPick.poses); draw(); return; }
  if(b.dataset.act==='queue'){
    b.disabled=true;
    try{
      await SM.postJSON('/queue/shoot',{character:who,shoots:[...picked]});
      SM.toast('queued as one job',{label:'Open the queue',run:()=>SM.nav('gpu')});
      picked.clear(); draw(); SM.recount();
    }catch(err){ SM.toast(err.message); b.disabled=false; }
  }
});

/* Jeremy, 2026-10-18: "i currently have to reload the browser after saving a
   character's game asset looks in order to run the game asset wardrobe photo
   shoot". The hub keeps this frame alive between tabs, so the catalog read at
   first load - who has approved looks, what is greyed - went stale the moment
   the Characters tab approved her 28. Read it again every time the tab is
   shown, and when the browser tab comes back; her selection and ticks stay. */
SM.on('shown',()=>load());
document.addEventListener('visibilitychange',()=>{ if(document.visibilityState==='visible') load(); });

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
