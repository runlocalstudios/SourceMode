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

from .ui import page

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

OWN_CSS = r"""
/* The GPU page adds almost nothing: the whole page is system components. */
#stale{margin-bottom:var(--s3)}
.logbox{margin-top:var(--s2);max-height:46vh;overflow:auto;background:var(--g2);
  border:1px solid var(--g3);border-radius:var(--r1);padding:var(--s3);
  font-family:var(--mono);font-size:12px;line-height:1.5;white-space:pre-wrap;
  overflow-wrap:anywhere;color:var(--g8)}
.logbox b{color:var(--g9)}
/* The runner's own last line, which is its account of what it is waiting for. */
.runner-says{font-family:var(--mono);font-size:12px;color:var(--g7);
  word-break:break-all;margin-top:var(--s2)}
"""

BODY = """
<div id=stale hidden></div>
<div class=wrap id=app>
  <div class=col-main>
    <div id=banners></div>
    <h2>Now</h2>
    <div id=now><div class="card skel" style="height:148px"></div></div>
    <h2>Next 24 hours</h2>
    <div id=tonight></div>
    <h2>Queue</h2>
    <div id=list></div>
    <div id=queuefoot></div>
    <div id=removed></div>
  </div>
  <div class=col-rail>
    <h2>Ready to train</h2>
    <div id=cands></div>
    <div id=sweepwrap></div>
    <h2>Runner</h2>
    <div id=runner></div>
  </div>
</div>
"""

OWN_JS = r"""
const $=id=>document.getElementById(id);
let state=null,stat=null,cands=[],sweeps=[],plan=null,posting=false;

/* A dead poll must never look like fresh data. */
SM.staleHandler((age,msg)=>{
  const b=$('stale');
  b.hidden=!msg;
  $('app').classList.toggle('stale',!!msg);
  if(msg) b.className='banner unknown', b.innerHTML=
     '<span class=msg><b>These numbers are '+SM.dur(age)+' old.</b>'
    +'<span class=why>'+SM.esc(msg)+'. Still retrying.</span></span>'
    +'<button class="btn" data-act="reload">Retry now</button>';
});

async function load(){
  const [s,t,c,w,p]=await Promise.all([
    SM.getJSON('/queue/state'),
    SM.getJSON('/status').catch(()=>null),
    SM.getJSON('/queue/candidates').catch(()=>[]),
    SM.getJSON('/queue/sweepable').catch(()=>[]),
    SM.getJSON('/queue/plan').catch(()=>null)]);
  state=s; stat=t; cands=c; sweeps=w; plan=p;
  draw();
}

const gb=k=>(stat&&stat.gpu)?stat.gpu[k]:null;
const stats=()=>{
  const unk=gb('util_pct')==null&&gb('mem_used_mb')==null;
  const cell=(lab,val)=>'<div class="stat'+(unk?' unknown':'')+'"><span>'+lab+'</span><b>'
    +(val==null?'&mdash;':val)+'</b></div>';
  return '<div class=stats>'
    +cell('load',gb('util_pct')==null?null:gb('util_pct')+'%')
    +cell('vram',gb('mem_used_mb')==null?null:(gb('mem_used_mb')/1024).toFixed(1)+' GB')
    +cell('power',gb('power_w')==null?null:Math.round(gb('power_w'))+' W')
    +cell('temp',gb('temp_c')==null?null:Math.round(gb('temp_c'))+'°C')
    +'</div>';
};

/* --- banners: every alarm carries its own repair ------------------------- */
function drawBanners(){
  const n=state.now, out=[];
  if(!state.lease||!state.lease.alive){
    const work=state.queued_s?(' '+state.jobs.length+' job'+(state.jobs.length===1?'':'s')
      +' waiting, '+SM.dur(state.queued_s)+' of work.'):'';
    out.push('<div class="banner stop"><span class=msg><b>The runner is not running.</b>'
      +'<span class=why>Nothing in the queue will start.'+work+'</span></span>'
      +'<button class="btn btn-primary" data-act="runner-start">Start the runner</button></div>');
  }
  if(state.paused)
    out.push('<div class="banner stop"><span class=msg><b>The queue is paused.</b>'
      +'<span class=why>'+SM.esc(state.pause_reason||'')+'</span></span>'
      +'<button class="btn btn-primary" data-act="resume">Resume the queue</button></div>');
  if(n&&n.stalled)
    out.push('<div class="banner stop"><span class=msg><b>'+SM.esc(n.who||'This job')
      +'&#39;s log has not moved in '+SM.dur(n.log_age_s)+'.</b>'
      +'<span class=why>Last line at '+SM.esc((n.log_last_line_at||'').slice(11,19))
      +'. The process is still alive, so the card is held and nothing else will start.'
      +'</span></span>'
      +'<button class="btn" data-act="log" data-id="'+SM.esc(n.job_id)+'">Log tail</button>'
      +'<button class="btn" data-act="pause">Hold the rest of the queue</button></div>');
  for(const j of state.jobs) if(j.status==='failed')
    out.push('<div class="banner stop"><span class=msg><b>'+SM.esc(j.who)+' failed.</b>'
      +'<span class=why>'+SM.esc(j.state.why)+'. Requeueing brings it back held, so'
      +' nothing starts until you say so.</span></span>'
      +'<button class="btn" data-act="log" data-id="'+SM.esc(j.id)+'">Log tail</button>'
      +'<button class="btn btn-primary" data-act="requeue" data-id="'+SM.esc(j.id)
      +'">Requeue (held)</button></div>');
  SM.set($('banners'),null,out.join(''));
}

/* --- the card reports the job holding it, never a state of its own ------- */
function drawNow(){
  const n=state.now;
  if(!n||!n.job_id){
    const unk=gb('util_pct')==null&&gb('mem_used_mb')==null;
    SM.set($('now'),null,'<div class="card e-'+(unk?'unknown':'wait')+'">'
      +'<div class=card-head>'+SM.pill(unk?'unknown':'wait')
      +'<h3>'+(unk?'The card cannot be read':'Nothing is running')+'</h3></div>'
      +'<div class=card-sub>'+(unk
        ? 'nvidia-smi failed. Something may be running; the queue is not starting'
          +' anything while this is true.'
        : 'The card is free.'+(plan?(' '+SM.dur(plan.free_s)+' of the next 24h is unbooked.'):''))
      +'</div>'+stats()+'</div>');
    return;
  }
  const bits=[];
  if(n.epoch!=null&&n.epochs) bits.push('<span class=num>epoch '+n.epoch+' of '+n.epochs+'</span>');
  if(n.eta_s!=null) bits.push('<span class=num>'+SM.dur(n.eta_s)+'</span> left');
  if(n.progress_line) bits.push(SM.esc(n.progress_line));
  SM.set($('now'),null,'<div class="card e-'+(n.stalled?'stop':'live')+'">'
    +'<div class=card-head>'+SM.pill(n.stalled?'stop':'live')
    +'<h3>'+SM.esc(n.who)+' &mdash; '+SM.esc(n.what)+'</h3>'
    +'<span class=age>as of '+SM.dur(SM.ageOf())+' ago</span></div>'
    +'<div class="card-sub'+(n.ageing?' stale':'')+'">'+bits.join(' &middot; ')+'</div>'
    +(n.progress!=null?'<div class="meter'+(n.stalled?' stop':'')
       +'"><i style="width:'+Math.round(n.progress*100)+'%"></i></div>':'')
    +stats()
    +'<div class=card-foot><button class="btn btn-ghost" data-act="log" data-id="'
    +SM.esc(n.job_id)+'">Log tail</button>'
    +'<span class="age'+(n.ageing?' stale':'')+'">log last moved '
    +SM.dur(n.log_age_s)+' ago</span></div>'
    +'<div id=logout></div></div>');
}

/* --- tonight, as booked and unbooked time ------------------------------- */
function drawPlan(){
  if(!plan){ SM.set($('tonight'),null,''); return; }
  const W=plan.window_s;
  let bars='';
  for(const b of plan.blocks){
    /* an unknown-length block gets a visible minimum, not a 0% sliver */
    const share=b.unknown?4:(b.end_s-b.start_s)/W*100;
    bars+='<button class="b-'+b.status+'" style="flex:0 0 '+share.toFixed(1)+'%" '
      +'data-go="'+SM.esc(b.id)+'" title="'+SM.esc(b.basis)+'">'
      +SM.esc(b.who)+' '+(b.unknown?'?':SM.dur(b.end_s-b.start_s))+'</button>';
  }
  if(plan.free_s>0)
    bars+='<button class=b-free style="flex:0 0 '+(plan.free_s/W*100).toFixed(1)+'%" '
      +'disabled>'+SM.dur(plan.free_s)+' free</button>';
  let notes='';
  if(plan.held_n)
    notes+='<div class="plan-line dim">'+plan.held_n+' held job'+(plan.held_n===1?'':'s')
      +' ('+SM.dur(plan.held_s)+') not counted as booked &mdash; a job that cannot'
      +' start is not a booking.</div>';
  if(plan.blocked_n)
    notes+='<div class="plan-line dim">'+plan.blocked_n+' job'+(plan.blocked_n===1?'':'s')
      +' blocked and waiting on you, also not booked.</div>';
  let fits='';
  if(plan.fits.length){
    const f=plan.fits[0];
    fits='<div class=card-foot><span>'+SM.esc(f.who)+' is approved, unqueued, <b>'
      +SM.dur(f.total_s)+'</b> &mdash; she fits.</span>'
      +'<button class="btn btn-primary push" data-act="queue" data-ds="'+SM.esc(f.dataset)
      +'" data-who="'+SM.esc(f.who)+'" data-secs="'+Math.round(f.total_s)+'">Add to queue</button></div>';
  }
  SM.set($('tonight'),null,'<div class=card><div class=plan>'+bars+'</div>'
    +'<div class=plan-ticks><span>now '+SM.clock(plan.now_ts)+'</span>'
    +'<span>+12h</span><span>+24h</span></div>'
    +'<div class=plan-line>'+(plan.unknown_n
       ? ('Card busy until at least <b>'+SM.clock(plan.booked_until_ts)+'</b>'
          +' &middot; '+plan.unknown_n+' job'+(plan.unknown_n===1?'':'s')
          +' of unknown length on top')
       : ('Card frees at <b>'+SM.clock(plan.booked_until_ts)+'</b>'
          +' &middot; <b>'+SM.dur(plan.free_s)+'</b> unbooked'))+'.</div>'
    +notes+fits+'</div>');
}

/* --- one row shape for a queued job ------------------------------------- */
function jobRow(el,j,i,n){
  el.className='jrow e-'+j.state.status;
  const running=j.status==='running';
  SM.set(el,null,
    (running?'<div class=grip style="cursor:default" aria-hidden=true>&#9612;</div>'
            :'<div class=grip data-grip="'+SM.esc(j.id)+'" title="drag to reorder" '
             +'aria-label="reorder">&#10287;</div>')
    +'<div class=main>'
    +'<div class=head>'+SM.pill(j.state.status)+'<span class=title>'+SM.esc(j.who)
      +' <span class=what>&mdash; '+SM.esc(j.what)+'</span></span></div>'
    +'<div class=why>'+SM.esc(j.state.why)+'</div>'
    +(j.estimate&&j.estimate.total_s&&!running
       ? '<div class=est><b>'+SM.dur(j.estimate.total_s)+'</b> of GPU time once it starts'
         +' &mdash; '+SM.dur(j.estimate.train_s)+' training + '+SM.dur(j.estimate.sweep_s)
         +' sweep</div><div class=basis>'+SM.esc(j.estimate.basis)+'</div>' : '')
    +(j.note?'<div class=basis>'+SM.esc(j.note)+'</div>':'')
    +'<div class=jid>'+SM.esc(j.id)
      +(j.log?' &middot; '+SM.esc(String(j.log).split(/[\\/]/).pop()):'')+'</div>'
    +'<div class="acts btn-row">'+acts(j,i,n)+'</div>'
    +'</div>');
}
function acts(j,i,n){
  if(j.status==='running')
    return '<button class="btn btn-ghost" data-act="log" data-id="'+SM.esc(j.id)+'">Log tail</button>';
  let h='';
  if(j.state.status==='you'&&j.blocked_reason)
    h+='<button class="btn btn-primary" data-go-tab="dataset" data-ref="'+SM.esc(j.label)
      +'">Open her training set</button>';
  h+='<button class="btn btn-icon" data-act="up" data-id="'+SM.esc(j.id)+'" data-pos="'+i
    +'" aria-label="move up"'+(i===0?' disabled':'')+'>&#9650;</button>'
   +'<button class="btn btn-icon" data-act="down" data-id="'+SM.esc(j.id)+'" data-pos="'+i
    +'" aria-label="move down"'+(i>=n-1?' disabled':'')+'>&#9660;</button>'
   +(j.hold
      ? '<button class="btn btn-primary" data-act="hold" data-id="'+SM.esc(j.id)
        +'" data-on="0">Release &mdash; let it run</button>'
      : '<button class="btn" data-act="hold" data-id="'+SM.esc(j.id)+'" data-on="1">Hold</button>')
   +'<button class="btn btn-danger push" data-act="cancel" data-id="'+SM.esc(j.id)
    +'" data-who="'+SM.esc(j.who)+'">Remove</button>';
  return h;
}

function drawCand(el,c){
  el.className='jrow e-you';
  const e=c.estimate||{};
  SM.set(el,null,'<div class=main>'
    +'<div class=head>'+SM.pill('you')+'<span class=title>'+SM.esc(c.who)
      +' <span class=what>&mdash; approved, never trained</span></span></div>'
    +'<div class=why>approved '+SM.esc(SM.ago(c.approved_at))+' &middot; '
      +SM.esc(c.images)+' images</div>'
    +(e.total_s?'<div class=est><b>'+SM.dur(e.total_s)+'</b> of GPU time &mdash; '
       +SM.dur(e.train_s)+' training + '+SM.dur(e.sweep_s)+' sweep</div>'
       +'<div class=basis>'+SM.esc(e.basis)+'</div>':'')
    +'<div class="acts btn-row">'
    +'<button class="btn btn-primary" data-act="queue" data-ds="'+SM.esc(c.dataset)
      +'" data-who="'+SM.esc(c.who)+'" data-secs="'+Math.round(e.total_s||0)
      +'">Add to queue</button>'
    +'<button class="btn btn-ghost" data-go-tab="dataset" data-ref="'+SM.esc(c.dataset)
      +'">Review again</button></div></div>');
}

/* Trained, but no sweep set exists - so nothing ever asked which epoch is hers.
   Read-only on purpose: the eval step is launched inside train_character.ps1 and
   there is no standalone script to queue, so this reports rather than pretending
   a button could fix it. */
function drawSweeps(){
  if(!sweeps.length){ SM.set($('sweepwrap'),null,''); return; }
  let h='<h2>Trained, never swept</h2>';
  for(const s of sweeps)
    h+='<div class="jrow e-you"><div class=main>'
      +'<div class=head>'+SM.pill('you')+'<span class=title>'+SM.esc(s.who)
      +' <span class=what>&mdash; trained, never swept</span></span></div>'
      +'<div class=why>'+s.checkpoints+' checkpoint'+(s.checkpoints===1?'':'s')
      +' on disk and no epoch sweep set, so nothing has asked which epoch is hers.'
      +' The eval step runs inside the training script; if it failed, the log says'
      +' <code>EVAL FAILED - no judge set</code>.</div>'
      +'<div class=jid>'+SM.esc(s.dataset)+'</div></div></div>';
  SM.set($('sweepwrap'),null,h);
}

function drawRunner(){
  const alive=state.lease&&state.lease.alive;
  SM.set($('runner'),null,'<div class="card e-'+(alive?'done':'stop')+'">'
    +'<div class=card-head>'+SM.pill(alive?'done':'stop',alive?'Up':'Not running')
    +'<h3>'+(alive?('Up since '+SM.esc(String(state.lease.started_at).slice(0,16).replace('T',' '))):'The runner is not running')+'</h3>'
    +(alive?'<span class=age>pid '+SM.esc(state.lease.pid)+'</span>':'')+'</div>'
    +(state.runner_says?'<div class=runner-says>'+SM.esc(state.runner_says)+'</div>':'')
    +'</div>');
}

function drawRemoved(){
  if(!state.removed||!state.removed.length){ SM.set($('removed'),null,''); return; }
  let h='<h2>Recently removed</h2>';
  for(const r of state.removed.slice().reverse())
    h+='<div class="jrow e-you"><div class=main>'
      +'<div class=head>'+SM.pill('you')+'<span class=title>'+SM.esc(r.who)
      +' <span class=what>&mdash; '+SM.esc(r.what)+'</span></span></div>'
      +'<div class=why>Removed &mdash; put it back if that was a mis-click.'
      +' It returns held.</div><div class=jid>'+SM.esc(r.id)+'</div>'
      +'<div class="acts btn-row"><button class="btn btn-primary" data-act="restore" '
      +'data-id="'+SM.esc(r.id)+'">Restore (held)</button></div></div></div>';
  SM.set($('removed'),null,h);
}

function draw(){
  drawBanners(); drawNow(); drawPlan();
  const q=state.jobs||[];
  if(!q.length)
    SM.set($('list'),null,'<div class=empty><b>Nothing queued</b>'
      +'Anything approved and waiting is in Ready to train.</div>');
  else {
    if($('list').querySelector('.empty')) $('list').innerHTML='';
    SM.patch($('list'),q,j=>j.id,(el,j)=>jobRow(el,j,q.indexOf(j),q.length));
  }
  let foot='';
  if(state.queued_s)
    foot+='<div class=basis>Waiting work adds about <b>'+SM.dur(state.queued_s)
      +'</b> of GPU time after whatever is running now.</div>';
  if(q.some(j=>j.status!=='running')&&!state.paused)
    foot+='<div class="btn-row" style="margin-top:var(--s2)">'
      +'<button class="btn" data-act="pause">Pause the queue</button>'
      +'<span class=dim>a running job is never interrupted</span></div>';
  SM.set($('queuefoot'),null,foot);
  drawRemoved();
  if(!cands.length)
    SM.set($('cands'),null,'<div class=empty><b>Nothing waiting</b>'
      +'Everything approved is queued or trained.</div>');
  else {
    if($('cands').querySelector('.empty')) $('cands').innerHTML='';
    SM.patch($('cands'),cands,c=>'cand-'+c.dataset,drawCand);
  }
  drawSweeps(); drawRunner();
  /* the shell's bottom bar belongs to this frame while this tab is on top */
  const n=state.now;
  SM.ctx({title:(n&&n.job_id)?(n.who+' - '+n.what):'Nothing is running',
          sub:(n&&n.job_id&&n.epoch!=null)?('epoch '+n.epoch+' of '+n.epochs
               +(n.eta_s!=null?(' - '+SM.dur(n.eta_s)+' left'):'')):'',
          status:(n&&n.job_id)?(n.stalled?'stop':'live'):'wait',
          progress:(n&&n.job_id)?n.progress:null});
  wireDrag();
}

/* --- actions: ONE delegated listener for the whole page ------------------ */
const ACTS={
  'runner-start':()=>SM.postJSON('/queue/runner/start'),
  'queue':b=>confirmQueue(b),
  'hold':b=>SM.postJSON('/queue/job/'+b.dataset.id+'/hold',{hold:b.dataset.on==='1'}),
  'up':b=>SM.postJSON('/queue/job/'+b.dataset.id+'/move',{position:+b.dataset.pos-1}),
  'down':b=>SM.postJSON('/queue/job/'+b.dataset.id+'/move',{position:+b.dataset.pos+1}),
  'requeue':b=>SM.postJSON('/queue/job/'+b.dataset.id+'/requeue'),
  'restore':b=>SM.postJSON('/queue/job/'+b.dataset.id+'/restore'),
  'pause':()=>SM.postJSON('/queue/pause'),
  'resume':()=>SM.postJSON('/queue/resume'),
  'reload':()=>load(),
  'cancel':b=>confirm('Remove '+b.dataset.who+' from the queue?'+SM.NL+SM.NL
     +'Hold keeps its place instead. A removed job can still be restored below.')
     ? SM.postJSON('/queue/job/'+b.dataset.id+'/cancel') : null,
  'log':async b=>{
    const d=await SM.getJSON('/queue/job/'+b.dataset.id+'/log?lines=60');
    const host=$('logout')||$('banners');
    let h='';
    for(const p of d.parts)
      h+='<div class=logbox><b>'+SM.esc(p.file)+'</b>'+SM.NL
        +SM.esc(p.lines.join(SM.NL))+'</div>';
    host.innerHTML=h||'<div class=logbox>no log on disk for '+SM.esc(d.id)+'</div>';
  },
};
/* There is deliberately no action that stops a running job. Detection ships;
   a kill button on a phone surface waits for a conversation. */
function confirmQueue(b){
  const t=+b.dataset.secs?SM.dur(+b.dataset.secs):'several hours';
  return confirm('Queue '+b.dataset.who+' for LoRA training?'+SM.NL+SM.NL
    +'24 epochs plus the epoch sweep: about '+t+' of GPU time.'+SM.NL+SM.NL
    +'It starts only when the card is free, and her approval is re-checked first.')
    ? SM.postJSON('/queue/training',{dataset:b.dataset.ds}) : null;
}
document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-act],[data-go-tab],[data-go]'); if(!b) return;
  if(b.dataset.goTab) return SM.nav(b.dataset.goTab,b.dataset.ref);
  if(b.dataset.go){
    const row=document.querySelector('[data-k="'+b.dataset.go+'"]');
    if(row) row.scrollIntoView({block:'center',behavior:'smooth'});
    return;
  }
  const fn=ACTS[b.dataset.act]; if(!fn) return;
  if(posting) return;
  posting=true; b.disabled=true;
  try{ await fn(b); if(b.dataset.act!=='log') await load(); }
  catch(err){ SM.toast(err.message); }
  finally{ posting=false; b.disabled=false; }
});

/* --- pointer dragging. HTML5 DnD does not fire on touch, which is why this
   page has always used pointer events; the arrows stay as the fallback. ---- */
let dragWired=false;
function wireDrag(){
  const list=$('list'); if(!list||dragWired) return;
  dragWired=true;
  let dragEl=null,startY=0,moved=false;
  const rows=()=>[...list.querySelectorAll('.jrow')];
  list.addEventListener('pointerdown',e=>{
    const grip=e.target.closest('[data-grip]'); if(!grip) return;
    dragEl=grip.closest('.jrow'); startY=e.clientY; moved=false;
    dragEl.classList.add('dragging');
    dragEl.dataset.locked='1';     /* a poll mid-drag must not overwrite the row */
    grip.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  list.addEventListener('pointermove',e=>{
    if(!dragEl) return;
    if(Math.abs(e.clientY-startY)>4) moved=true;
    for(const r of rows()) r.classList.remove('dropzone');
    const t=rows().find(r=>{
      if(r===dragEl) return false;
      const b=r.getBoundingClientRect();
      return e.clientY>=b.top&&e.clientY<=b.bottom;
    });
    if(t) t.classList.add('dropzone');
  });
  const up=async e=>{
    if(!dragEl) return;
    const all=rows();
    const t=all.find(r=>r.classList.contains('dropzone'));
    dragEl.classList.remove('dragging');
    delete dragEl.dataset.locked;
    for(const r of all) r.classList.remove('dropzone');
    const dropped=dragEl; dragEl=null;
    if(!moved||!t) return;
    /* Reorder the DOM first so the list does not jump, then send the WHOLE
       resulting order in one request - no intermediate states to get wrong. */
    const b=t.getBoundingClientRect();
    t.parentNode.insertBefore(dropped,(b.top+b.height/2>e.clientY)?t:t.nextSibling);
    try{ await SM.postJSON('/queue/order',{ids:rows().map(r=>r.dataset.k)}); }
    catch(err){ SM.toast(err.message); }
    load();
  };
  list.addEventListener('pointerup',up);
  list.addEventListener('pointercancel',up);
}

if(SM.standalone()) document.title='SourceMode GPU';
SM.poll(5000,()=>{ if(!posting) return load(); });
"""

PAGE = page("SourceMode GPU", BODY, OWN_JS, OWN_CSS)


# How long a training run takes here, measured from completed runs rather than
# assumed: checkpoint-to-checkpoint wall time divided by the steps between saves.
# 2026-10-04, five runs: 5.03 / 5.08 / 5.10 / 5.17 / 5.33 s/step - tight enough to
# quote. The epoch sweep that follows ran 120, 121 and 121 minutes on the three
# most recent characters; the two older numbers (416m, 1866m) are a sweep WAITING
# for the card, not a sweep running, which is exactly the contention the queue now
# prevents. These are fallbacks: _rate() re-measures and only uses them if it cannot.
FALLBACK_S_PER_STEP = 5.10
FALLBACK_SWEEP_S = 121 * 60
# 2026-10-04, median over 24 finished sweeps: 79.6 s per rendered image, with the
# bulk tightly clustered 73-90 s. The asset figure is one finished pack (amanda,
# 56 shots) at 119 s - a shot is slower than a sweep render because the pack
# renders several candidates per look through the native pipeline.
FALLBACK_S_PER_RENDER = 79.6
FALLBACK_S_PER_SHOT = 119.0
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
        # Resolve the sweep by PATTERN + ARM GRAMMAR, not by a hardcoded
        # `_asset` suffix. Of 29 `dense_*` sets on disk only 6 carry `_asset`;
        # dense_ash_v2.json, dense_geena_v2.json and dense_trina_v2.json are
        # full 90-item epoch sweeps with no suffix at all, so the old filename
        # test silently declined to measure them.
        from ..assets.judge import judge_root, sweep_sets_for  # noqa: PLC0415

        rows_for_ds = sweep_sets_for(judge_root(cfg), ds)
        js = ((judge_root(cfg) / "sets" / f"{rows_for_ds[0]['id']}.json")
              if rows_for_ds else None)
        if js is not None and js.is_file():
            sweep = js.stat().st_mtime - cps[-1].stat().st_mtime
            # A sweep that "took" six hours spent most of it waiting for the card.
            # Keep the plausible ones; the median would survive either way.
            if 0 < sweep < 4 * 3600:
                sweeps.append(sweep)

    # How long ONE rendered image takes, measured the same way: the span across a
    # finished run divided by its images. A training step and a render are
    # different units and a page that quotes both must measure both - quoting
    # only the training rate is why every eval and asset job read as zero-length.
    def _per_file(root, pattern, lo=20.0, hi=600.0):
        """Seconds per image, as the MEDIAN GAP between consecutive files.

        Not span/count: amanda's pack is 504 shots across 28 hours and sandra's
        367 across 25, because a pack is rendered over days with the card doing
        other things in between. span/count measures the idle, not the work, and
        read 250 s/shot against a true ~120. A median gap ignores any number of
        pauses as long as most renders follow each other.

        The floor is 20 s, not 2, because the gap distribution is bimodal: a
        cluster around 4 s where several files land per render, and the real
        render gap above 50 s. Counting the fast cluster pulled sandra's median
        to 66 s against a true 116 - which is BELOW the sweep render rate, and
        that is what gave it away.
        """
        out = []
        for d in sorted(root.glob("*")):
            files = sorted((f for f in d.rglob(pattern) if "_web" not in f.parts),
                           key=lambda f: f.stat().st_mtime)
            if len(files) < 20:
                continue
            gaps = [b.stat().st_mtime - a.stat().st_mtime
                    for a, b in zip(files, files[1:])]
            gaps = [g for g in gaps if lo < g < hi]
            if len(gaps) >= 10:
                out.append(statistics.median(gaps))
        return out

    renders = _per_file(out, "scene_*.png")
    shots = [r for d in [out / "game-assets"] if d.is_dir()
             for r in _per_file(d, "shot_*.png")]

    value = {
        "s_per_step": statistics.median(steps_rates) if steps_rates else FALLBACK_S_PER_STEP,
        "sweep_s": statistics.median(sweeps) if sweeps else FALLBACK_SWEEP_S,
        "s_per_render": statistics.median(renders) if renders else FALLBACK_S_PER_RENDER,
        "s_per_shot": statistics.median(shots) if shots else FALLBACK_S_PER_SHOT,
        "n_runs": len(steps_rates), "n_render_runs": len(renders),
        "n_shot_runs": len(shots),
        "measured": bool(steps_rates),
        "render_measured": bool(renders), "shot_measured": bool(shots),
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
    # The step count is worth seeing; the rate it was multiplied by is not.
    # Jeremy, 2026-10-04: "We don't need to show the seconds per step. The total
    # training time is enough. And I do like to see the total steps."
    basis = f"{images} images x{repeats} repeats x{EPOCHS} epochs = {steps} steps"
    return {"train_s": train_s, "sweep_s": r["sweep_s"], "total_s": train_s + r["sweep_s"],
            "steps": steps, "repeats": repeats, "basis": basis}


STALL_S = 900.0    # 15 minutes of a silent log while the process is still alive
AGEING_S = 300.0   # past this the ETA is drawn with its age, not as a fresh number


def _dur(s: float | None) -> str:
    """"4h 18m". The same two-field shape SM.dur() prints, so a sentence
    composed on the server and one composed in the page never disagree."""
    if s is None:
        return ""
    s = int(round(s))
    h, m = s // 3600, s % 3600 // 60
    return f"{h}h {m:02d}m" if h else (f"{m}m" if m else f"{s}s")


def _iso_utc(ts: float) -> str:
    from datetime import datetime, timezone  # noqa: PLC0415

    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def _state_of(job: dict, *, paused: bool, runner_alive: bool,
              log_age_s: float | None) -> dict:
    """The ONE place a job's status word is decided. Pages never compute one.

    Seven words, one colour each, no synonyms - so two pages cannot disagree
    about what a held job is called. `log_age_s` is passed in rather than read:
    queue_state() is pure over the queue file and cannot see the training log.
    None means "we were not told", which is today's behaviour exactly - no stall
    detection, not a false negative.
    """
    if job["status"] == "running":
        if log_age_s is not None and log_age_s > STALL_S:
            return {"status": "stop",
                    "why": f"the log has not moved in {_dur(log_age_s)} - it may be stuck"}
        return {"status": "live", "why": "running now"}
    if job["status"] == "failed":
        return {"status": "stop", "why": f"failed, exit {job['exit_code']}"}
    if job["hold"]:
        return {"status": "you", "why": "held - it will not start until you release it"}
    if job["blocked_reason"]:
        return {"status": "you", "why": job["blocked_reason"]}
    if not job["is_next"]:
        return {"status": "wait", "why": "waiting its turn"}
    if paused:
        return {"status": "stop", "why": "next up, but the queue is paused"}
    if not runner_alive:
        return {"status": "stop", "why": "next up, but the runner is not running"}
    return {"status": "next", "why": "starts as soon as the card is free"}


def now_card(jobs: list[dict], status: dict | None) -> dict | None:
    """What the card is doing - the ONE place `progress_line` exists.

    queue_state() cannot compose this alone: the queue file knows which job is
    running, and the trainer's progress lives behind the sampler. The two are
    joined here and nowhere else.

    `log_age_s` is what makes a stall visible. It depends on
    training.sample_training() reporting the NEWER of the log and its `.err`
    sidecar - tqdm writes to stderr, so on a live run the `.log` stops moving.
    Before that was fixed a healthy run read as 196 minutes silent.
    """
    if not status:
        return None
    run = next((j for j in jobs if j["status"] == "running"), None)
    tr = status.get("training") or {}
    pr = tr.get("progress") or {}
    mtime, sampled = tr.get("log_mtime"), status.get("sampled_at")
    age = max(0.0, sampled - mtime) if (mtime and sampled) else None
    # The sampler's training block describes the most recent TRAINING run, which
    # is not necessarily what is on the card. Attributing it to a prep, eval or
    # assets job reported Tess's captioning as "step 3744 of 3744 at 5.44 s/it",
    # which was Zara's finished training run - a progress bar for the wrong job,
    # and before this a stall flag for the wrong job too. Training numbers are
    # reported only when a training job is what is running.
    training_job = bool(run and run.get("kind") == "train")
    step, total = (pr.get("step"), pr.get("total")) if training_job else (None, None)
    line = ""
    if step is not None and total:
        line = f"step {step} of {total}"
        if pr.get("s_per_it"):
            line += f" at {pr['s_per_it']:.2f} s/it"
    return {
        "job_id": run["id"] if run else None,
        "who": (run or {}).get("who"), "what": (run or {}).get("what"),
        "kind": (run or {}).get("kind"),
        "epoch": tr.get("epoch") if training_job else None,
        "epochs": tr.get("epochs") if training_job else None,
        "step": step, "total": total,
        "progress": (step / total) if (step is not None and total) else None,
        "eta_s": pr.get("eta_s") if training_job else None,
        "elapsed_s": pr.get("elapsed_s") if training_job else None,
        "s_per_it": pr.get("s_per_it") if training_job else None,
        "progress_line": line,
        "log": tr.get("log") if training_job else (run or {}).get("log"),
        "log_age_s": age if training_job else None,
        "log_last_line_at": _iso_utc(mtime) if (mtime and training_job) else None,
        "stalled": bool(training_job and age is not None and age > STALL_S),
        "ageing": bool(training_job and age is not None and age > AGEING_S),
        "sampled_at": sampled,
    }


def render_count(cmd: list[str]) -> tuple[int, str] | None:
    """How many images a queued RENDER job will produce, read from its command.

    Only the shapes this repo queues itself are understood; anything else
    returns None and is reported as unknown rather than guessed at. A job whose
    length cannot be derived must not be drawn as zero-length - that is how a
    schedule claims the card is free while three jobs are waiting on it.
    """
    import json as _json  # noqa: PLC0415
    from pathlib import Path as _P  # noqa: PLC0415

    joined = " ".join(cmd)

    def flag(name, default=None):
        return cmd[cmd.index(name) + 1] if name in cmd and cmd.index(name) + 1 < len(cmd) else default

    if "assets" in cmd and "render" in cmd:
        plan_p = flag("--plan")
        if not plan_p:
            return None
        try:
            doc = _json.loads(_P(plan_p).read_text(encoding="utf-8"))
            looks = sum(c["lookCount"] for c in doc["categories"].values())
        except (OSError, ValueError, KeyError):
            return None
        shots = int(flag("--shots", 4) or 4)
        only = flag("--only")
        if only:
            looks = len([x for x in only.split(",") if x.strip()])
        return looks * shots, f"{looks} looks x {shots} shots"

    if "prompt_ab.py" in joined:
        arms = len([a for a in (flag("--arms", "") or "").split("|") if "=" in a])
        scenes = len([x for x in (flag("--scenes", "0,2,6") or "").split(",") if x.strip()])
        if arms and scenes:
            return arms * scenes, f"{arms} arms x {scenes} scenes"
        return None

    if "dense_epoch_eval.py" in joined:
        # positional: script char sub total start end trigger ckpt [scenes]
        pos = [c for c in cmd if not c.startswith("--")]
        try:
            i = next(k for k, c in enumerate(pos) if c.endswith("dense_epoch_eval.py"))
            start, end = int(pos[i + 4]), int(pos[i + 5])
            scenes = int(pos[i + 8]) if len(pos) > i + 8 else 20
        except (StopIteration, ValueError, IndexError):
            return None
        epochs = flag("--epochs")
        n_eps = len([x for x in epochs.split(",") if x.strip()]) if epochs else (end - start + 1)
        if n_eps <= 0 or scenes <= 0:
            return None
        return n_eps * scenes, f"{n_eps} epochs x {scenes} scenes"
    return None


def job_estimate(cfg: dict, job: dict) -> dict | None:
    """Wall-clock for any queued job, or None when its length is unknowable."""
    if job["kind"] == "train":
        from ..train.preview import load_preview, preview_root  # noqa: PLC0415

        doc = load_preview(preview_root(cfg), job["label"])
        imgs = (doc.get("n") or len(doc.get("images", []))) if doc else 0
        return estimate(cfg, imgs)
    got = render_count(job.get("cmd") or [])
    if not got:
        return None
    n, how = got
    r = _rate(cfg)
    per = r["s_per_shot"] if job["kind"] == "assets" else r["s_per_render"]
    measured = r["shot_measured"] if job["kind"] == "assets" else r["render_measured"]
    unit = "shot" if job["kind"] == "assets" else "render"
    runs = r["n_shot_runs"] if job["kind"] == "assets" else r["n_render_runs"]
    return {"train_s": None, "sweep_s": None, "total_s": n * per, "steps": None,
            "basis": f"{how} = {n} {unit}s at {per:.0f} s/{unit}"
                     + (f", measured over {runs} past runs" if measured else ", assumed")}


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


def queue_state(cfg: dict, status: dict | None = None) -> dict:
    from ..config import outputs_dir  # noqa: PLC0415
    from ..gpu import queue as q  # noqa: PLC0415
    from ..gpu.lease import lease_path, pid_alive, read as read_lease  # noqa: PLC0415

    out = outputs_dir(cfg)
    doc = q.load(q.queue_path(out))
    head = q.head(doc)

    jobs, removed = [], []
    for j in doc["jobs"]:
        if j["status"] in ("done", "cancelled"):
            if j["status"] == "cancelled":
                removed.append({"id": j["id"], "kind": j["kind"], "label": j["label"],
                                "who": character_of(j["label"]).replace("_", " ").title(),
                                "what": KIND_LABEL.get(j["kind"], j["kind"]),
                                "ended_at": j["ended_at"]})
            continue
        row = {k: j[k] for k in ("id", "kind", "label", "status", "hold", "exit_code", "note", "log")}
        # Written for a person: the character, then what is being done to her.
        row["who"] = character_of(j["label"]).replace("_", " ").title()
        row["what"] = KIND_LABEL.get(j["kind"], j["kind"])
        if j["kind"] == "train":
            row["what"] = "LoRA training, then the epoch sweep"
        row["is_next"] = bool(head and j["id"] == head["id"])
        # Every kind, not just training: an eval or an asset pack is hours of the
        # card and used to be reported as nothing at all.
        row["estimate"] = job_estimate(cfg, j)
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

    # The status WORD for every row, decided in one place. A running job also
    # gets the log's age, which is the only way a silently stuck run is visible:
    # without it a dead process still renders as a healthy progress bar with a
    # confident, frozen ETA.
    now = now_card(jobs, status)
    age = (now or {}).get("log_age_s")
    for row in jobs:
        # The age we have is the TRAINING log's. A prep, eval or assets job
        # writes no training log, so handing it that age marked every one of
        # them Stopped fifteen minutes in - j002 went red while it was running
        # perfectly well. Only a training job is watched this way.
        watched = row["status"] == "running" and row["kind"] == "train"
        row["state"] = _state_of(
            row, paused=doc["paused"],
            runner_alive=bool(lease and lease["alive"]),
            log_age_s=age if watched else None)
    # What the queue adds AFTER whatever is running now - the number he actually
    # wants when deciding whether to add another character tonight.
    queued_s = sum((j["estimate"] or {}).get("total_s") or 0
                   for j in jobs if j["status"] == "queued" and not j["hold"])
    return {"jobs": jobs, "removed": removed[-5:],
            "paused": doc["paused"], "pause_reason": doc["pause_reason"],
            "queued_s": queued_s or None,
            "now": now,
            "lease": lease, "runner_says": _runner_last_line(out),
            "attention": sum(1 for j in jobs if j["blocked_reason"] or j["status"] == "failed")
                         + (1 if doc["paused"] else 0)
                         + (0 if (lease and lease["alive"]) or not jobs else 1)
                         + (1 if (now and now["stalled"]) else 0)}


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


def sweepable(cfg: dict) -> list[dict]:
    """Trained, but the epoch sweep never produced a judge set.

    A real stranding gap: `scripts/train_character.ps1` logs
    `EVAL FAILED - no judge set` and nothing ever mentions it again, so a
    five-hour run can finish with no way to choose an epoch and no surface
    saying so.

    The sweep is resolved by pattern AND arm grammar, never by a hardcoded
    `dense_<ds>_asset` filename - 23 of the 29 `dense_*` sets on disk have no
    `_asset` suffix, so the filename test would report a dozen characters as
    never swept and offer each a button that cannot help them.
    """
    from ..assets.judge import judge_root, sweep_sets_for  # noqa: PLC0415
    from ..config import outputs_dir  # noqa: PLC0415
    from ..gpu import queue as q  # noqa: PLC0415
    from ..train.epochs import checkpoint_dirs  # noqa: PLC0415
    from ..train.preview import preview_root  # noqa: PLC0415

    out = outputs_dir(cfg)
    jroot = judge_root(cfg)
    doc = q.load(q.queue_path(out))
    base = out / "lora-datasets"
    set_ids = [f.stem for f in (jroot / "sets").glob("*.json")] if (jroot / "sets").is_dir() else []
    rows = []
    for d in sorted(base.glob("*")) if base.is_dir() else []:
        if not d.is_dir():
            continue
        ds = d.name
        ckpts = [c for sub in checkpoint_dirs(out, ds) for c in sub.glob("*.safetensors")]
        if not ckpts:
            continue                       # not trained

        # A run with a custom output name is swept under THAT name, not the
        # dataset's: gabi_curated trained `gabi_full` and was swept as
        # `gabi_every_epoch`, jojo_curated trained `jojo_a2` and was swept as
        # `coarse_jojo_a2`, sunny_curated trained `sunny_r32` as
        # `coarse_sunny_r32`. Resolving on the dataset id alone reported all
        # three as never swept, which is three false alarms out of three.
        #
        # So the names to look under are the dataset, every checkpoint's output
        # name, and the leading token of each - and a match on ANY of them
        # counts. This list exists to prompt an action, so it must under-report
        # rather than over-report: a stranded run found late costs less than a
        # button that cannot help.
        names = {ds, character_of(ds)}
        for c in ckpts:
            stem = c.stem.rsplit("-", 1)[0] if c.stem.rsplit("-", 1)[-1].isdigit() else c.stem
            names.add(stem)
            names.add(stem.split("_")[0])
        names = {n for n in names if len(n) >= 3}
        if any(sweep_sets_for(jroot, n) for n in names):
            continue                       # already swept, under one of its names
        if any(any(n in sid for n in names) for sid in set_ids):
            continue                       # a judge set names it, grammar aside
        if q.duplicate_of(doc, "eval", ds) or q.duplicate_of(doc, "train", ds):
            continue                       # queued; the queue is the surface
        doc_prev = None
        try:
            from ..train.preview import load_preview  # noqa: PLC0415

            doc_prev = load_preview(preview_root(cfg), ds)
        except Exception:  # noqa: BLE001
            doc_prev = None
        rows.append({"dataset": ds, "character": character_of(ds),
                     "who": character_of(ds).replace("_", " ").title(),
                     "checkpoints": len(ckpts),
                     "images": (doc_prev.get("n") if doc_prev else 0) or 0})
    return rows


def position(cfg: dict, dataset: str) -> dict:
    """Where this dataset sits in the training order, and what it would cost.

    Approval IS the trigger and approval order IS the training order, so the
    page that performs an approval should be able to say what approving does.

    THE BUG this gets right: the obvious implementation compares candidate
    approval times against `approval_state(...)["at"]`, but for a dataset that is
    not approved yet that field is None. Coerced to "" it sorts BEFORE every real
    timestamp, so `before` is always empty and the answer is always "queued + 1" -
    which is the one case the feature exists for. Three explicit branches instead:

    - approved and current: its place is by its own approval time
    - never approved: it would be approved NOW, so it goes after every candidate
    - lapsed: also now. The old timestamp is not the answer either - re-approving
      is a new approval, and it goes to the back of the order, not back to where
      it used to be.
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    from ..config import outputs_dir  # noqa: PLC0415
    from ..gpu import queue as q  # noqa: PLC0415
    from ..train.preview import approval_state, load_preview, preview_root  # noqa: PLC0415

    root = preview_root(cfg)
    st = approval_state(root, dataset)
    rows = candidates(cfg)

    if st["approved"] and st["at"]:
        at, counts_itself = st["at"], True
    else:
        at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        counts_itself = False

    before = [c for c in rows
              if c["dataset"] != dataset and (c["approved_at"] or "") < at]
    doc = q.load(q.queue_path(outputs_dir(cfg)))
    queued = [j for j in doc["jobs"]
              if j["kind"] == "train" and j["status"] in ("queued", "running")]

    doc_prev = load_preview(root, dataset)
    images = (doc_prev.get("n") or len(doc_prev.get("images", []))) if doc_prev else 0
    est = estimate(cfg, images)
    ahead = sum((estimate(cfg, c["images"]) or {}).get("total_s") or 0 for c in before)
    return {"dataset": dataset, "approved": st["approved"], "stale": st["stale"],
            "counts_itself": counts_itself,
            "queued_n": len(queued), "before_n": len(before),
            # 1-based: the jobs already in the queue, then the approvals ahead of
            # this one, then this one.
            "place": len(queued) + len(before) + 1,
            "after": (queued[-1]["label"] if queued else
                      (before[-1]["dataset"] if before else None)),
            "ahead_s": ahead, "estimate": est}


def plan(cfg: dict, status: dict | None = None) -> dict:
    """The card's next 24 hours as blocks. Held and blocked jobs are NOT bookings.

    "Waiting work adds about 9h 40m" is a number; this is a schedule. The
    question worth answering is "what is this card doing tonight and is there a
    gap", and that used to be mental arithmetic over three estimates.

    Every field read here is declared somewhere: `st["now"]` is now_card()'s
    block, `j["estimate"]` is estimate()'s keys, `j["state"]` is _state_of()'s.
    Nothing reads a bare `elapsed_s` off a job row, because job rows have never
    carried one.
    """
    import time  # noqa: PLC0415

    st = queue_state(cfg, status)
    nowb = st.get("now") or {}
    now_ts, window = time.time(), 86400.0
    blocks, t = [], 0.0
    for j in st["jobs"]:
        if j["hold"] or j["state"]["status"] in ("stop", "you"):
            continue
        est = j["estimate"] or {}
        if j["status"] == "running":
            sweep = (est.get("sweep_s") or 0.0) if j["kind"] == "train" else 0.0
            if nowb.get("eta_s") is not None:
                # the trainer's own tqdm ETA, then the sweep this SAME job owns
                # ("LoRA training, then the epoch sweep" is one queue entry)
                dur, estimated = nowb["eta_s"] + sweep, False
                basis = "from the log: " + (nowb.get("progress_line") or "")
                if sweep:
                    basis += f", then the sweep at {round(sweep / 60)} min"
            elif est.get("total_s") is not None:
                dur = max(0.0, est["total_s"] - (nowb.get("elapsed_s") or 0.0))
                basis, estimated = est.get("basis") or "", True
            else:
                dur, basis, estimated = 0.0, "no progress line and no image count", True
        else:
            dur = est.get("total_s") or 0.0
            basis, estimated = est.get("basis") or "", True
            if not dur:
                # Only `train` jobs carry an estimate, so a prep or assets job
                # has no duration. Say so rather than drawing a 0%-wide block
                # with an empty tooltip: an unknown length is a fact, and
                # silently treating it as zero is what makes a schedule lie.
                basis = f"no measured duration for a {j['kind']} job"
        blocks.append({"id": j["id"], "who": j["who"], "what": j["what"],
                       "status": j["state"]["status"], "start_s": t, "end_s": t + dur,
                       "estimated": estimated, "unknown": not dur, "basis": basis})
        t += dur
    # A held job is not a booking, and neither is one that cannot start. Both are
    # reported separately rather than quietly counted, because counting them is
    # how "busy till Tuesday" becomes wrong.
    held = [j for j in st["jobs"] if j["hold"]]
    blocked = [j for j in st["jobs"]
               if not j["hold"] and j["state"]["status"] in ("stop", "you")]

    def secs(rows):
        return sum((j["estimate"] or {}).get("total_s") or 0 for j in rows)

    free = max(0.0, window - t)
    # A job whose length cannot be derived contributes 0 to the total, so the
    # total is a FLOOR and the page must say so rather than print a time the
    # card will be free. Reporting "frees at 10:14" with a running job of
    # unknown length is the same lie as counting a held job as a booking.
    unknown = [b for b in blocks if b["unknown"]]
    return {"now_ts": now_ts, "window_s": window, "blocks": blocks,
            "unknown_n": len(unknown),
            "booked_s": t, "booked_until_ts": now_ts + t, "free_s": free,
            "held_s": secs(held), "held_n": len(held),
            "blocked_s": secs(blocked), "blocked_n": len(blocked),
            "fits": [{"dataset": c["dataset"], "who": c["who"],
                      "total_s": (c["estimate"] or {}).get("total_s")}
                     for c in candidates(cfg)
                     if 0 < ((c["estimate"] or {}).get("total_s") or 0) <= free][:3]}


def job_log_tail(cfg: dict, job_id: str, lines: int = 60) -> dict:
    """The last N lines of one job's log, decoded by BOM.

    PowerShell's `*>` redirect writes UTF-16, which is why this goes through
    monitor.training.decode_log rather than read_text(): a UTF-16 log read as
    UTF-8 is unreadable noise, and this is the page that replaces "go and open a
    terminal" for a failed run.
    """
    from pathlib import Path as _P  # noqa: PLC0415

    from ..config import outputs_dir  # noqa: PLC0415
    from ..gpu import queue as q  # noqa: PLC0415
    from .training import read_tail  # noqa: PLC0415

    out = outputs_dir(cfg)
    job = q.find(q.load(q.queue_path(out)), job_id)
    if job is None:
        raise KeyError(job_id)
    path = job.get("log")
    found = []
    for cand in ([_P(path)] if path else []) + ([_P(str(path) + ".err")] if path else []):
        if cand.is_file():
            try:
                text = read_tail(cand)   # head+tail, decoded by BOM
            except OSError:
                continue
            found.append({"file": cand.name,
                          "lines": text.splitlines()[-max(1, min(lines, 400)):]})
    return {"id": job_id, "who": character_of(job["label"]).replace("_", " ").title(),
            "status": job["status"], "exit_code": job.get("exit_code"),
            "log": path, "parts": found}


def training_command(cfg: dict, dataset: str) -> list[str]:
    """The one place a training invocation is written. He never types a path."""
    from ..config import ENGINE_ROOT  # noqa: PLC0415

    script = ENGINE_ROOT / "scripts" / "train_character.ps1"
    return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
            "-Ds", dataset, "-Char", character_of(dataset)]


def prep_command(cfg: dict, character: str, *, cap: int = 100,
                 no_base: bool = False) -> list[str]:
    """The one place a prep invocation is written - gather, gaze, caption, preview.

    This exists for the same reason training_command() does, and for one more:
    the prep jobs already in the queue carry an ABSOLUTE path into a Claude
    session's temp directory, because whoever queued them pasted one. A job
    record outlives the session that wrote it, so a queue entry is the last
    place a temp path should appear. Built from ENGINE_ROOT, it cannot.
    """
    from ..config import ENGINE_ROOT  # noqa: PLC0415

    script = ENGINE_ROOT / "scripts" / "character_chain.ps1"
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
           "-Char", character, "-Cap", str(int(cap))]
    if no_base:
        cmd.append("-NoBase")
    return cmd


def queue_router(cfg: dict, status=None):
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
        # The sampler is what makes the `now` block exist. Without it this route
        # returned now=None while a job was plainly running, so the page's Now
        # card read "Nothing is running" directly above a queue row saying
        # "Running now".
        return queue_state(cfg, status() if status else None)

    @router.get("/queue/candidates")
    def candidates_route() -> list[dict]:
        return candidates(cfg)

    @router.get("/queue/sweepable")
    def sweepable_route() -> list[dict]:
        """Trained, but no epoch sweep set exists - so nothing ever asked which
        epoch is hers. Read-only: this build offers no button that starts a
        sweep, because the eval step is launched by train_character.ps1 and
        there is no standalone script to queue."""
        return sweepable(cfg)

    @router.get("/queue/plan")
    def plan_route() -> dict:
        return plan(cfg, status() if status else None)

    @router.get("/queue/position")
    def position_route(dataset: str) -> dict:
        """What approving this dataset would do. Reads only; writes nothing."""
        if not dataset or "/" in dataset or "\\" in dataset or ".." in dataset:
            raise HTTPException(400, "a dataset id is required")
        return position(cfg, dataset)

    @router.get("/queue/job/{job_id}/log")
    def job_log(job_id: str, lines: int = 60) -> dict:
        try:
            return job_log_tail(cfg, job_id, lines)
        except KeyError as exc:
            raise HTTPException(404, f"no job {job_id}") from exc

    @router.post("/queue/runner/start")
    def runner_start() -> dict:
        """Start the runner's scheduled task, in the place you find it stopped.

        Idempotent by construction: the runner itself refuses to start while a
        live runner holds the lease, so a second tap cannot produce a second
        runner. The subprocess timeout here cannot cause GPU work to start - it
        bounds a `schtasks` call only, and on timeout it raises and this route
        500s without having queued or started anything.
        """
        import subprocess  # noqa: PLC0415

        from ..gpu.lease import lease_path, pid_alive, read as read_lease  # noqa: PLC0415
        from ..config import outputs_dir  # noqa: PLC0415

        rec = read_lease(lease_path(outputs_dir(cfg)))
        if rec and pid_alive(int(rec.get("pid", 0))):
            return {"started": False, "why": "a runner is already holding the lease",
                    **queue_state(cfg)}
        try:
            r = subprocess.run(["schtasks", "/Run", "/TN", "SourceMode GPU Runner"],
                               capture_output=True, text=True, timeout=20, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise HTTPException(500, f"could not run schtasks: {exc}") from exc
        if r.returncode != 0:
            raise HTTPException(500, (r.stderr or r.stdout or "schtasks failed").strip())
        return {"started": True, **queue_state(cfg)}

    @router.post("/queue/job/{job_id}/requeue")
    def requeue(job_id: str) -> dict:
        """Put a failed job back, HELD - the same post-condition as restore().

        A one-tap button that starts a seven-hour run is the defect class the
        launcher scripts had. Coming back held means the queue does not move
        until you say so.
        """
        p = path()
        doc = q.load(p)
        job = q.find(doc, job_id)
        if job is None:
            raise HTTPException(404, f"no job {job_id}")
        if job["status"] != "failed":
            raise HTTPException(409, f"{job_id} is {job['status']}, not failed")
        job["status"] = "queued"
        job["hold"] = True
        job["exit_code"] = None
        job["started_at"] = None
        job["ended_at"] = None
        job["note"] = "requeued from the GPU page; held"
        q.save(p, doc)
        return queue_state(cfg)

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

    @router.post("/queue/prep")
    def add_prep(body: dict = Body(default={})) -> dict:
        """Queue the gather/caption/preview chain for one character.

        No approval gate: this chain BUILDS the thing an approval is later given
        to, and it ends at the preview rather than at training. It is still one
        queued job on the one runner, so it cannot run beside anything else.
        """
        char = str(body.get("character", "")).strip()
        if not char or "/" in char or "\\" in char or ".." in char:
            raise HTTPException(400, "a character is required")
        doc = q.load(path())
        dup = q.duplicate_of(doc, "prep", char)
        if dup:
            raise HTTPException(409, f"{char} is already {dup['status']} in the queue")
        job = q.add(doc, kind="prep", label=char,
                    cmd=prep_command(cfg, char, cap=int(body.get("cap") or 100),
                                     no_base=bool(body.get("no_base"))),
                    cwd=str(ENGINE_ROOT),
                    note="queued from the GPU page")
        q.save(path(), doc)
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

    @router.post("/queue/job/{job_id}/restore")
    def restore(job_id: str) -> dict:
        """Put a removed job back, held. Cancelling is soft precisely so this works."""
        p = path()
        doc = q.load(p)
        try:
            q.restore(doc, job_id)
        except KeyError as exc:
            raise HTTPException(404, f"no job {job_id}") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
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
