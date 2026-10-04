"""One bookmarkable page with tabs for the things Jeremy actually does on a phone.

The GPU tab opens first, deliberately: the question on walking up to the box is
"what is it doing and what is next", and judging is something he chooses to do.

`/judge` and `/dataset` are each self-contained pages with their own scripts and
their own use of `location.hash`, so merging them into one document would collide
on both. The hub embeds each in its own frame instead: nothing in either page
changes, they still work standalone, and each frame keeps its own hash.

Both frames stay loaded once visited, so switching tabs does not lose your place
in a 140-image judge set. The tab labels carry live counts - sets left to judge,
training sets left to approve - so the page answers "is there anything for me"
before you tap anything.

    GET  /            the hub
    GET  /hub/counts  {gpu: n needing attention, judge: n unfinished, datasets: n unapproved}
"""

from __future__ import annotations

PAGE = """<!-- review hub -->
<title>SourceMode review</title>
<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>
 html,body{height:100%;margin:0;background:#111;color:#ddd;font:14px system-ui,sans-serif}
 body{display:flex;flex-direction:column}
 #tabs{display:flex;flex:none;border-bottom:1px solid #333;background:#161616;
   padding-top:env(safe-area-inset-top)}
 #tabs button{flex:1;padding:14px 8px;font:inherit;font-size:15px;background:none;border:0;
   color:#888;border-bottom:2px solid transparent;cursor:pointer}
 #tabs button.on{color:#fff;border-bottom-color:#4a9eff;background:#1c1c1c}
 #tabs .n{display:inline-block;min-width:20px;margin-left:6px;padding:1px 6px;border-radius:999px;
   background:#333;color:#ccc;font-size:12px}
 #tabs button.on .n{background:#4a9eff;color:#04203f}
 .pane{flex:1;border:0;width:100%;display:none}
 .pane.on{display:block}
</style>
<div id=tabs>
  <button id=t_gpu class=on onclick="show('gpu')">GPU<span class=n id=n_gpu></span></button>
  <button id=t_judge onclick="show('judge')">Judging<span class=n id=n_judge></span></button>
  <button id=t_datasets onclick="show('datasets')">Training sets<span class=n id=n_datasets></span></button>
</div>
<iframe id=p_gpu class="pane on" src="/queue"></iframe>
<iframe id=p_judge class=pane></iframe>
<iframe id=p_datasets class=pane></iframe>
<script>
const $=id=>document.getElementById(id);
const SRC={gpu:'/queue',judge:'/judge',datasets:'/dataset'};
function show(tab){
  for(const k of Object.keys(SRC)){
    const on=k===tab;
    $('t_'+k).classList.toggle('on',on);
    $('p_'+k).classList.toggle('on',on);
    // load a frame the first time its tab is opened, then leave it alone so
    // switching back keeps its scroll position and whatever set was open
    if(on && !$('p_'+k).src) $('p_'+k).src=SRC[k];
  }
  if(location.hash.slice(1)!==tab) history.replaceState(null,'','#'+tab);
}
async function counts(){
  try{
    const c=await fetch('/hub/counts',{cache:'no-store'}).then(r=>r.json());
    // The GPU badge counts things WAITING ON HIM - paused, blocked, failed, or no
    // runner - never the number of queued jobs, which is never zero and never
    // actionable. A blank badge means there is nothing to do.
    for(const [k,v] of [['gpu',c.gpu],['judge',c.judge],['datasets',c.datasets]])
      $('n_'+k).textContent=v?v:'';
  }catch(e){}
}
show(location.hash.slice(1) in SRC ? location.hash.slice(1) : 'gpu');
counts(); setInterval(counts,30000);
</script>
"""


def hub_router(cfg: dict):
    from fastapi import APIRouter  # noqa: PLC0415
    from fastapi.responses import HTMLResponse  # noqa: PLC0415

    from ..assets.judge import judge_root, list_sets  # noqa: PLC0415
    from ..train.preview import list_previews, preview_root  # noqa: PLC0415

    r = APIRouter()

    @r.get("/", response_class=HTMLResponse)
    def _hub():
        return PAGE

    @r.get("/hub/counts")
    def _counts() -> dict:
        """What is waiting for him, without loading either page."""
        from .queue_page import queue_state  # noqa: PLC0415

        try:
            gpu = queue_state(cfg)["attention"]
        except Exception:  # noqa: BLE001 - a tab badge must never 500 the whole hub
            gpu = 0
        return {"gpu": gpu,
                "judge": sum(1 for s in list_sets(judge_root(cfg)) if not s["done"]),
                "datasets": sum(1 for s in list_previews(preview_root(cfg)) if not s["approved"])}

    return r
