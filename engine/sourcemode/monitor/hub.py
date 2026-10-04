"""One bookmarkable page with tabs for the things Jeremy actually does on a phone.

The GPU tab opens first, deliberately: the question on walking up to the box is
"what is it doing and what is next", and judging is something he chooses to do.

`/judge` and `/dataset` are each self-contained pages with their own scripts and
their own use of `location.hash`, so merging them into one document would collide
on both. The hub embeds each in its own frame instead: nothing in either page
changes, they still work standalone, and each frame keeps its own hash.

Both frames stay loaded once visited, so switching tabs does not lose your place
in a 140-image judge set. A later visit to an already-loaded frame moves its hash
rather than reloading the document, which is what preserves that scroll position.

What the shell adds beyond the tab strip:

- **The card's state is readable from every tab.** A bottom bar outside the
  frames carries the status pill, one sentence and a progress hairline. The
  dominant use is a phone glance, and until now a glance at the Judging tab said
  nothing about the card.
- **The browser chrome carries the worst state in the house.** `theme-color` is
  rewritten from the severity each poll, so iOS tints the top of Safari, and
  `document.title` is prefixed so the app switcher carries it too.
- **Hidden frames stop polling.** `{t:'hidden'}` stops that frame's timer;
  `{t:'shown'}` fires one immediate load. Three frames used to poll forever,
  including the two you were not looking at.
- **`chrome:'immersive'`** lets the judge page ask for the screen: the bar is
  hidden entirely and the tab strip collapses to a 20px grab strip, rather than
  a 100vh stage being compressed by 56px.

The frame protocol is versioned. `sm:1` means a phone holding a frame cached
across a monitor restart posts or receives a shape the other side ignores
instead of throwing.

    GET  /            the hub
    GET  /hub/now     one sentence, the severity, the three badge counts
    GET  /hub/counts  {gpu, judge, datasets} - kept as an alias for one release
                      so a phone holding the old cached page keeps working
"""

from __future__ import annotations

from .ui import page

OWN_CSS = r"""
html,body{height:100%;margin:0;padding:0;overflow:hidden}
body{display:flex;flex-direction:column;background:var(--g0)}
#tabs{display:flex;flex:none;background:var(--g1);border-bottom:1px solid var(--g3);
  padding-top:var(--safe-t);transition:transform var(--m-base) var(--ease)}
#tabs button{flex:1;min-height:var(--tap);padding:var(--s2) var(--s1);background:none;
  border:0;border-bottom:2px solid transparent;color:var(--g7);
  font:var(--t-body);font-weight:600;cursor:pointer;display:flex;
  align-items:center;justify-content:center;gap:var(--s2);
  -webkit-tap-highlight-color:transparent}
#tabs button.on{color:var(--g9);border-bottom-color:var(--act);background:var(--g2)}
#tabs .n{min-width:22px;padding:1px 6px;border-radius:var(--rp);font:var(--t-small);
  font-weight:700;background:var(--g4);color:var(--g8);visibility:hidden}
#tabs .n.show{visibility:visible}
#tabs .n.you{background:var(--you);color:var(--on-you)}
#tabs .n.stop{background:var(--stop);color:var(--on-stop)}
.pane{flex:1;border:0;width:100%;display:none;background:var(--g0)}
.pane.on{display:block}
#nowwrap{position:relative;flex:none}
#nowbar{display:flex;align-items:center;gap:var(--s3);width:100%;
  min-height:var(--nowbar);padding:var(--s2) var(--s4) calc(var(--s2) + var(--safe-b));
  background:var(--g1);border:0;border-top:1px solid var(--g3);
  color:var(--g8);font:var(--t-body);text-align:left;cursor:pointer}
#nowbar .txt{flex:1;min-width:0}
#nowbar .txt b{display:block;color:var(--g9);font-weight:600;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
#nowbar .txt span{display:block;font:var(--t-meta);color:var(--g7)}
#nowbar .meter{position:absolute;left:0;right:0;bottom:0;margin:0;border-radius:0}
/* IMMERSIVE: the judge page asks for the screen and gets it. The bottom bar is
   removed rather than compressing a 100vh stage by 56px. */
body[data-chrome=immersive] #nowwrap{display:none}
body[data-chrome=immersive] #tabs{height:var(--grab);min-height:var(--grab);
  overflow:hidden;padding-top:0}
body[data-chrome=immersive] #tabs button{min-height:var(--grab);font-size:0;
  border-bottom:0}
body[data-chrome=immersive] #tabs .n{display:none}
body[data-chrome=immersive] #tabs button.on{background:var(--g4)}
"""

BODY = """
<div id=tabs role=tablist aria-label="sections">
  <button id=t_gpu class=on role=tab aria-selected=true data-tab=gpu>
    GPU<span class=n id=n_gpu></span></button>
  <button id=t_judge role=tab aria-selected=false data-tab=judge>
    Judging<span class=n id=n_judge></span></button>
  <button id=t_dataset role=tab aria-selected=false data-tab=dataset>
    Training sets<span class=n id=n_dataset></span></button>
</div>

<iframe id=p_gpu class="pane on" src="/queue" title="GPU"></iframe>
<iframe id=p_judge class=pane title="Judging"></iframe>
<iframe id=p_dataset class=pane title="Training sets"></iframe>

<div id=nowwrap>
  <button id=nowbar aria-label="what the card is doing">
    <span id=nowpill></span>
    <span class=txt><b id=nowline>reading the card&hellip;</b><span id=nowsub></span></span>
    <span class=chev aria-hidden=true>&#8250;</span>
    <span class="meter meter-thin" id=nowmeter hidden><i style="width:0"></i></span>
  </button>
</div>
"""

OWN_JS = r"""
const $=id=>document.getElementById(id);
const SRC={gpu:'/queue',judge:'/judge',dataset:'/dataset'};
/* The phone's browser chrome carries the worst state in the house. The colours
   come from the stylesheet, so the hub holds no hex literal of its own. */
const TINT={stop:'stop-bg',you:'you-bg',live:'live-bg',unknown:'unk-bg',idle:'g0'};

function show(tab,ref){
  if(!(tab in SRC)) tab='gpu';
  for(const k of Object.keys(SRC)){
    const on=k===tab, f=$('p_'+k), b=$('t_'+k);
    b.classList.toggle('on',on); b.setAttribute('aria-selected',on?'true':'false');
    f.classList.toggle('on',on);
    if(on){
      /* first visit loads the frame; later visits only move its hash, so a
         140-image set keeps its scroll position exactly as it does today */
      if(!f.src) f.src=SRC[k]+(ref?'#'+ref:'');
      else if(ref){ try{ f.contentWindow.location.hash=ref; }catch(e){} }
    }
    try{ f.contentWindow.postMessage({sm:1,t:on?'shown':'hidden'},location.origin); }
    catch(e){}
  }
  document.body.dataset.chrome='normal';   /* a tab switch always restores chrome */
  const h='#'+tab+(ref?'/'+ref:'');
  if(location.hash!==h) history.replaceState(null,'',h);
}
$('tabs').addEventListener('click',e=>{
  if(document.body.dataset.chrome==='immersive'){
    document.body.dataset.chrome='normal'; return;   /* the grab strip */
  }
  const b=e.target.closest('button[data-tab]'); if(b) show(b.dataset.tab);
});
window.addEventListener('message',e=>{
  if(e.origin!==location.origin) return;
  const m=e.data; if(!m||m.sm!==1) return;
  if(m.t==='go') show(m.tab,m.ref);
  else if(m.t==='chrome') document.body.dataset.chrome=
    m.mode==='immersive'?'immersive':'normal';
  else if(m.t==='counts') now();
});
$('nowbar').onclick=()=>show('gpu');

function badge(el,n,sev){
  el.textContent=n?n:''; el.className='n'+(n?' show':'')+(n?' '+sev:'');
}
async function now(){
  let d;
  try{ d=await SM.getJSON('/hub/now'); }
  catch(e){
    $('nowpill').innerHTML=SM.pill('unknown');
    $('nowline').textContent='Cannot reach the monitor';
    $('nowsub').textContent=e.message+' - retrying';
    document.title='(?) SourceMode';
    return;
  }
  $('nowpill').innerHTML=SM.pill(d.pill.status,d.pill.word);
  $('nowline').textContent=d.line;
  $('nowsub').textContent=d.sub||'';
  const m=$('nowmeter'); m.hidden=d.progress==null;
  if(d.progress!=null) m.firstElementChild.style.width=Math.round(d.progress*100)+'%';
  badge($('n_gpu'),d.counts.gpu,d.severity==='stop'?'stop':'you');
  badge($('n_judge'),d.counts.judge,'you');
  badge($('n_dataset'),d.counts.datasets,'you');
  tint(d.severity);
  const nTotal=d.counts.gpu+d.counts.judge+d.counts.datasets;
  document.title=(d.severity==='stop'?'(!) ':(d.severity==='you'?'('+nTotal+') ':''))
    +'SourceMode';
}
function tint(sev){
  document.querySelector('meta[name=theme-color]')
    .setAttribute('content',SM.token(TINT[sev]||TINT.idle));
}
tint('idle');
const start=location.hash.slice(1).split('/');
show(start[0]||'gpu',start[1]);
SM.poll(15000,now);
"""

# The theme-color tag ships with NO content: a `content="#0b0c0e"` is a quoted
# hex literal, and no page may hold one. `tint()` fills it from --g0 on load.
PAGE = page("SourceMode", BODY, OWN_JS, OWN_CSS, head="<meta name=theme-color>")


def _counts(cfg: dict) -> tuple[dict, list[str]]:
    """The three badge counts, each guarded on its own.

    The old `/hub/counts` wrapped only `gpu` in try/except, while `judge` and
    `datasets` called `list_sets()` / `list_previews()` bare - and `list_sets()`
    reads `s["items"]` and `s["title"]` with no guard. One malformed manifest
    among the 88 files in `outputs/judge/sets/` therefore 500s all three badges.
    Each count now fails alone and says so in `degraded`.
    """
    from ..assets.judge import judge_root, list_sets  # noqa: PLC0415
    from ..train.preview import list_previews, preview_root  # noqa: PLC0415

    from .queue_page import queue_state  # noqa: PLC0415

    out, degraded = {}, []
    for key, fn in (
        ("gpu", lambda: queue_state(cfg)["attention"]),
        ("judge", lambda: sum(1 for s in list_sets(judge_root(cfg)) if not s["done"])),
        ("datasets", lambda: sum(1 for s in list_previews(preview_root(cfg))
                                 if not s["approved"])),
    ):
        try:
            out[key] = fn()
        except Exception:  # noqa: BLE001 - a badge must never 500 the whole hub
            out[key] = 0
            degraded.append(key)
    return out, degraded


def _now(cfg: dict, status=None) -> dict:
    """One sentence about the card, the severity, and the three counts.

    `severity` is the max over: a queue alarm (`stop`), something waiting on him
    (`you`), a running job (`live`), an unreadable GPU (`unknown`), else `idle`.
    The card gets no status of its own - it reports the job holding it, or says
    that nothing holds it.
    """
    from .queue_page import queue_state  # noqa: PLC0415

    counts, degraded = _counts(cfg)

    try:
        q = queue_state(cfg)
    except Exception:  # noqa: BLE001
        q = {"jobs": [], "paused": False, "pause_reason": "", "lease": None,
             "queued_s": None}
        degraded.append("queue")

    stat = {}
    if status is not None:
        try:
            stat = status() or {}
        except Exception:  # noqa: BLE001
            degraded.append("status")

    jobs = q.get("jobs") or []
    running = next((j for j in jobs if j["status"] == "running"), None)
    waiting = [j for j in jobs if j["status"] == "queued" and not j["hold"]]
    lease = q.get("lease")
    runner_down = bool(jobs) and not (lease and lease.get("alive"))

    job, training = stat.get("job") or {}, stat.get("training") or {}
    gpu = stat.get("gpu") or {}

    # the sentence
    if running:
        line = running["who"] + " - " + running["what"]
        bits = []
        if training.get("epoch") is not None and training.get("epochs"):
            bits.append("epoch " + str(training["epoch"]) + " of " + str(training["epochs"]))
        prog = training.get("progress") or {}
        if prog.get("eta_s"):
            bits.append(_dur(prog["eta_s"]) + " left")
        sub = " · ".join(bits)
        progress = (prog["step"] / prog["total"]) if prog.get("total") else job.get("progress")
        status_word = "live"
    else:
        line = "Nothing is running"
        sub = (str(len(waiting)) + " waiting · " + _dur(q.get("queued_s"))
               + " of work") if waiting else "the card is free"
        progress, status_word = None, "wait"

    severities = ["idle"]
    if running:
        severities.append("live")
    if gpu and gpu.get("util_pct") is None and gpu.get("mem_used_mb") is None:
        severities.append("unknown")
    if counts.get("gpu") or counts.get("judge") or counts.get("datasets"):
        severities.append("you")
    if q.get("paused") or runner_down or any(j["status"] == "failed" for j in jobs):
        severities.append("stop")
    severity = _worst(severities)

    pill = {"status": status_word, "word": None}
    if runner_down:
        line = "The runner is not running - nothing in the queue will start"
        sub = (str(len(jobs)) + " jobs waiting · " + _dur(q.get("queued_s"))
               + " of work") if jobs else ""
        pill = {"status": "stop", "word": "Stopped"}
    elif q.get("paused"):
        line = "The queue is paused"
        sub = q.get("pause_reason") or ""
        pill = {"status": "stop", "word": "Paused"}
    elif severity == "unknown":
        pill = {"status": "unknown", "word": None}

    return {"severity": severity, "pill": pill, "line": line, "sub": sub,
            "progress": progress, "counts": counts,
            "sampled_at": stat.get("sampled_at"), "degraded": degraded}


_RANK = {"stop": 5, "you": 4, "unknown": 3, "live": 2, "idle": 0}


def _worst(items: list[str]) -> str:
    return max(items, key=lambda s: _RANK.get(s, 0))


def _dur(s) -> str:
    """Same shape as SM.dur, for the one sentence built server-side."""
    if not s:
        return "0m"
    s = int(round(s))
    h, m = s // 3600, s % 3600 // 60
    return f"{h}h {m:02d}m" if h else (f"{m}m" if m else f"{s}s")


def hub_router(cfg: dict, status=None):
    from fastapi import APIRouter  # noqa: PLC0415
    from fastapi.responses import HTMLResponse  # noqa: PLC0415

    r = APIRouter()

    @r.get("/", response_class=HTMLResponse)
    def _hub():
        return PAGE

    @r.get("/hub/now")
    def _hub_now() -> dict:
        return _now(cfg, status)

    @r.get("/hub/counts")
    def _hub_counts() -> dict:
        """Kept as an alias for one release: a phone holding the old cached page
        polls this, and it must not 404 under it."""
        counts, _ = _counts(cfg)
        return counts

    return r
