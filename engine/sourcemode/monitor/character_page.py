"""The new-character form: everything asset generation needs, asked once.

    GET  /character            the form
    GET  /character/fields     the field list, so the page never hardcodes it
    POST /character/preview    the composed clause + what is still thin
    POST /character/create     writes appearance.json + wardrobe.json
"""

from __future__ import annotations

from .ui import page

OWN_CSS = r"""
.f{margin-bottom:var(--s4)}
.f label{display:block;font:var(--t-meta);color:var(--g8);font-weight:600;
  margin-bottom:var(--s1)}
.f .hint{display:block;font:var(--t-small);color:var(--g6);margin-bottom:var(--s2)}
.f input,.f textarea{width:100%;box-sizing:border-box;min-height:var(--tap);
  padding:var(--s2) var(--s3);background:var(--g1);border:1px solid var(--g4);
  border-radius:var(--r2);color:var(--g9);font:var(--t-body)}
.f textarea{min-height:68px;resize:vertical}
.f input:focus,.f textarea:focus{outline:none;border-color:var(--act)}
.f.need label::after{content:' *';color:var(--you-ink)}
.f.bad input,.f.bad textarea{border-color:var(--stop-line)}
.clause{padding:var(--s3);background:var(--g1);border:1px solid var(--g3);
  border-left:3px solid var(--act);border-radius:var(--r2);
  font:var(--t-meta);color:var(--g8);white-space:pre-wrap;word-break:break-word}
pre.snip{margin:0;padding:var(--s3);background:var(--g0);border:1px solid var(--g3);
  border-radius:var(--r2);color:var(--g8);font-size:12px;line-height:1.5;
  overflow-x:auto;white-space:pre}
"""

BODY = """
<div class=wrap id=app>
  <div class=col-main>
    <h2>New character</h2>
    <div id=form></div>
  </div>
  <div class=col-rail><div id=rail></div></div>
</div>
<div id=bars></div>
"""

OWN_JS = r"""
const $=id=>document.getElementById(id);
let fields=[], val={};

async function load(){
  try{ fields=await SM.getJSON('/character/fields'); }
  catch(e){ $('form').innerHTML='<div class=errbox><b>Could not load</b>'
    +SM.esc(e.message)+'</div>'; return; }
  draw(); preview();
}

function draw(){
  SM.set($('form'),null, fields.map(f=>
    '<div class="f'+(f.kind==='need'?' need':'')+'" data-f="'+SM.esc(f.key)+'">'
    +'<label for="i_'+SM.esc(f.key)+'">'+SM.esc(f.label)+'</label>'
    +'<span class=hint>'+SM.esc(f.hint)+'</span>'
    +(f.long?'<textarea id="i_'+SM.esc(f.key)+'" data-k="'+SM.esc(f.key)+'"></textarea>'
            :'<input id="i_'+SM.esc(f.key)+'" data-k="'+SM.esc(f.key)+'" '
             +'autocapitalize=none autocorrect=off>')
    +'</div>').join(''));
}

let timer=null;
document.addEventListener('input',e=>{
  const k=e.target.dataset.k; if(!k) return;
  val[k]=e.target.value;
  clearTimeout(timer); timer=setTimeout(preview,250);
});

async function preview(){
  let d; try{ d=await SM.postJSON('/character/preview',val); }catch(e){ return; }
  for(const f of fields){
    const el=document.querySelector('.f[data-f="'+CSS.escape(f.key)+'"]');
    if(el) el.classList.toggle('bad', d.missing_keys.includes(f.key));
  }
  SM.set($('rail'),null,
    '<div class=card><div class=card-head><h3>Her clause</h3></div>'
    +'<div class=card-sub>Every render she is ever in carries this sentence.</div>'
    +'<div class=clause>'+(d.clause?SM.esc(d.clause):'&mdash;')+'</div></div>'
    +(d.missing.length
      ? '<div class="banner stop"><span class=msg><b>Not enough to render her.</b>'
        +'<span class=why>'+SM.esc(d.missing.join(', '))+'</span></span></div>' : '')
    +(d.thin.length
      ? '<div class="banner you"><span class=msg><b>Thin, but not blocking.</b>'
        +'<span class=why>'+d.thin.map(t=>SM.esc(t)).join('<br>')+'</span></span></div>'
      : '')
    +(d.conflicts&&d.conflicts.length
      ? '<div class="banner you"><span class=msg><b>The game already says otherwise.</b>'
        +'<span class=why>'+d.conflicts.map(t=>SM.esc(t)).join('<br>')+'</span></span></div>'
      : ''));
  SM.set($('bars'),null,'<div class=actbar>'
    +'<button class="btn btn-primary" data-act=create'+(d.missing.length?' disabled':'')
    +'>Create '+SM.esc(val.name||val.character||'character')+'</button></div>');
}

document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-act]'); if(!b) return;
  if(b.dataset.act!=='create') return;
  b.disabled=true;
  let d; try{ d=await SM.postJSON('/character/create',val); }
  catch(err){ SM.toast(err.message); b.disabled=false; return; }
  SM.set($('form'),null,
    '<div class=empty><b>'+SM.esc(d.character)+' is on record</b>'
    +'Written to '+SM.esc(d.written.join(' and '))+'.'
    +' She appears on the shoots tab as soon as she has an approved LoRA.</div>'
    +'<h2>For chillafterdark</h2>'
    +'<div class=card-sub>Nothing is written into the game repo from here &mdash;'
    +' paste this yourself.</div>'
    +'<pre class=snip>'+SM.esc(d.snippet)+'</pre>');
  SM.set($('bars'),null,'<div class=actbar>'
    +'<button class="btn" data-act=copy>Copy the snippet</button>'
    +'<button class="btn btn-ghost" onclick="location.reload()">Add another</button>'
    +'</div>');
  window.__snip=d.snippet;
});

document.addEventListener('click',e=>{
  if(!e.target.closest('[data-act=copy]')) return;
  try{ navigator.clipboard.writeText(window.__snip||''); SM.toast('copied'); }
  catch(err){ SM.toast('select it and copy by hand'); }
});

load();
"""

PAGE = page("new character", BODY, OWN_JS, OWN_CSS)

#: Fields rendered as a textarea rather than a single line.
LONG = {"features", "negative", "style", "palette", "avoid", "job"}


def character_router(cfg: dict):
    from fastapi import APIRouter, Body, HTTPException  # noqa: PLC0415
    from fastapi.responses import HTMLResponse  # noqa: PLC0415

    from ..assets.character_new import (  # noqa: PLC0415
        FIELDS, appearance_clause, create, missing, thin)

    r = APIRouter()

    def _chars_dir():
        from ..config import ENGINE_ROOT  # noqa: PLC0415

        return (ENGINE_ROOT.parent / "characters")

    @r.get("/character", response_class=HTMLResponse)
    def _page():
        return PAGE

    @r.get("/character/fields")
    def _fields() -> list[dict]:
        return [{"key": k, "label": lab, "kind": kind, "hint": hint,
                 "long": k in LONG} for k, lab, kind, hint in FIELDS]

    @r.post("/character/preview")
    def _preview(body: dict = Body(default={})) -> dict:
        gaps = missing(body)
        labels = {k: lab for k, lab, _, _ in FIELDS}
        # The game is authoritative on age and on anything its writing asserts,
        # so a clash is surfaced while he is still typing rather than after the
        # record is written and a sweep has already used it.
        conflicts = []
        cid = str(body.get("character", "")).strip().lower()
        if cid:
            from ..assets.appearance import game_facts  # noqa: PLC0415

            g = game_facts(cid)
            if g.get("found"):
                if body.get("age") and g.get("age") and str(body["age"]) != str(g["age"]):
                    conflicts.append(f"age: you typed {body['age']}, the game says "
                                     f"{g['age']} - the game wins")
                for e in g.get("ethnicity") or []:
                    if e.lower() not in str(body.get("ethnicity", "")).lower():
                        conflicts.append(f"the game calls her {e}")
        try:
            clause = appearance_clause(body) if not gaps else ""
        except (KeyError, ValueError):
            clause = ""
        return {"clause": clause, "missing": gaps, "thin": thin(body),
                "conflicts": conflicts,
                "missing_keys": [k for k, lab, kind, _ in FIELDS
                                 if kind == "need" and labels[k] in gaps]}

    @r.post("/character/create")
    def _create(body: dict = Body(default={})) -> dict:
        from datetime import datetime, timezone  # noqa: PLC0415

        payload = {**body, "created": datetime.now(timezone.utc).date().isoformat()}
        try:
            return create(payload, characters_dir=_chars_dir())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    return r
