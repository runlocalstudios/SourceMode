"""The GPU queue, on a phone: what is running, what is next, and the controls.

Deliberately NOT a second opinion about the card. The runner is the authority on
why it is waiting - it is the process holding the lease and watching the
processes - so this page reports the runner's own last log line rather than
running its own scan. Two sources of truth about "is the card busy" is how the
old launchers ended up disagreeing with each other.

    GET  /queue                   the page (a hub tab)
    GET  /queue/state             jobs, lease, pause, the runner's last line
    POST /queue/pause|resume
    POST /queue/job/{id}/hold     {"hold": true|false}
    POST /queue/job/{id}/move     {"position": n}
    POST /queue/job/{id}/cancel
"""

from __future__ import annotations

from pathlib import Path

PAGE = """<!-- gpu queue -->
<title>SourceMode GPU</title>
<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>
 body{margin:0;background:#111;color:#ddd;font:14px system-ui,sans-serif;padding:12px 12px 40px}
 h2{font-size:15px;margin:18px 0 8px;color:#aaa;font-weight:600}
 .card{background:#181818;border:1px solid #2c2c2c;border-radius:6px;padding:12px;margin-bottom:10px}
 .big{font-size:17px;color:#fff;margin-bottom:2px}
 .muted{color:#888}
 .bar{height:6px;background:#262626;border-radius:3px;overflow:hidden;margin-top:8px}
 .bar>i{display:block;height:100%;background:#4a9eff}
 .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(78px,1fr));gap:8px;margin-top:10px}
 .grid div{background:#141414;border:1px solid #262626;border-radius:4px;padding:6px 8px}
 .grid b{display:block;font-size:15px;color:#fff;font-weight:600}
 .job{display:flex;align-items:center;gap:8px;padding:9px 10px;border:1px solid #2c2c2c;
   border-radius:5px;margin-bottom:7px;background:#181818;flex-wrap:wrap}
 .job .id{font-family:ui-monospace,monospace;color:#777;font-size:12px}
 .job .what{flex:1;min-width:120px;color:#eee}
 .tag{font-size:11px;padding:2px 7px;border-radius:999px;background:#2a2a2a;color:#bbb}
 .tag.running{background:#13364f;color:#7fc2ff}
 .tag.next{background:#123d1e;color:#6ee89a}
 .tag.held{background:#3d3312;color:#e8cf6e}
 .tag.failed{background:#4a1a1a;color:#ff9a9a}
 .tag.blocked{background:#4a2a12;color:#ffb37a}
 button{background:#2a2a2a;color:#ddd;border:1px solid #555;padding:5px 9px;cursor:pointer;
   border-radius:3px;font:inherit;font-size:12px}
 button:disabled{opacity:.35;cursor:default}
 .warn{background:#3a1414;border-color:#6b2020}
 .ok{color:#6ee89a}
 .bad{color:#ff9a9a}
 code{color:#9ab;word-break:break-all}
</style>
<div id=app class=muted>loading…</div>
<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s==null?'':s).replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]));
let state=null,stat=null;

async function load(){
  try{
    [state,stat]=await Promise.all([
      fetch('/queue/state',{cache:'no-store'}).then(r=>r.json()),
      fetch('/status',{cache:'no-store'}).then(r=>r.json()).catch(()=>null),
    ]);
    draw();
  }catch(e){ $('app').innerHTML='<p class=bad>could not load: '+esc(e.message)+'</p>'; }
}

function hms(s){ if(s==null) return ''; s=Math.round(s);
  const h=Math.floor(s/3600),m=Math.floor(s%3600/60);
  return h?`${h}h ${m}m`:(m?`${m}m`:`${s}s`); }

function draw(){
  const g=stat&&stat.gpu, job=stat&&stat.job, q=state.jobs||[];
  let h='';

  // --- what the card is doing right now ---
  h+='<div class=card>';
  h+=`<div class=big>${esc(job?job.title:'unknown')}</div>`;
  if(job&&job.detail) h+=`<div class=muted>${esc(job.detail)}</div>`;
  if(job&&job.progress!=null){
    h+=`<div class=bar><i style="width:${Math.round(job.progress*100)}%"></i></div>`;
    h+=`<div class=muted style="margin-top:4px">${Math.round(job.progress*100)}%`
      +(job.step?` · step ${job.step}/${job.total}`:'')
      +(job.eta_s?` · ${hms(job.eta_s)} left`:'')+'</div>';
  }
  if(g) h+='<div class=grid>'
    +`<div>util<b>${g.util_pct==null?'—':g.util_pct+'%'}</b></div>`
    +`<div>vram<b>${g.mem_used_mb==null?'—':Math.round(g.mem_used_mb/1024)+'G'}</b></div>`
    +`<div>power<b>${g.power_w==null?'—':Math.round(g.power_w)+'W'}</b></div>`
    +`<div>temp<b>${g.temp_c==null?'—':Math.round(g.temp_c)+'°'}</b></div>`
    +'</div>';
  h+='</div>';

  // --- the queue ---
  if(state.paused) h+=`<div class="card warn"><b>Queue paused</b><div class=muted>`
    +esc(state.pause_reason)+`</div><p><button onclick="act('/queue/resume')">Resume the queue</button></p></div>`;

  h+='<h2>Queue</h2>';
  if(!q.length) h+='<p class=muted>Nothing queued.</p>';
  q.forEach((j,i)=>{
    const tags=[];
    if(j.status==='running') tags.push('<span class="tag running">running</span>');
    if(j.is_next) tags.push('<span class="tag next">next</span>');
    if(j.hold) tags.push('<span class="tag held">held</span>');
    if(j.status==='failed') tags.push(`<span class="tag failed">failed ${esc(j.exit_code)}</span>`);
    if(j.blocked_reason) tags.push('<span class="tag blocked">blocked</span>');
    h+='<div class=job>'
      +`<span class=id>${esc(j.id)}</span>`
      +`<span class=what>${esc(j.kind)}: <b>${esc(j.label)}</b></span>`
      +tags.join(' ');
    if(j.status==='queued'){
      h+=`<button ${i===0?'disabled':''} onclick="move('${j.id}',${i-1})">&#9650;</button>`
        +`<button onclick="move('${j.id}',${i+1})">&#9660;</button>`
        +`<button onclick="hold('${j.id}',${j.hold?'false':'true'})">${j.hold?'Release':'Hold'}</button>`
        +`<button onclick="cancel('${j.id}')">Cancel</button>`;
    }
    if(j.blocked_reason) h+=`<div class=muted style="flex-basis:100%">${esc(j.blocked_reason)}</div>`;
    if(j.note) h+=`<div class=muted style="flex-basis:100%;font-size:12px">${esc(j.note)}</div>`;
    h+='</div>';
  });

  if(!state.paused&&q.some(j=>j.status==='queued'))
    h+=`<p><button onclick="act('/queue/pause')">Pause the queue</button>
      <span class=muted>a running job is never interrupted</span></p>`;

  // --- the runner itself ---
  h+='<h2>Runner</h2><div class=card>';
  h+=state.lease&&state.lease.alive
    ? `<div class=ok>up · PID ${esc(state.lease.pid)} since ${esc(state.lease.started_at)}</div>`
    : '<div class=bad>NOT RUNNING — nothing will start. Start-ScheduledTask "SourceMode GPU Runner"</div>';
  if(state.runner_says) h+=`<div class=muted style="margin-top:6px"><code>${esc(state.runner_says)}</code></div>`;
  h+='</div>';

  $('app').className='';
  $('app').innerHTML=h;
}

async function act(url,body){
  await fetch(url,{method:'POST',headers:{'content-type':'application/json'},
                   body:body===undefined?undefined:JSON.stringify(body)});
  load();
}
const move=(id,pos)=>act(`/queue/job/${id}/move`,{position:pos});
const hold=(id,on)=>act(`/queue/job/${id}/hold`,{hold:on==='true'||on===true});
function cancel(id){ if(confirm('Cancel '+id+'?')) act(`/queue/job/${id}/cancel`); }

load(); setInterval(load,5000);
</script>
"""


def _runner_last_line(outputs_root: Path) -> str | None:
    """The runner's own last log line - its account of what it is waiting for."""
    p = outputs_root / "logs" / "gpu-runner.log"
    if not p.is_file():
        return None
    try:
        tail = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    return tail[-1].strip() if tail else None


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
        row = {k: j[k] for k in ("id", "kind", "label", "status", "hold", "exit_code", "note")}
        row["is_next"] = bool(head and j["id"] == head["id"])
        row["blocked_reason"] = None
        # Only the head job can block the queue, and it blocks rather than being
        # skipped - so that is the only one worth checking an approval for.
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
    return {"jobs": jobs, "paused": doc["paused"], "pause_reason": doc["pause_reason"],
            "lease": lease, "runner_says": _runner_last_line(out),
            "attention": sum(1 for j in jobs if j["blocked_reason"] or j["status"] == "failed")
                         + (1 if doc["paused"] else 0)
                         + (0 if (lease and lease["alive"]) or not jobs else 1)}


def queue_router(cfg: dict):
    from fastapi import APIRouter, Body, HTTPException  # noqa: PLC0415
    from fastapi.responses import HTMLResponse  # noqa: PLC0415

    from ..config import outputs_dir  # noqa: PLC0415
    from ..gpu import queue as q  # noqa: PLC0415

    router = APIRouter()
    path = lambda: q.queue_path(outputs_dir(cfg))  # noqa: E731

    @router.get("/queue", response_class=HTMLResponse)
    def page() -> str:
        return PAGE

    @router.get("/queue/state")
    def state() -> dict:
        return queue_state(cfg)

    @router.post("/queue/pause")
    def pause() -> dict:
        p = path()
        doc = q.load(p)
        q.pause(doc, "paused by hand from the queue page")
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
        except ValueError as exc:  # running: not cancellable from a web page
            raise HTTPException(409, str(exc)) from exc
        q.save(p, doc)
        return queue_state(cfg)

    return router
