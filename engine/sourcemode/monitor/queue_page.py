"""The GPU page: what the card is doing, what is next, and what is ready to start.

Written as a control surface, not a readout. Two rules it exists to enforce:

- **Nothing approved can hide.** Jeremy's rule is that approval IS the trigger and
  approval order IS the training order. The first version of this page listed only
  jobs someone had typed into the queue, so sunny_v2 (approved 2026-09-22) and
  three others sat approved and untrained without appearing anywhere. The
  "Ready to train" list is therefore built from the APPROVAL RECORDS, not from a
  hand-maintained list, and it is sorted by when he approved them.
- **He can start work without opening Claude Code.** The training command is built
  here, server-side, from a dataset id - he never types a path or a flag. The job
  still carries `requires_approval`, so the runner re-checks approval at start
  time rather than trusting what this page saw.

Labels are written for a person: "Marisol - LoRA training" and "epoch 3 of 24,
4h 12m left", never "j001 train:marisol_v2". The job id is still there, small, so
a log line can be matched back to a row.

Dragging uses POINTER events, not HTML5 drag-and-drop, because this page is read
on a phone over Tailscale and HTML5 DnD does not fire on touch. The arrows stay as
a fallback.

    GET  /queue                     the page (the hub's first tab)
    GET  /queue/state               jobs, lease, pause, the runner's last line
    GET  /queue/candidates          approved datasets with no checkpoints
    POST /queue/training            {"dataset": "marisol_v2"} -> queued
    POST /queue/order               {"ids": [...]} -> exactly that order
    POST /queue/pause|resume
    POST /queue/job/{id}/hold       {"hold": true|false}
    POST /queue/job/{id}/move       {"position": n}
    POST /queue/job/{id}/cancel
"""

from __future__ import annotations

import re
from pathlib import Path

# "marisol_v2" -> "marisol". A trailing version is a dataset convention, not part
# of the character's name, and the page shows the result before anything is queued.
_VERSION_TAIL = re.compile(r"_v\d+$")

KIND_LABEL = {
    "prep": "captions and preview",
    "train": "LoRA training",
    "eval": "epoch sweep",
    "assets": "asset render",
    "other": "job",
}

PAGE = """<!-- gpu control -->
<title>SourceMode GPU</title>
<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>
 :root{--bg:#111;--card:#191919;--line:#2d2d2d;--dim:#8a8a8a;--fg:#e8e8e8}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif;
   padding:14px 14px 48px;-webkit-text-size-adjust:100%}
 h2{font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:var(--dim);
   margin:26px 0 10px;font-weight:700}
 .card{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:14px}
 .now .what{font-size:19px;font-weight:600}
 .now .sub{color:var(--dim);margin-top:3px}
 .bar{height:7px;background:#272727;border-radius:4px;overflow:hidden;margin-top:11px}
 .bar>i{display:block;height:100%;background:linear-gradient(90deg,#3b82f6,#60a5fa);
   transition:width .6s}
 .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:12px}
 .stats div{background:#141414;border:1px solid #242424;border-radius:6px;padding:7px 9px}
 .stats span{display:block;font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}
 .stats b{font-size:17px;font-weight:600}

 .row{display:flex;gap:11px;align-items:flex-start;background:var(--card);
   border:1px solid var(--line);border-radius:9px;padding:12px;margin-bottom:9px;
   touch-action:pan-y}
 .row.drag{opacity:.45}
 .row.over{border-color:#3b82f6;box-shadow:0 0 0 1px #3b82f6 inset}
 .row.running{border-color:#1d4e76}
 .row.held{border-color:#6b5520;background:#1d1a12}
 .row.failed{border-color:#6b2424;background:#1d1212}
 .grip{width:26px;min-width:26px;height:34px;cursor:grab;color:#555;display:flex;
   align-items:center;justify-content:center;font-size:19px;user-select:none;touch-action:none}
 .grip:active{cursor:grabbing}
 .body{flex:1;min-width:0}
 .who{font-size:17px;font-weight:600}
 .kind{color:var(--dim)}
 .state{margin-top:4px}
 .state.go{color:#6ee89a}
 .state.wait{color:#9cc6ff}
 .state.hold{color:#e8cf6e}
 .state.bad{color:#ff9a9a}
 .note{color:var(--dim);font-size:13px;margin-top:5px}
 .est{margin-top:5px;color:#cbd5e1}
 .est b{color:#fff}
 .jid{font-family:ui-monospace,monospace;font-size:11px;color:#5a5a5a;margin-top:6px}
 .acts{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
 button{background:#272727;color:var(--fg);border:1px solid #454545;padding:7px 12px;
   border-radius:6px;font:inherit;font-size:13px;cursor:pointer;min-height:36px}
 button:hover{background:#333}
 button:disabled{opacity:.3;cursor:default}
 button.go{background:#17422a;border-color:#2b6b45;color:#c7f6d8}
 button.warn{background:#44200f;border-color:#7a3c1c;color:#ffd6b8}
 .alarm{background:#3a1414;border:1px solid #7a2626;border-radius:9px;padding:13px;margin-bottom:12px}
 .ready{display:flex;gap:11px;align-items:center;background:#15190f;border:1px solid #394420;
   border-radius:9px;padding:12px;margin-bottom:9px;flex-wrap:wrap}
 .ready .body{flex:1;min-width:140px}
 .stale{color:#e8cf6e}
 .empty{color:var(--dim)}
 code{color:#8fa7bd;font-size:12px;word-break:break-all}
</style>
<div id=app class=empty>loading…</div>
<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s==null?'':s).replace(/[<>&"]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c]));
let state=null,stat=null,cands=[],busyPost=false;
const NL=String.fromCharCode(10);

const dur=s=>{ if(s==null) return ''; s=Math.round(s);
  const h=Math.floor(s/3600),m=Math.floor(s%3600/60);
  return h? h+'h '+m+'m' : (m? m+'m' : s+'s'); };

function ago(iso){
  if(!iso) return '';
  const d=Math.max(0,(Date.now()-new Date(iso).getTime())/1000);
  if(d<3600) return Math.round(d/60)+' minutes ago';
  if(d<86400) return Math.round(d/3600)+' hours ago';
  const days=Math.round(d/86400);
  return days+(days===1?' day ago':' days ago');
}

async function load(){
  try{
    [state,stat,cands]=await Promise.all([
      fetch('/queue/state',{cache:'no-store'}).then(r=>r.json()),
      fetch('/status',{cache:'no-store'}).then(r=>r.json()).catch(()=>null),
      fetch('/queue/candidates',{cache:'no-store'}).then(r=>r.json()).catch(()=>[]),
    ]);
    draw();
  }catch(e){ $('app').innerHTML='<div class=alarm>Could not reach the monitor: '+esc(e.message)+'</div>'; }
}

// --- what the card is doing -------------------------------------------------
function nowCard(){
  const g=stat&&stat.gpu, j=stat&&stat.job;
  let h='<div class="card now">';
  h+='<div class=what>'+esc(j?j.title:'Unknown')+'</div>';
  const tr=stat&&stat.training, bits=[];
  if(tr&&tr.epoch!=null&&tr.epochs) bits.push('epoch '+tr.epoch+' of '+tr.epochs);
  else if(j&&j.step!=null&&j.total) bits.push('step '+j.step+' of '+j.total);
  if(j&&j.eta_s) bits.push(dur(j.eta_s)+' left');
  if(j&&j.detail) bits.push(j.detail);
  if(bits.length) h+='<div class=sub>'+esc(bits.join(' · '))+'</div>';
  if(j&&j.progress!=null) h+='<div class=bar><i style="width:'+Math.round(j.progress*100)+'%"></i></div>';
  if(g) h+='<div class=stats>'
    +'<div><span>load</span><b>'+(g.util_pct==null?'—':g.util_pct+'%')+'</b></div>'
    +'<div><span>vram</span><b>'+(g.mem_used_mb==null?'—':(g.mem_used_mb/1024).toFixed(1)+' GB')+'</b></div>'
    +'<div><span>power</span><b>'+(g.power_w==null?'—':Math.round(g.power_w)+' W')+'</b></div>'
    +'<div><span>temp</span><b>'+(g.temp_c==null?'—':Math.round(g.temp_c)+'°C')+'</b></div>'
    +'</div>';
  return h+'</div>';
}

// --- one queue row ----------------------------------------------------------
function jobRow(j,i,n){
  const cls=['row'];
  if(j.status==='running') cls.push('running');
  else if(j.hold) cls.push('held');
  else if(j.status==='failed') cls.push('failed');

  let state='',sc='wait';
  if(j.status==='running'){
    sc='go'; state='Running now';
    const tr=stat&&stat.training;
    if(tr&&tr.epoch!=null&&tr.epochs) state='Running — epoch '+tr.epoch+' of '+tr.epochs;
    else if(tr&&tr.progress) state='Running — step '+tr.progress.step+' of '+tr.progress.total;
    if(tr&&tr.progress&&tr.progress.eta_s) state+=' · '+dur(tr.progress.eta_s)+' left';
  }
  else if(j.status==='failed'){ state='Failed (exit '+j.exit_code+')'; sc='bad'; }
  else if(j.hold){ state='Held — it will not start until you release it'; sc='hold'; }
  else if(j.blocked_reason){ state=j.blocked_reason; sc='bad'; }
  else if(j.is_next){ state=state_next(); sc='wait'; }
  else state='Waiting its turn';

  let h='<div class="'+cls.join(' ')+'" data-id="'+esc(j.id)+'" data-pos="'+i+'">';
  h+= j.status==='running' ? '<div class=grip style="cursor:default">▌</div>'
                           : '<div class=grip data-grip="'+esc(j.id)+'" title="drag to reorder">⠿</div>';
  h+='<div class=body>';
  h+='<div class=who>'+esc(j.who)+' <span class=kind>— '+esc(j.what)+'</span></div>';
  h+='<div class="state '+sc+'">'+esc(state)+'</div>';
  if(j.estimate&&j.estimate.total_s&&j.status!=='running')
    h+='<div class=est>'+dur(j.estimate.total_s)+' of GPU time once it starts — '
      +dur(j.estimate.train_s)+' training + '+dur(j.estimate.sweep_s)+' sweep</div>';
  if(j.note) h+='<div class=note>'+esc(j.note)+'</div>';
  h+='<div class=jid>'+esc(j.id)+(j.log?' · '+esc(j.log.split(/[\\\\/]/).pop()):'')+'</div>';
  if(j.status!=='running'){
    h+='<div class=acts>';
    h+='<button '+(i===0?'disabled':'')+' onclick="move(\\''+j.id+'\\','+(i-1)+')">▲ Up</button>';
    h+='<button '+(i>=n-1?'disabled':'')+' onclick="move(\\''+j.id+'\\','+(i+1)+')">▼ Down</button>';
    h+= j.hold ? '<button class=go onclick="hold(\\''+j.id+'\\',false)">Release — let it run</button>'
               : '<button onclick="hold(\\''+j.id+'\\',true)">Hold</button>';
    h+='<button class=warn onclick="cancel(\\''+j.id+'\\',\\''+esc(j.who)+'\\')">Remove</button>';
    h+='</div>';
  }
  return h+'</div></div>';
}

function state_next(){
  if(state.paused) return 'Next up — but the queue is paused';
  if(!state.lease||!state.lease.alive) return 'Next up — but the runner is not running';
  const s=state.runner_says||'';
  const m=s.match(/card busy - (.+?);/);
  if(m) return 'Next up — waiting for the card ('+m[1].replace(/PID \\d+ \\(/g,'').replace(/\\)/g,'')+')';
  return 'Next up — starts as soon as the card is free';
}

function draw(){
  const q=state.jobs||[];
  let h='';

  if(!state.lease||!state.lease.alive)
    h+='<div class=alarm><b>The runner is not running.</b><div class=empty>'
      +'Nothing in the queue will start. Run: Start-ScheduledTask "SourceMode GPU Runner"</div></div>';
  if(state.paused)
    h+='<div class=alarm><b>The queue is paused.</b><div class=empty>'+esc(state.pause_reason)+'</div>'
      +'<div class=acts><button class=go onclick="act(\\'/queue/resume\\')">Resume the queue</button></div></div>';

  h+=nowCard();

  h+='<h2>Queue</h2>';
  h+= q.length ? '<div id=list>'+q.map((j,i)=>jobRow(j,i,q.length)).join('')+'</div>'
               : '<div class="card empty">Nothing queued. Anything ready to train is listed below.</div>';
  if(state.queued_s)
    h+='<div class=note style="margin:-2px 0 8px">Waiting work adds about <b>'+dur(state.queued_s)
      +'</b> of GPU time after whatever is running now.</div>';
  if(q.some(j=>j.status!=='running')&&!state.paused)
    h+='<div class=acts style="margin-top:4px"><button onclick="act(\\'/queue/pause\\')">Pause the queue</button>'
      +'<span class=empty style="align-self:center">a running job is never interrupted</span></div>';

  h+='<h2>Ready to train</h2>';
  if(!cands.length) h+='<div class="card empty">Nothing approved is waiting. Everything approved is queued or trained.</div>';
  cands.forEach(c=>{
    h+='<div class=ready><div class=body>'
      +'<div class=who>'+esc(c.who)+' <span class=kind>— approved, never trained</span></div>'
      +'<div class="state '+(c.days_waiting>=3?'stale':'wait')+'">approved '+esc(ago(c.approved_at))
      +' · '+esc(c.images)+' images</div>'
      +(c.estimate&&c.estimate.total_s
         ? '<div class=est><b>'+dur(c.estimate.total_s)+'</b> of GPU time — '
           +dur(c.estimate.train_s)+' training + '+dur(c.estimate.sweep_s)+' sweep</div>'
           +'<div class=jid>'+esc(c.estimate.basis)+'</div>'
         : '')
      +'<div class=jid>'+esc(c.dataset)+' → character '+esc(c.character)+'</div></div>'
      +'<button class=go onclick="queueTraining(\\''+c.dataset+'\\',\\''+esc(c.who)+'\\','+(c.estimate&&c.estimate.total_s?Math.round(c.estimate.total_s):0)+)">Add to queue</button>'
      +'</div>';
  });

  h+='<h2>Runner</h2><div class=card>';
  h+= state.lease&&state.lease.alive
    ? '<div class=state style="color:#6ee89a">Running · PID '+esc(state.lease.pid)+' since '+esc(state.lease.started_at)+'</div>'
    : '<div class=state style="color:#ff9a9a">Not running</div>';
  if(state.runner_says) h+='<div class=note style="margin-top:7px"><code>'+esc(state.runner_says)+'</code></div>';
  h+='</div>';

  $('app').className='';
  $('app').innerHTML=h;
  wireDrag();
}

// --- actions ----------------------------------------------------------------
async function act(url,body){
  if(busyPost) return;
  busyPost=true;
  try{
    const r=await fetch(url,{method:'POST',headers:{'content-type':'application/json'},
                            body:body===undefined?undefined:JSON.stringify(body)});
    if(!r.ok){ const d=await r.json().catch(()=>({})); alert(d.detail||('HTTP '+r.status)); }
  }finally{ busyPost=false; }
  load();
}
const move=(id,pos)=>act('/queue/job/'+id+'/move',{position:pos});
const hold=(id,on)=>act('/queue/job/'+id+'/hold',{hold:on});
function cancel(id,who){ if(confirm('Remove '+who+' from the queue?')) act('/queue/job/'+id+'/cancel'); }
function queueTraining(ds,who,secs){
  const t=secs?dur(secs):'several hours';
  if(confirm('Queue '+who+' for LoRA training?'+NL+NL+'24 epochs plus the epoch sweep: about '+t
    +' of GPU time.'+NL+NL+'It starts only when the card is free, and her approval is re-checked first.'))
    act('/queue/training',{dataset:ds});
});
}

// --- pointer dragging (touch included; HTML5 DnD does not fire on touch) ----
function wireDrag(){
  const list=$('list'); if(!list) return;
  let dragEl=null,startY=0,moved=false;

  const rowsNow=()=>[...list.querySelectorAll('.row')];

  function down(e){
    const grip=e.target.closest('[data-grip]'); if(!grip) return;
    dragEl=grip.closest('.row'); startY=e.clientY; moved=false;
    dragEl.classList.add('drag');
    grip.setPointerCapture(e.pointerId);
    e.preventDefault();
  }
  function moveP(e){
    if(!dragEl) return;
    if(Math.abs(e.clientY-startY)>4) moved=true;
    for(const r of rowsNow()) r.classList.remove('over');
    const t=rowsNow().find(r=>{
      if(r===dragEl) return false;
      const b=r.getBoundingClientRect();
      return e.clientY>=b.top&&e.clientY<=b.bottom;
    });
    if(t) t.classList.add('over');
  }
  function up(e){
    if(!dragEl) return;
    const rows=rowsNow();
    const t=rows.find(r=>r.classList.contains('over'));
    dragEl.classList.remove('drag');
    for(const r of rows) r.classList.remove('over');
    const dropped=dragEl; dragEl=null;
    if(!moved||!t) return;
    // Reorder in the DOM first so the list does not jump, then send the whole
    // resulting order in ONE request - no intermediate states to get wrong.
    const before=t.getBoundingClientRect().top+t.getBoundingClientRect().height/2>e.clientY;
    t.parentNode.insertBefore(dropped,before?t:t.nextSibling);
    act('/queue/order',{ids:rowsNow().map(r=>r.dataset.id)});
  }
  list.addEventListener('pointerdown',down);
  list.addEventListener('pointermove',moveP);
  list.addEventListener('pointerup',up);
  list.addEventListener('pointercancel',up);
}

load(); setInterval(()=>{ if(!busyPost) load(); },5000);
</script>
"""


# How long a training run takes here, measured from completed runs rather than
# assumed: checkpoint-to-checkpoint wall time divided by the steps between saves.
# 2026-10-04, five runs: 5.03 / 5.08 / 5.10 / 5.17 / 5.33 s/step - tight enough to
# quote. The epoch sweep that follows ran 120, 121 and 121 minutes on the three
# most recent characters; the two older numbers (416m, 1866m) are a sweep WAITING
# for the card, not a sweep running, which is exactly the contention the queue now
# prevents. These are fallbacks: _rate() re-measures and only uses them if it cannot.
FALLBACK_S_PER_STEP = 5.10
FALLBACK_SWEEP_S = 121 * 60
EPOCHS = 24
_rate_cache: dict = {}


def _rate(cfg: dict, max_age_s: float = 600.0) -> dict:
    """(s_per_step, sweep_s) from past runs, so the estimate tracks the machine.

    Re-measured at most every ten minutes: it is a glob and a stat, but it is on
    the path of a page that polls every five seconds.
    """
    import statistics
    import time

    now = time.monotonic()
    if _rate_cache.get("at", 0) + max_age_s > now:
        return _rate_cache["value"]

    from ..config import outputs_dir  # noqa: PLC0415
    from ..train.dataset import choose_num_repeats  # noqa: PLC0415
    from ..train.preview import load_preview, preview_root  # noqa: PLC0415

    out = outputs_dir(cfg)
    root = preview_root(cfg)
    steps_rates, sweeps = [], []
    for lora in sorted((out / "lora-datasets").glob("*/lora")):
        cps = sorted(lora.glob("*-0000*.safetensors"), key=lambda p: p.stat().st_mtime)
        if len(cps) < 6:
            continue          # too few saves to time anything from
        ds = lora.parent.name
        doc = load_preview(root, ds)
        n = (doc.get("n") or len(doc.get("images", []))) if doc else 0
        if not n:
            continue
        per_epoch = n * choose_num_repeats(n)
        span = cps[-1].stat().st_mtime - cps[0].stat().st_mtime
        gaps = len(cps) - 1
        if span > 0 and gaps > 0:
            steps_rates.append(span / (gaps * per_epoch))
        js = out / "judge" / "sets" / f"dense_{ds}_asset.json"
        if js.is_file():
            sweep = js.stat().st_mtime - cps[-1].stat().st_mtime
            # A sweep that "took" six hours spent most of it waiting for the card.
            # Keep the plausible ones; the median would survive either way.
            if 0 < sweep < 4 * 3600:
                sweeps.append(sweep)

    value = {
        "s_per_step": statistics.median(steps_rates) if steps_rates else FALLBACK_S_PER_STEP,
        "sweep_s": statistics.median(sweeps) if sweeps else FALLBACK_SWEEP_S,
        "n_runs": len(steps_rates),
        "measured": bool(steps_rates),
    }
    _rate_cache.update(at=now, value=value)
    return value


def estimate(cfg: dict, images: int) -> dict:
    """Wall-clock estimate for the standard 24-epoch run plus its epoch sweep."""
    from ..train.dataset import choose_num_repeats  # noqa: PLC0415

    r = _rate(cfg)
    if images <= 0:
        return {"train_s": None, "sweep_s": None, "total_s": None, "steps": None,
                "basis": "no image count, so no estimate"}
    repeats = choose_num_repeats(images)
    steps = images * repeats * EPOCHS
    train_s = steps * r["s_per_step"]
    basis = (f"{images} images x{repeats} repeats x{EPOCHS} epochs = {steps} steps at "
             f"{r['s_per_step']:.2f} s/step"
             + (f", measured over {r['n_runs']} past runs" if r["measured"] else ", assumed"))
    return {"train_s": train_s, "sweep_s": r["sweep_s"], "total_s": train_s + r["sweep_s"],
            "steps": steps, "repeats": repeats, "basis": basis}


def character_of(dataset: str) -> str:
    """`marisol_v2` -> `marisol`. Shown in the UI before anything is queued, so a
    dataset whose name does not follow the convention is visible rather than silent."""
    return _VERSION_TAIL.sub("", dataset)


def _runner_last_line(outputs_root: Path) -> str | None:
    """The runner's own last log line - its account of what it is waiting for.
    This page never scans processes itself: the runner holds the lease and does the
    watching, and two sources of truth about a busy card is how the old launcher
    scripts ended up disagreeing with each other."""
    p = outputs_root / "logs" / "gpu-runner.log"
    if not p.is_file():
        return None
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    return lines[-1].strip() if lines else None


def queue_state(cfg: dict) -> dict:
    from ..config import outputs_dir  # noqa: PLC0415
    from ..gpu import queue as q  # noqa: PLC0415
    from ..gpu.lease import lease_path, pid_alive, read as read_lease  # noqa: PLC0415

    out = outputs_dir(cfg)
    doc = q.load(q.queue_path(out))
    head = q.head(doc)

    jobs = []
    for j in doc["jobs"]:
        if j["status"] in ("done", "cancelled"):
            continue
        row = {k: j[k] for k in ("id", "kind", "label", "status", "hold", "exit_code", "note", "log")}
        # Written for a person: the character, then what is being done to her.
        row["who"] = character_of(j["label"]).replace("_", " ").title()
        row["what"] = KIND_LABEL.get(j["kind"], j["kind"])
        if j["kind"] == "train":
            row["what"] = "LoRA training, then the epoch sweep"
        row["is_next"] = bool(head and j["id"] == head["id"])
        row["estimate"] = None
        if j["kind"] == "train":
            from ..train.preview import load_preview, preview_root  # noqa: PLC0415

            doc_prev = load_preview(preview_root(cfg), j["label"])
            imgs = (doc_prev.get("n") or len(doc_prev.get("images", []))) if doc_prev else 0
            row["estimate"] = estimate(cfg, imgs)
        row["blocked_reason"] = None
        # Only the head job can block the queue - it blocks rather than being
        # skipped - so it is the only one worth checking an approval for.
        if row["is_next"] and j["requires_approval"]:
            from ..gpu.runner import approval_ok  # noqa: PLC0415

            ok, why = approval_ok(j["requires_approval"])
            if not ok:
                row["blocked_reason"] = why
        jobs.append(row)

    rec = read_lease(lease_path(out))
    lease = None
    if rec:
        lease = {"pid": rec.get("pid"), "started_at": rec.get("started_at"),
                 "alive": pid_alive(int(rec.get("pid", 0)))}
    # What the queue adds AFTER whatever is running now - the number he actually
    # wants when deciding whether to add another character tonight.
    queued_s = sum((j["estimate"] or {}).get("total_s") or 0
                   for j in jobs if j["status"] == "queued" and not j["hold"])
    return {"jobs": jobs, "paused": doc["paused"], "pause_reason": doc["pause_reason"],
            "queued_s": queued_s or None,
            "lease": lease, "runner_says": _runner_last_line(out),
            "attention": sum(1 for j in jobs if j["blocked_reason"] or j["status"] == "failed")
                         + (1 if doc["paused"] else 0)
                         + (0 if (lease and lease["alive"]) or not jobs else 1)}


def candidates(cfg: dict) -> list[dict]:
    """Approved datasets with no checkpoints, oldest approval first.

    Built from the approval records rather than a list anyone maintains, because the
    hand-maintained version is how sunny_v2 sat approved and untrained from
    2026-09-22 - and how mira_v2 was missed before her. Approval order IS the
    training order, so that is the order they come back in.
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    from ..config import outputs_dir  # noqa: PLC0415
    from ..gpu import queue as q  # noqa: PLC0415
    from ..train.preview import approval_state, load_preview, preview_root  # noqa: PLC0415

    root = preview_root(cfg)
    out = outputs_dir(cfg)
    doc = q.load(q.queue_path(out))
    now = datetime.now(timezone.utc)

    rows = []
    for p in sorted((root / "previews").glob("*.json")):
        ds = p.stem
        st = approval_state(root, ds)
        if not st["approved"]:
            continue
        if list((out / "lora-datasets" / ds / "lora").glob("*.safetensors")):
            continue   # any checkpoint at all means trained; a prune deletes the losers
        if q.duplicate_of(doc, "train", ds):
            continue   # already queued or running
        doc_prev = load_preview(root, ds)
        waited = None
        if st["at"]:
            try:
                waited = (now - datetime.fromisoformat(st["at"])).days
            except ValueError:
                waited = None
        # The preview's own count: `n` if it carries one, else the images list.
        # NOT "items" - that key does not exist, and reading it reported 0 images
        # for every candidate.
        images = 0
        if doc_prev:
            images = doc_prev.get("n") or len(doc_prev.get("images", []))
        rows.append({"dataset": ds, "character": character_of(ds),
                     "who": character_of(ds).replace("_", " ").title(),
                     "approved_at": st["at"], "days_waiting": waited,
                     "images": images, "estimate": estimate(cfg, images)})
    rows.sort(key=lambda r: r["approved_at"] or "")
    return rows


def training_command(cfg: dict, dataset: str) -> list[str]:
    """The one place a training invocation is written. He never types a path."""
    from ..config import ENGINE_ROOT  # noqa: PLC0415

    script = ENGINE_ROOT / "scripts" / "train_character.ps1"
    return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
            "-Ds", dataset, "-Char", character_of(dataset)]


def queue_router(cfg: dict):
    from fastapi import APIRouter, Body, HTTPException  # noqa: PLC0415
    from fastapi.responses import HTMLResponse  # noqa: PLC0415

    from ..config import ENGINE_ROOT, outputs_dir  # noqa: PLC0415
    from ..gpu import queue as q  # noqa: PLC0415

    router = APIRouter()

    def path():
        return q.queue_path(outputs_dir(cfg))

    @router.get("/queue", response_class=HTMLResponse)
    def page() -> str:
        return PAGE

    @router.get("/queue/state")
    def state() -> dict:
        return queue_state(cfg)

    @router.get("/queue/candidates")
    def candidates_route() -> list[dict]:
        return candidates(cfg)

    @router.post("/queue/training")
    def add_training(body: dict = Body(default={})) -> dict:
        """Queue the standard training run for an approved dataset.

        The dataset must be approved NOW to be queued at all, and the job also
        carries requires_approval so the runner re-checks at start time - approval
        can lapse in between, by design, if the captions change.
        """
        from ..train.preview import approval_state, preview_root  # noqa: PLC0415

        ds = str(body.get("dataset", "")).strip()
        if not ds or "/" in ds or "\\" in ds or ".." in ds:
            raise HTTPException(400, "a dataset id is required")
        st = approval_state(preview_root(cfg), ds)
        if not st["approved"]:
            raise HTTPException(409, f"{ds} is not approved as it stands - review it first")

        p = path()
        doc = q.load(p)
        dup = q.duplicate_of(doc, "train", ds)
        if dup:
            raise HTTPException(409, f"{ds} is already {dup['status']} in the queue")
        job = q.add(doc, kind="train", label=ds, cmd=training_command(cfg, ds),
                    cwd=str(ENGINE_ROOT), requires_approval=ds,
                    note=f"queued from the GPU page; approved {st['at']}")
        q.save(p, doc)
        return {"queued": job["id"], **queue_state(cfg)}

    @router.post("/queue/order")
    def order(body: dict = Body(default={})) -> dict:
        ids = body.get("ids") or []
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise HTTPException(400, "ids must be a list of job ids")
        p = path()
        doc = q.load(p)
        try:
            q.reorder(doc, ids)
        except KeyError as exc:
            raise HTTPException(404, f"unknown job(s): {exc}") from exc
        q.save(p, doc)
        return queue_state(cfg)

    @router.post("/queue/pause")
    def pause() -> dict:
        p = path()
        doc = q.load(p)
        q.pause(doc, "paused by hand from the GPU page")
        q.save(p, doc)
        return queue_state(cfg)

    @router.post("/queue/resume")
    def resume() -> dict:
        p = path()
        doc = q.load(p)
        q.resume(doc)
        q.save(p, doc)
        return queue_state(cfg)

    @router.post("/queue/job/{job_id}/hold")
    def hold(job_id: str, body: dict = Body(default={})) -> dict:
        p = path()
        doc = q.load(p)
        try:
            q.set_hold(doc, job_id, bool(body.get("hold", True)))
        except KeyError as exc:
            raise HTTPException(404, f"no job {job_id}") from exc
        q.save(p, doc)
        return queue_state(cfg)

    @router.post("/queue/job/{job_id}/move")
    def move(job_id: str, body: dict = Body(default={})) -> dict:
        p = path()
        doc = q.load(p)
        try:
            q.move(doc, job_id, int(body.get("position", 0)))
        except KeyError as exc:
            raise HTTPException(404, f"no job {job_id}") from exc
        q.save(p, doc)
        return queue_state(cfg)

    @router.post("/queue/job/{job_id}/cancel")
    def cancel(job_id: str) -> dict:
        p = path()
        doc = q.load(p)
        try:
            q.cancel(doc, job_id)
        except KeyError as exc:
            raise HTTPException(404, f"no job {job_id}") from exc
        except ValueError as exc:  # running: stopping it is a deliberate act elsewhere
            raise HTTPException(409, str(exc)) from exc
        q.save(p, doc)
        return queue_state(cfg)

    return router
