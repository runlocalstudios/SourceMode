"""The Characters tab: everything that defines a character, one page each.

    GET  /characters                   the page (/appearance serves it too)
    GET  /appearance/list              every character, unconfirmed first
    GET  /appearance/ref?char=&name=   one reference photo (web-sized)
    POST /appearance/<char>/confirm    {prompt, negative} -> confirmed record
    POST /characters/<char>/profile    {ethnicity, wardrobe} -> saved

Was the Looks tab. Jeremy, 2026-10-06, after Bri's invented "lighter caramel
ends" and Jaina's freckles: "I need to now review all of these because they're
so fucked up that I can't trust them." Each card puts her reference photos
beside the exact text every render of her carries, with race words marked (his
rule: no race in any prompt). Confirm writes his text and binds it to a
fingerprint; check() - the pre-flight the sweep and the shoots already run -
refuses anything unconfirmed.

2026-10-11 it became Characters: her locked LoRA, what has been rendered of
her, the context the game's writing uses (age, ethnicity - never prompted),
two jobs tied to the game places she works them, free-form style per outfit
type, and her hair options. "Marisol and Zara are both strippers and both work
at the beach bar, I can't have them working at the beach bar in stripper
outfits."
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .ui import page

REFS = Path("C:/Epic Games/Files/cnc info/codex/references")
GAME_ASSETS = Path("C:/dev/chillafterdark/src/assets/characters")
EXT = (".png", ".jpg", ".jpeg", ".webp")
#: Words that name a race or ethnicity. Highlighted, never auto-removed - he edits.
RACE = re.compile(r"\b(?:white|black|latina|latino|hispanic|asian|half-asian|east asian|"
                  r"southeast asian|south asian|indian|filipina|korean|japanese|chinese|"
                  r"vietnamese|thai|irish|italian|italian-american|mediterranean|caucasian|"
                  r"african|middle eastern|arab|persian|mixed|biracial)\b", re.I)
# The Fit dropdown is gone - Jeremy, 2026-10-10: "It's too confusing ... I
# already have the description in there for pretty much every character."


def _refs(char: str) -> list[str]:
    if not REFS.is_dir():
        return []
    return [p.name for p in sorted(REFS.iterdir())
            if p.suffix.lower() in EXT and p.stem.split("_")[0].lower() == char]


def _lock(char: str, judge_root: Path | None) -> dict | None:
    from ..train.locked import load_registry  # noqa: PLC0415

    row = load_registry().get(char)
    if not row:
        return None
    # the basis names the set it was judged on, wherever in the line it sits
    # ("epoch-choices: dense_zara_v2_asset 9/10 at ep18")
    sweep = next((m for m in re.findall(r"((?:dense|shoot|ab)_[a-z0-9_]+)", row.get("basis") or "")
                  if judge_root and (judge_root / "sets" / f"{m}.json").is_file()), None)
    return {"file": row.get("file"), "epoch": row.get("epoch"), "basis": row.get("basis", ""),
            "at": row.get("locked_at"), "sweep": sweep}


def _packs(char: str, outputs: Path | None, judge_root: Path | None) -> dict:
    """What exists of her: outfits the game ships, shoots rendered here, and
    whether an asset-pack plan has been written."""
    od = GAME_ASSETS / char / "outfits"
    shipped = sum(1 for p in od.iterdir() if p.suffix.lower() in EXT) if od.is_dir() else 0
    shoots = []
    if judge_root and (judge_root / "sets").is_dir():
        for sp in sorted((judge_root / "sets").glob(f"shoot_{char}_*.json")):
            vp = judge_root / "verdicts" / sp.name
            try:
                n = len(json.loads(sp.read_text(encoding="utf-8")).get("items") or [])
                v = json.loads(vp.read_text(encoding="utf-8")) if vp.is_file() else {}
            except (OSError, ValueError):
                continue
            shoots.append({"set": sp.stem, "name": sp.stem[len(f"shoot_{char}_"):],
                           "n": n, "judged": len(v),
                           "kept": sum(1 for x in v.values() if x == "keep")})
    plan = bool(outputs and (outputs / "game-assets" / char / "plan_28.json").is_file())
    return {"shipped": shipped, "shoots": shoots, "plan": plan}


def records(outputs: Path | None = None, judge_root: Path | None = None) -> list[dict]:
    from ..assets import appearance as A  # noqa: PLC0415
    from ..assets import wardrobe as W  # noqa: PLC0415

    A.reload()
    look = A._load()["look"]
    places_named = A.location_names()
    out = []
    # every record we have, plus every key character the game has that we do
    # not: she appears with empty fields, and confirming her writes the record
    names = {c for c in look if not c.startswith("_")} | set(A.key_characters())
    for c in sorted(names):
        rec = look.get(c) or {}
        g = A.game_facts(c)
        sched = g.get("schedule") or []
        places, seen = [], set()
        for loc, outfit in sched:
            if loc in seen:
                continue
            seen.add(loc)
            places.append({"id": loc, "name": places_named.get(loc, loc),
                           "work": any(o == "work" for lc, o in sched if lc == loc)})
        out.append({
            "character": c, "age": A.age_of(c),
            "prompt": rec.get("prompt", ""),
            "negative": rec.get("negative", ""),
            "note": rec.get("_note", ""), "confirmed": A.confirmed(c),
            "confirmed_at": (rec.get("confirmed") or {}).get("at"),
            "race": sorted({m.group(0) for m in RACE.finditer(rec.get("prompt", ""))}),
            "game": g.get("opening", ""), "refs": _refs(c),
            "ethnicity": rec.get("ethnicity", ""),
            "game_job": A.persona_job(c),
            "places": places,
            "lock": _lock(c, judge_root),
            "packs": _packs(c, outputs, judge_root),
            "wardrobe": W.editable(c),
            "hair_default": list(W.DEFAULT_HAIR if not W.is_short_haired(c) else W.SHORT_HAIR),
        })
    out.sort(key=lambda r: (r["confirmed"], r["character"]))
    return out


def outfit_types() -> list[dict]:
    from ..assets.wardrobe import OUTFIT_TYPES  # noqa: PLC0415

    return [{"key": k, "label": lab, "covers": cov} for k, lab, cov in OUTFIT_TYPES]


OWN_CSS = r"""
html,body{overflow-x:hidden}
/* one column: the shared .wrap reserves a rail this page does not have */
#app{display:block;max-width:760px;margin:0 auto;padding:0 var(--s3);box-sizing:border-box}
#app,.col-main{min-width:0;width:100%;overflow-x:hidden}
.top{display:flex;gap:var(--s2);align-items:center;margin-bottom:var(--s2)}
.top h2{flex:1;margin:0}
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
.lk textarea.short{min-height:0;padding:var(--s2) var(--s3);line-height:1.35}
.lk .hl{padding:var(--s2) var(--s3);background:var(--g0);border:1px dashed var(--g4);
  border-radius:var(--r2);font:var(--t-meta);color:var(--g7);margin-top:var(--s2)}
.lk .hl mark{background:var(--stop-bg);color:var(--stop-ink);border-radius:3px;padding:0 2px}
.lk .row{display:flex;gap:var(--s2);align-items:center;flex-wrap:wrap;margin-top:var(--s2)}
.lk input[type=text],.lk input:not([type]){min-height:var(--tap);background:var(--g1);color:var(--g9);
  border:1px solid var(--g4);border-radius:var(--r2);padding:0 var(--s2);font-size:16px;
  flex:1;min-width:0;width:100%;box-sizing:border-box}
.lk .note{font:var(--t-small);color:var(--g6);margin-top:var(--s2)}
.lk details summary{cursor:pointer}
.sec{margin-top:var(--s3);padding-top:var(--s2);border-top:1px solid var(--g3)}
.sec h4{margin:0 0 var(--s1);font:var(--t-meta);font-weight:600;color:var(--g8);
  text-transform:uppercase;letter-spacing:.04em}
.sec .sub{font:var(--t-small);color:var(--g6);margin-bottom:var(--s1)}
.fld{margin-top:var(--s2)}
.fld label{display:block;font:var(--t-meta);font-weight:600;color:var(--g8);margin-bottom:2px}
.fld .cov{font:var(--t-small);font-weight:400;color:var(--g6)}
.sec h4 .draft{text-transform:none;letter-spacing:0;font-weight:400;margin-left:var(--s2)}
.facts{display:grid;grid-template-columns:auto 1fr;gap:var(--s1) var(--s3);font:var(--t-meta);color:var(--g8)}
.facts dt{color:var(--g6)}
.facts dd{margin:0;min-width:0;overflow-wrap:anywhere}
.job{margin-top:var(--s2)}
.job .row{margin-top:var(--s1)}
.facts .w{color:var(--g6);font:var(--t-small)}
.linkish{background:none;border:0;padding:0;color:var(--act);font:inherit;cursor:pointer;
  text-decoration:underline;text-underline-offset:3px}
.draft{font:var(--t-small);color:var(--you-ink)}
.sec h5{margin:var(--s3) 0 0;font:var(--t-meta);font-weight:600;color:var(--g8)}
.look{display:grid;grid-template-columns:auto 1fr;gap:var(--s1) var(--s2);align-items:start;margin-top:var(--s2)}
.look .lid{font:var(--t-small);color:var(--g6);padding-top:9px;font-variant-numeric:tabular-nums}
.look input{grid-column:2}
.lk .row .note{margin:0}
#big{position:fixed;inset:0;z-index:60;background:rgba(0,0,0,.92);display:none;
  align-items:center;justify-content:center}
#big.on{display:flex}
#big img{max-width:96vw;max-height:94vh}
"""

BODY = """
<div class=wrap id=app>
  <div class=col-main>
    <div class=top><h2>Characters</h2>
      <button class="btn btn-sm" data-act=newchar>New character &rarr;</button></div>
    <select id=who aria-label="character"></select>
    <div class=card-sub id=sum>loading&hellip;</div>
    <div id=list></div>
  </div>
</div>
<div id=big><img alt=""></div>
"""

OWN_JS = r"""
const $=id=>document.getElementById(id);
let recs=[], types=[];
const refUrl=(c,n)=>'/appearance/ref?char='+encodeURIComponent(c)+'&name='+encodeURIComponent(n);
const RACE=/\b(white|black|latina|latino|hispanic|asian|half-asian|east asian|southeast asian|south asian|indian|filipina|korean|japanese|chinese|vietnamese|thai|irish|italian|italian-american|mediterranean|caucasian|african|middle eastern|arab|persian|mixed|biracial)\b/gi;

async function load(){
  try{ [recs,types]=await Promise.all([SM.getJSON('/appearance/list'),SM.getJSON('/characters/outfit-types')]); }
  catch(e){ $('list').innerHTML='<div class=errbox><b>Could not load</b> '+SM.esc(e.message)+'</div>'; return; }
  draw();
}
function marked(t){ return SM.esc(t).replace(RACE,m=>'<mark>'+m+'</mark>'); }
/* Jeremy, 2026-10-07: "I want to be able to revisit any of the girls' looks
   from a drop down even if they are already approved". The page opens on what
   still needs review; the dropdown reaches anyone. Kept in the hash so a
   reload, a Confirm or a Save stays on the same character. */
let pick=decodeURIComponent(location.hash.slice(1))||'';
window.addEventListener('hashchange',()=>{ pick=decodeURIComponent(location.hash.slice(1))||''; draw(); });
function drawPicker(){
  const open=recs.filter(r=>!r.confirmed);
  const opt=(v,t)=>'<option value="'+SM.esc(v)+'"'+(v===pick?' selected':'')+'>'+SM.esc(t)+'</option>';
  $('who').innerHTML=opt('','Needs review ('+open.length+')')
    +recs.slice().sort((a,b)=>a.character.localeCompare(b.character))
      .map(r=>opt(r.character,r.character+(r.confirmed?'  ✓':'  • needs review'))).join('');
}
$('who').addEventListener('change',e=>{
  pick=e.target.value; history.replaceState(null,'','#'+encodeURIComponent(pick)); draw();
  window.scrollTo(0,0);
});
function shown(){
  if(pick) return recs.filter(r=>r.character===pick);
  const open=recs.filter(r=>!r.confirmed);
  return open.length?open:[];
}
const ta=(k,v,cls,ph)=>'<textarea rows=1 data-k="'+k+'"'+(cls?' class='+cls:'')+' spellcheck=true'
  +(ph?' placeholder="'+SM.esc(ph)+'"':'')+'>'+SM.esc(v||'')+'</textarea>';

function appearance(r){
  return (r.refs.length?'<div class=refs>'+r.refs.map(n=>'<img loading=lazy src="'+refUrl(r.character,n)+'" alt="'+SM.esc(n)+'">').join('')+'</div>'
                       :'<div class=card-sub>No reference photos.</div>')
    +(r.game?'<div class=game>Game: '+SM.esc(r.game)+'</div>':'')
    +'<h4 class=sr-only>Description</h4>'
    +'<textarea data-k=prompt spellcheck=false>'+SM.esc(r.prompt)+'</textarea>'
    +'<div class=hl data-hl>'+(r.race.length?marked(r.prompt):'No race words.')+'</div>'
    +'<div class=row><label>Negative</label><input data-k=negative placeholder="negative (optional)" value="'+SM.esc(r.negative||'')+'"></div>'
    +'<div class=row><button class="btn btn-primary" data-act=confirm>'+(r.confirmed?'Save &amp; re-confirm':'Confirm')+'</button></div>';
}

function lockLine(r){
  const l=r.lock;
  if(!l) return '<dt>LoRA</dt><dd>not locked</dd>';
  const d=l.at?new Date(l.at):null;
  const when=d?(d.getMonth()+1)+'/'+d.getDate()+'/'+String(d.getFullYear()).slice(2):'';
  return '<dt>LoRA</dt><dd>'+SM.esc(l.file)+' (epoch '+SM.esc(String(l.epoch))+')'
    +(when?' - locked '+when:'')
    +(l.sweep?' &middot; <button class=linkish data-act=sweep data-set="'+SM.esc(l.sweep)+'">sweep</button>':'')
    +'</dd>';
}
function packLine(r){
  const p=r.packs, bits=[];
  bits.push(p.shipped?(p.shipped+' outfits in the game'):'no outfits in the game');
  if(p.plan) bits.push('asset-pack plan written');
  const shoots=p.shoots.length
    ? p.shoots.map(s=>SM.esc(s.name.replace(/_/g,' '))+' '+(s.judged?s.kept+'/'+s.judged:'unjudged')).join(', ')
    : 'none yet';
  return '<dt>Packs</dt><dd>'+SM.esc(bits.join(' · '))+'</dd><dt>Shoots</dt><dd>'+shoots+'</dd>';
}

function profile(r){
  const w=r.wardrobe;
  const job=(j,i)=>'<div class="fld job" data-job="'+i+'">'
    +'<label>Job '+(i+1)+'</label>'
    +'<input data-j=job value="'+SM.esc(j.job)+'" placeholder="the job, e.g. server at The Sandbar">'
    +'<div class=row>'+ta('j_outfit',j.outfit,'short','what she wears for it')+'</div>'
    +'</div>';
  return '<div class=sec><h4>Context</h4><div class=sub>For the game&rsquo;s writing; never put in a prompt.</div>'
    +'<dl class=facts><dt>Age</dt><dd>'+(r.age?SM.esc(String(r.age))+' <span class=w>(the game&rsquo;s)</span>':'&mdash;')+'</dd>'
    +lockLine(r)+packLine(r)+'</dl>'
    +'<div class=fld><label>Ethnicity</label><input data-k=ethnicity value="'+SM.esc(r.ethnicity||'')+'"></div></div>'
    +'<div class=sec><h4>Jobs</h4>'
    +(r.game_job?'<div class=sub>The game says: '+SM.esc(r.game_job)+'</div>':'')
    +w.jobs.map(job).join('')+'</div>'
    +'<div class=sec><h4>Style'+(w.draft?'<span class=draft>draft - not yet saved by you</span>':'')+'</h4>'
    +'<div class=fld><label>Overall</label>'+ta('style',w.style,'short','chic, trendy, shabby, overdressed, revealing, conservative...')+'</div>'
    +'<div class=fld><label>Palette</label>'+ta('palette',w.palette,'short','the colours she actually wears')+'</div>'
    +'<div class=fld><label>Never wears</label>'+ta('avoid',w.avoid,'short','the line she does not cross, in any outfit')+'</div>'
    +types.map(t=>'<div class=fld><label>'+SM.esc(t.label)+' <span class=cov>- '+SM.esc(t.covers)+'</span></label>'
      +ta('o_'+t.key,w.outfits[t.key],'short')+'</div>').join('')
    +'</div>'
    +'<div class=sec><h4>Hair options</h4><div class=sub>One per line. Starts as the shared list; edit, add or delete lines.</div>'
    +ta('hair',(w.hair.length?w.hair:r.hair_default).join('\n'),'short')+'</div>'
    +'<div class=row><button class="btn btn-primary" data-act=save>Save '+SM.esc(r.character)+'</button></div>'
    +'<div class="sec looks" data-looks="'+SM.esc(r.character)+'"><h4>Wardrobe pack &mdash; 28 looks</h4>'
    +'<div class=sub>loading&hellip;</div></div>';
}

/* --- the 28-look plan ----------------------------------------------------
   Jeremy, 2026-10-12: the pack box on Shoots said "decide the 28 outfits" and
   gave him nowhere to do it. Draft from her record, edit every line, approve;
   the approved plan is what the Shoots tab renders. */
async function loadLooks(){
  for(const el of document.querySelectorAll('[data-looks]')){
    const c=el.dataset.looks;
    try{ drawLooks(el, await SM.getJSON('/characters/'+encodeURIComponent(c)+'/looks')); }
    catch(e){ el.querySelector('.sub').textContent='Could not load: '+e.message; }
  }
}
function drawLooks(el,st){
  const c=st.character;
  let h='<h4>Wardrobe pack &mdash; 28 looks'
    +(st.state==='approved'?'<span class=draft style="color:var(--done-ink)">approved '+SM.esc(SM.ago(st.approved_at))+'</span>'
     :st.state==='draft'?'<span class=draft>draft - edit, then approve</span>':'')+'</h4>';
  if(st.state==='none'){
    const n=Object.values(st.shipped||{}).reduce((a,b)=>a+b,0);
    h+='<div class=sub>Nothing drafted yet. The asset pack on the Shoots tab stays locked until 28 looks are approved.'
      +(n?' She has '+n+' outfits in the game already, so the new looks number on from there.':'')+'</div>'
      +'<div class=row><button class="btn btn-primary" data-act=lk_draft>Draft the 28 looks</button></div>';
    el.innerHTML=h; return;
  }
  h+='<div class=sub>One outfit and one hair per look. The draft is garments in her palette, and five days at her job built from her job line - edit anything. Hair words: colour, dye and length only.</div>';
  for(const cat of st.categories){
    h+='<h5>'+SM.esc(cat.label)+' <span class=cov>'+cat.looks.length+(cat.guide?' &middot; her record: '+SM.esc(cat.guide):'')+'</span></h5>';
    for(const l of cat.looks){
      h+='<div class=look><span class=lid>'+SM.esc(l.id)+'</span>'
        +'<textarea rows=1 class=short data-lo="'+SM.esc(l.id)+'" placeholder="the outfit">'+SM.esc(l.outfit)+'</textarea>'
        +'<input data-lh="'+SM.esc(l.id)+'" value="'+SM.esc(l.hair)+'" placeholder="her hair ...">'
        +'</div>';
    }
  }
  h+='<div class=row><button class="btn btn-primary" data-act=lk_save>Save</button>'
    +(st.state==='draft'
      ?'<button class="btn" data-act=lk_approve'+(st.blank?' disabled title="'+st.blank+' blank"':'')+'>Approve &mdash; unlocks the pack on Shoots</button>'
       +'<button class="btn btn-ghost" data-act=lk_draft>Start over</button>'
      :'')
    +(st.blank?'<span class=note>'+st.blank+' blank</span>':'')+'</div>';
  el.innerHTML=h;
  for(const t of el.querySelectorAll('textarea')) fit(t);
}
function collectLooks(el){
  return {all:[...el.querySelectorAll('[data-lo]')].map(t=>({id:t.dataset.lo,outfit:t.value,
    hair:(el.querySelector('[data-lh="'+CSS.escape(t.dataset.lo)+'"]')||{}).value||''}))};
}
async function looksAct(b){
  const el=b.closest('[data-looks]'), c=el.dataset.looks, a=b.dataset.act;
  const u='/characters/'+encodeURIComponent(c)+'/looks';
  if(a==='lk_draft' && el.querySelector('[data-lo]') && !confirm('Replace every line with a fresh draft?')) return;
  b.disabled=true;
  try{
    let st;
    if(a==='lk_draft') st=await SM.postJSON(u+'/draft',{});
    else if(a==='lk_save'){ st=await SM.postJSON(u,{categories:collectLooks(el)}); SM.toast('looks saved'); }
    else if(a==='lk_approve'){
      st=await SM.postJSON(u,{categories:collectLooks(el)});   /* save what is on screen first */
      st=await SM.postJSON(u+'/approve',{});
      SM.toast(c+': 28 looks approved - the pack is open on Shoots',{label:'Shoots',run:()=>SM.nav('shoots',c)});
    }
    drawLooks(el,st);
  }catch(err){ SM.toast(err.message); b.disabled=false; }
}

function draw(){
  drawPicker();
  const open=recs.filter(r=>!r.confirmed).length;
  $('sum').textContent=pick?'':(open?(open+' of '+recs.length+' descriptions still to confirm. A sweep or shoot will not render a character until hers is confirmed. Pick anyone from the list.')
                            :('All '+recs.length+' descriptions confirmed. Pick a character from the list.'));
  const one=!!pick;
  SM.set($('list'),null,shown().map(r=>
    '<div class="card lk '+(r.confirmed?'e-done':'e-you')+'" data-c="'+SM.esc(r.character)+'">'
      +'<div class=card-head>'+SM.pill(r.confirmed?'done':'you')
      +'<h3>'+SM.esc(r.character)+'</h3>'
      +(r.confirmed?'<span class=age>confirmed '+SM.esc(SM.ago(r.confirmed_at))+'</span>':'')+'</div>'
      +appearance(r)+(one?profile(r):'')
    +'</div>').join(''));
  for(const t of document.querySelectorAll('.lk textarea')) fit(t);
  loadLooks();
}
/* the whole text visible at once - no inner scrolling to read what she is */
function fit(t){ t.style.height='auto'; t.style.height=(t.scrollHeight+2)+'px'; }
document.addEventListener('input',e=>{
  if(e.target.tagName==='TEXTAREA') fit(e.target);
  if(e.target.dataset.k!=='prompt') return;
  const card=e.target.closest('.lk'), t=e.target.value, hl=card.querySelector('[data-hl]');
  hl.innerHTML=RACE.test(t)?marked(t):'No race words.'; RACE.lastIndex=0;
});
function collect(card){
  const v=k=>{ const el=card.querySelector('[data-k="'+k+'"]'); return el?el.value:''; };
  const outfits={}; for(const t of types) outfits[t.key]=v('o_'+t.key);
  const rec=recs.find(r=>r.character===card.dataset.c)||{wardrobe:{jobs:[]},hair_default:[]};
  const jobs=[...card.querySelectorAll('[data-job]')].map((j,i)=>({
    job:j.querySelector('[data-j=job]').value,
    outfit:j.querySelector('[data-k=j_outfit]').value,
    places:((rec.wardrobe.jobs[i]||{}).places)||[]}));
  /* unchanged from the shared list = no list of her own, so a later change
     to the shared list still reaches her */
  const hair=v('hair').split('\n').map(x=>x.trim()).filter(Boolean);
  const same=hair.join('\n')===rec.hair_default.join('\n');
  return {ethnicity:v('ethnicity'),
          wardrobe:{style:v('style'),palette:v('palette'),avoid:v('avoid'),outfits,jobs,
                    hair:same?[]:hair}};
}
document.addEventListener('click',async e=>{
  const img=e.target.closest('.refs img');
  if(img){ $('big').querySelector('img').src=img.src; $('big').classList.add('on'); return; }
  if(e.target.closest('#big')){ $('big').classList.remove('on'); return; }
  const b=e.target.closest('[data-act]'); if(!b) return;
  if(b.dataset.act==='newchar'){ location.href='/character'; return; }
  if(b.dataset.act==='sweep'){ SM.nav('judge',b.dataset.set); return; }
  if(b.dataset.act.startsWith('lk_')) return looksAct(b);
  const card=b.closest('.lk'); if(!card) return;
  const c=card.dataset.c, val=k=>card.querySelector('[data-k='+k+']').value;
  b.disabled=true;
  try{
    if(b.dataset.act==='confirm'){
      await SM.postJSON('/appearance/'+encodeURIComponent(c)+'/confirm',
        {prompt:val('prompt'),negative:val('negative')});
      SM.toast(c+' confirmed');
    }else if(b.dataset.act==='save'){
      await SM.postJSON('/characters/'+encodeURIComponent(c)+'/profile',collect(card));
      SM.toast(c+' saved');
    }
    const y=window.scrollY; await load(); window.scrollTo(0,y);
  }catch(err){ SM.toast(err.message); b.disabled=false; }
});
load();
"""

PAGE = page("Characters", BODY, OWN_JS, OWN_CSS)


def appearance_router(cfg: dict):
    from fastapi import APIRouter, Body, HTTPException  # noqa: PLC0415
    from fastapi.responses import FileResponse, HTMLResponse  # noqa: PLC0415

    from ..assets.judge import judge_root  # noqa: PLC0415
    from ..config import outputs_dir  # noqa: PLC0415

    r = APIRouter()

    @r.get("/characters", response_class=HTMLResponse)
    @r.get("/appearance", response_class=HTMLResponse)
    def _page():
        return HTMLResponse(PAGE, headers={"Cache-Control": "no-store"})

    @r.get("/appearance/list")
    def _list() -> list[dict]:
        return records(outputs_dir(cfg), judge_root(cfg))

    @r.get("/characters/outfit-types")
    def _types() -> list[dict]:
        return outfit_types()

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
            rec = A.confirm(char, {k: body.get(k, "") for k in A.CONFIRM_FIELDS})
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"character": char.lower(), "confirmed": rec["confirmed"]}

    # --- the 28-look wardrobe plan -------------------------------------------
    # Jeremy, 2026-10-12: the asset pack was greyed out for Ash with nowhere on
    # the monitor to do what it asked. Draft here, edit, approve; approving is
    # what unlocks the pack on the Shoots tab.
    def _char(char: str) -> str:
        c = (char or "").strip().lower()
        if not re.match(r"^[a-z][a-z0-9_]{0,31}$", c):
            raise HTTPException(400, "a character id is required")
        return c

    @r.get("/characters/{char}/looks")
    def _looks(char: str) -> dict:
        from ..assets import looks as L  # noqa: PLC0415

        return L.state(cfg, _char(char))

    @r.post("/characters/{char}/looks/draft")
    def _looks_draft(char: str) -> dict:
        from ..assets import looks as L  # noqa: PLC0415

        return L.draft(cfg, _char(char))

    @r.post("/characters/{char}/looks")
    def _looks_save(char: str, body: dict = Body(...)) -> dict:
        from ..assets import looks as L  # noqa: PLC0415

        try:
            return L.save(cfg, _char(char), body.get("categories") or {})
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @r.post("/characters/{char}/looks/approve")
    def _looks_approve(char: str) -> dict:
        from ..assets import looks as L  # noqa: PLC0415

        try:
            return L.approve(cfg, _char(char))
        except ValueError as e:
            raise HTTPException(409, str(e)) from e

    @r.post("/characters/{char}/profile")
    def _profile(char: str, body: dict = Body(...)) -> dict:
        from ..assets import appearance as A  # noqa: PLC0415
        from ..assets import wardrobe as W  # noqa: PLC0415

        c = char.lower()
        try:
            rec = W.save(c, body.get("wardrobe") or {})
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if "ethnicity" in body:
            A.set_context(c, ethnicity=str(body.get("ethnicity") or ""))
        return {"character": c, "wardrobe": rec}

    return r
