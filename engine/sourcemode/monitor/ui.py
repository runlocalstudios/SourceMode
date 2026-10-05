"""The one visual language for the four review pages, and the one shared script.

Three pages were built at three different times with three different greys
(`#111`, `#191919`, `#1b1b1b`), three button styles, two hand-drawn "divider
between done and not-done" implementations and two list pickers. Every change
had to be made four times and was usually made once. This is the file that has
to be edited to change any of them.

Concatenated into the pages, never formatted: the pages hold CSS and JS inside
Python strings, so an f-string would eat every brace. Each page is

    PAGE = HEAD + "<style>" + CSS + OWN_CSS + "</style>" + BODY \\
                + "<script>" + SHELL + "</script><script>" + OWN_JS + "</script>"

so `tests/test_page_js.py` node-checks SHELL once per page, and
`tests/test_ui_vocabulary.py` can subtract TOKENS/BASE/PARTS to see only what a
page added for itself. No @import, no CDN, no font file: the system stack is the
only typeface, and it is also the only one that renders instantly with the
internet down.

Two rules are enforced by tests rather than by hope:

- **No page defines a colour.** Every colour is `var(--token)`. A page that needs
  a new one adds it here. That includes page *script* - a theme-colour map holds
  token NAMES and reads them through `SM.token()`.
- **Only PARTS styles a status.** A page may use `.pill you`; only this file may
  say what that looks like.

The breakpoint ladder is four steps and nothing may add a fifth:

    <=440px   4 stat tiles -> 2            a 390pt phone cannot hold four numbers
    <=820px   rows stack, thumb controls   the phone layout
    >=1040px  main + rail                  the first width that fits 760 + 300
    >=1700px  main 860, rail 440           a 2560px monitor, without a 2000px line
"""

from __future__ import annotations

# --------------------------------------------------------------------- tokens ---
# Raw string: the CSS below contains no backslash escapes today, and a raw string
# keeps it that way if one is ever added (a `\2713` would otherwise be a Python
# escape before it was ever a CSS one).
TOKENS = r"""
:root{
  /* ---------- type ---------- */
  --font:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
  --mono:ui-monospace,SFMono-Regular,"Cascadia Mono",Consolas,monospace;
  --t-micro:700 11px/1.3 var(--font);   /* uppercase section labels, tracked */
  --t-small:400 12px/1.4 var(--font);   /* ids, basis strings, timestamps    */
  --t-meta:400 13px/1.45 var(--font);   /* secondary lines, chips            */
  --t-body:400 15px/1.5 var(--font);    /* default                           */
  --t-read:400 15px/1.6 var(--font);    /* PROSE READ WORD BY WORD: captions */
  --t-lead:600 17px/1.35 var(--font);   /* row titles                        */
  --t-title:600 20px/1.25 var(--font);  /* now card headline                 */
  --t-huge:600 26px/1.15 var(--font);   /* stat tile values                  */
  --track:.09em;                        /* the only letter-spacing used      */
  --measure:56ch;                       /* the only max-width for prose      */

  /* ---------- one grey ramp. No page may introduce another. ---------- */
  --g0:#0b0c0e;   /* page ground                                   */
  --g1:#121417;   /* card                                          */
  --g2:#181b1f;   /* raised inside a card: stat tile, caption well */
  --g3:#21252a;   /* hairline                                      */
  --g4:#2c3238;   /* hairline strong, button face                  */
  --g5:#3d454d;   /* button border                                 */
  --g6:#5d676f;   /* disabled ink, drag grip                       */
  --g7:#8c959d;   /* secondary ink  (4.6:1 on --g0)                */
  --g8:#d2d8de;   /* body ink      (12.6:1 on --g0)                */
  --g9:#f3f6f8;   /* headline ink                                  */

  /* The ground behind a photograph. It is NOT --g0: the frame around a
     photograph must not tint it, and a judged face is judged on black. */
  --photo:#000;

  /* ---------- status. One colour means one thing, everywhere. ----------
     live    the card is doing this now
     next    first in order, starts when the card frees
     wait    queued behind something
     you     will not progress until you act
     stop    failed, stalled, paused, down
     done    finished clean
     unknown we cannot read it                                          */
  --live:#4a9eff; --live-ink:#a8d2ff; --live-bg:#12243a; --live-line:#2a5c92;
  --wait:#7b858e; --wait-ink:#b9c1c8; --wait-bg:#191d21; --wait-line:#333a41;
  --you:#f0b429;  --you-ink:#ffd978;  --you-bg:#2b2008;  --you-line:#6b5213;
  --stop:#f2555a; --stop-ink:#ffb0b2; --stop-bg:#2d1114; --stop-line:#7a2a2d;
  --done:#3ddc84; --done-ink:#9fe9bd; --done-bg:#0e2518; --done-line:#246b43;
  --unk:#b388ff;  --unk-ink:#d6c2ff;  --unk-bg:#1f1733;  --unk-line:#5a3f91;

  /* Ink ON a saturated status fill - a tab badge, a plan block. These are the
     three colours a page used to hand-type; they exist so no page has to. */
  --on-live:#06121f; --on-you:#2b2008; --on-stop:#2d1114;

  /* ---------- action. One accent for every primary action, and it is NOT a
     status colour: green here would mean "finished", amber "waiting". ---- */
  --act:#2f6fd0; --act-hi:#3d84ef; --act-ink:#eaf2ff;

  /* ---------- spacing: a 4px grid, seven steps ---------- */
  --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:24px; --s6:32px; --s7:48px;

  /* ---------- radius ---------- */
  --r1:6px; --r2:10px; --r3:14px; --rp:999px;

  /* ---------- elevation (two, both flat enough for OLED) ---------- */
  --e1:0 1px 2px rgba(0,0,0,.5);
  --e2:0 -12px 32px rgba(0,0,0,.55);

  /* ---------- motion. Four durations, one curve. ---------- */
  --m-fast:120ms; --m-base:180ms; --m-sheet:220ms; --m-fade:90ms;
  --ease:cubic-bezier(.2,.7,.2,1);

  /* ---------- touch ---------- */
  --tap:48px;        /* every primary control              */
  --tap-min:44px;    /* floor; nothing smaller is tappable */
  --thumb:84px;      /* the judge verdict circles          */
  --cell:26px;       /* a scene-grid cell                  */
  --safe-b:env(safe-area-inset-bottom,0px);
  --safe-t:env(safe-area-inset-top,0px);
  --nowbar:56px;     /* the hub's bottom bar               */
  --grab:20px;       /* the immersive grab strip           */

  /* ---------- desktop columns (used in grid-template-columns) ---------- */
  --col-main:760px; --col-rail-min:300px; --col-rail-max:400px;
}
"""

# ----------------------------------------------------------------------- base ---
BASE = r"""
*,*::before,*::after{box-sizing:border-box}
html,body{margin:0;background:var(--g0);color:var(--g8);font:var(--t-body);
  -webkit-text-size-adjust:100%}
a{color:var(--live-ink)}
h1,h2,h3{margin:0}
h2{font:var(--t-micro);letter-spacing:var(--track);text-transform:uppercase;
  color:var(--g7);margin:var(--s5) 0 var(--s2)}
h2:first-child{margin-top:0}
code,.mono{font-family:var(--mono);font-size:12px}
hr{border:0;border-top:1px solid var(--g3);margin:var(--s4) 0}

/* one focus ring, visible on every surface, keyboard only */
:focus-visible{outline:2px solid var(--live);outline-offset:2px;border-radius:var(--r1)}

.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);
  white-space:nowrap}
.dim{color:var(--g7)}
.num{font-variant-numeric:tabular-nums}   /* every changing number is tabular */
.trunc{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-thumb{background:var(--g4);border-radius:var(--rp)}
::-webkit-scrollbar-track{background:transparent}

@media (prefers-reduced-motion:reduce){
  *{animation-duration:1ms!important;transition-duration:1ms!important}
}
"""

# ---------------------------------------------------------------------- parts ---
PARTS = r"""
/* ---------------------------------------------------------- status pill ---
   the ONLY element that states a status */
.pill{display:inline-flex;align-items:center;gap:var(--s1);flex:none;
  padding:3px 9px 3px 7px;border-radius:var(--rp);font:var(--t-small);
  font-weight:600;letter-spacing:.01em;border:1px solid;white-space:nowrap}
.pill::before{content:'';width:7px;height:7px;border-radius:50%;background:currentColor}
.pill.live{color:var(--live-ink);background:var(--live-bg);border-color:var(--live-line)}
.pill.next{color:var(--live-ink);background:transparent;border-color:var(--live-line)}
.pill.wait{color:var(--wait-ink);background:var(--wait-bg);border-color:var(--wait-line)}
.pill.you{color:var(--you-ink);background:var(--you-bg);border-color:var(--you-line)}
.pill.stop{color:var(--stop-ink);background:var(--stop-bg);border-color:var(--stop-line)}
.pill.done{color:var(--done-ink);background:var(--done-bg);border-color:var(--done-line)}
.pill.unknown{color:var(--unk-ink);background:var(--unk-bg);border-color:var(--unk-line)}
.pill.live::before{animation:breathe 2.4s var(--ease) infinite}
@keyframes breathe{0%,100%{opacity:1}50%{opacity:.35}}

/* ---------------------------------------------------------- card, banner ---*/
.card{background:var(--g1);border:1px solid var(--g3);border-radius:var(--r2);
  padding:var(--s4);box-shadow:var(--e1)}
.card+.card{margin-top:var(--s2)}
.card-head{display:flex;align-items:flex-start;gap:var(--s3);margin-bottom:var(--s2)}
.card-head h3{font:var(--t-lead);color:var(--g9);flex:1;min-width:0}
.card-sub{font:var(--t-meta);color:var(--g7);margin-top:2px}
.card-foot{display:flex;gap:var(--s2);flex-wrap:wrap;margin-top:var(--s3);
  align-items:center}

/* status-tinted edge. Left edge only: a full tint on a 100-row page is noise. */
.card.e-live{border-left:3px solid var(--live)}
.card.e-you{border-left:3px solid var(--you)}
.card.e-stop{border-left:3px solid var(--stop)}
.card.e-done{border-left:3px solid var(--done)}
.card.e-unknown{border-left:3px solid var(--unk)}

/* an alarm that carries its own repair */
.banner{display:flex;flex-wrap:wrap;align-items:center;gap:var(--s2) var(--s3);
  border-radius:var(--r2);padding:var(--s3) var(--s4);margin-bottom:var(--s3);
  border:1px solid}
.banner b{font-weight:600}
.banner .msg{flex:1;min-width:200px}
.banner .why{display:block;font:var(--t-meta);opacity:.85;margin-top:2px}
.banner.stop{background:var(--stop-bg);border-color:var(--stop-line);color:var(--stop-ink)}
.banner.you{background:var(--you-bg);border-color:var(--you-line);color:var(--you-ink)}
.banner.unknown{background:var(--unk-bg);border-color:var(--unk-line);color:var(--unk-ink)}

/* ---------------------------------------------------------------- buttons ---
   four kinds, and that is the whole set */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:var(--s2);
  min-height:var(--tap-min);padding:0 var(--s4);border-radius:var(--r1);
  font:var(--t-meta);font-weight:600;cursor:pointer;
  background:var(--g4);color:var(--g8);border:1px solid var(--g5);
  transition:background var(--m-fast) var(--ease),transform var(--m-fast) var(--ease);
  -webkit-tap-highlight-color:transparent;touch-action:manipulation;user-select:none}
.btn:active{transform:scale(.98)}
.btn[disabled]{opacity:.35;cursor:default;transform:none}
.btn-primary{background:var(--act);border-color:var(--act-hi);color:var(--act-ink)}
.btn-danger{background:transparent;border-color:var(--stop-line);color:var(--stop-ink)}
.btn-ghost{background:transparent;border-color:var(--g4);color:var(--g7)}
.btn-lg{min-height:var(--tap);font:var(--t-body);font-weight:600;padding:0 var(--s5)}
.btn-sm{min-height:36px;padding:0 var(--s3)}
.btn-wide{width:100%}
.btn-icon{width:var(--tap-min);min-width:var(--tap-min);padding:0;font-size:18px}
@media (hover:hover){
  .btn:hover{background:var(--g5)}
  .btn-primary:hover{background:var(--act-hi)}
  .btn-danger:hover{background:var(--stop-bg)}
  .btn-ghost:hover{background:var(--g2);color:var(--g8)}
}
.btn-row{display:flex;gap:var(--s2);flex-wrap:wrap;align-items:center}
.btn-row .push{margin-left:auto}

/* ------------------------------------------- stat tiles, meter, staleness ---*/
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:var(--s2);margin-top:var(--s3)}
.stat{background:var(--g2);border:1px solid var(--g3);border-radius:var(--r1);
  padding:var(--s2) var(--s3)}
.stat span{display:block;font:var(--t-micro);letter-spacing:var(--track);
  text-transform:uppercase;color:var(--g7)}
.stat b{font:var(--t-huge);font-variant-numeric:tabular-nums;color:var(--g9)}
.stat.unknown b{color:var(--unk-ink)}
@media (max-width:440px){.stats{grid-template-columns:repeat(2,1fr)}}

.meter{height:6px;background:var(--g3);border-radius:var(--rp);overflow:hidden;
  margin-top:var(--s3)}
.meter>i{display:block;height:100%;background:var(--live);
  transition:width var(--m-base) var(--ease)}
.meter.you>i{background:var(--you)}
.meter.done>i{background:var(--done)}
.meter.stop>i{background:var(--stop)}
.meter-thin{height:3px;margin:0}
.meter-hair{height:2px;margin:0;border-radius:0;background:transparent}

/* every live number can say how old it is */
.age{font:var(--t-small);color:var(--g7);font-variant-numeric:tabular-nums}
.stale{color:var(--unk-ink)}
.stale .num,.stale b{text-decoration:underline dotted var(--unk-line) 2px;
  text-underline-offset:3px}

/* -------------------------------------------------------------- job row ---*/
.jrow{display:flex;gap:var(--s3);align-items:flex-start;background:var(--g1);
  border:1px solid var(--g3);border-left-width:3px;border-left-color:var(--g3);
  border-radius:var(--r2);padding:var(--s3);margin-bottom:var(--s2);touch-action:pan-y}
.jrow.e-live{border-left-color:var(--live)}
.jrow.e-you{border-left-color:var(--you)}
.jrow.e-stop{border-left-color:var(--stop)}
.jrow.e-next{border-left-color:var(--live)}
.jrow.dragging{opacity:.4}
.jrow.dropzone{box-shadow:0 0 0 2px var(--live) inset}
.jrow .grip{width:28px;min-width:28px;height:var(--tap-min);display:flex;
  align-items:center;justify-content:center;color:var(--g6);font-size:19px;
  cursor:grab;touch-action:none;user-select:none}
.jrow .grip:active{cursor:grabbing}
.jrow .main{flex:1;min-width:0}
.jrow .title{font:var(--t-lead);color:var(--g9)}
.jrow .title .what{font-weight:400;color:var(--g7)}
.jrow .head{display:flex;gap:var(--s2);align-items:center;flex-wrap:wrap}
.jrow .why,.jrow .est{font:var(--t-meta);color:var(--g8);margin-top:var(--s1)}
.jrow .est b{color:var(--g9);font-variant-numeric:tabular-nums}
.jrow .basis,.jrow .jid{font:var(--t-small);color:var(--g6);margin-top:var(--s1);
  font-family:var(--mono);word-break:break-all}
.jrow .basis.clamp{font-family:inherit;word-break:normal;display:-webkit-box;
  -webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.jrow .acts{margin-top:var(--s3)}

/* --------------------------------------------------------------- plan bar ---*/
.plan{display:flex;height:38px;border-radius:var(--r1);overflow:hidden;
  background:var(--g2);border:1px solid var(--g3);margin-top:var(--s2)}
.plan>button{border:0;padding:0 0 0 6px;min-width:6px;cursor:pointer;position:relative;
  font:var(--t-small);font-weight:600;color:var(--on-live);overflow:hidden;
  text-align:left;white-space:nowrap;border-right:1px solid var(--g0)}
.plan>button:last-child{border-right:0}
.plan .b-live{background:var(--live)}
.plan .b-wait{background:var(--live-line);color:var(--live-ink)}
.plan .b-you{background:var(--you);color:var(--on-you)}
.plan .b-stop{background:var(--stop);color:var(--on-stop)}
.plan .b-free{background:repeating-linear-gradient(135deg,var(--g2),var(--g2) 5px,
  var(--g3) 5px,var(--g3) 10px);color:var(--g7);cursor:default}
.plan-ticks{display:flex;font:var(--t-small);color:var(--g6);margin-top:var(--s1);
  font-variant-numeric:tabular-nums}
.plan-ticks span{flex:1}
.plan-ticks span+span{text-align:center}
.plan-ticks span:last-child{text-align:right}
.plan-line{font:var(--t-body);color:var(--g8);margin-top:var(--s3)}
.plan-line b{color:var(--g9);font-variant-numeric:tabular-nums}

/* ----------------------------------------------------------------- ledger ---
   one row shape for everything that happened */
.ledger{display:flex;flex-direction:column;gap:var(--s1)}
.lrow{display:grid;grid-template-columns:86px 1fr auto;gap:var(--s3);
  align-items:center;padding:var(--s2) var(--s3);background:var(--g1);
  border:1px solid var(--g3);border-radius:var(--r1)}
.lrow .when{font:var(--t-small);color:var(--g7);font-variant-numeric:tabular-nums}
.lrow .what{min-width:0}
.lrow .what b{font:var(--t-body);font-weight:600;color:var(--g9)}
.lrow .what span{display:block;font:var(--t-meta);color:var(--g7)}
@media (max-width:820px){
  .lrow{grid-template-columns:1fr auto;grid-template-areas:"when when" "what act"}
  .lrow .when{grid-area:when}
  .lrow .what{grid-area:what}
  .lrow .act{grid-area:act}
}

/* ------------------------------------------------------------------ chips ---
   grey  a note                   (missing attribute)
   amber look at this             (close call)
   red   a defect that will train (no caption) */
.chips{display:flex;flex-wrap:wrap;gap:var(--s1);margin-top:var(--s2)}
.chip{display:inline-block;padding:3px 9px;border-radius:var(--rp);
  font:var(--t-meta);border:1px solid var(--g4);background:var(--g2);color:var(--g7)}
.chip-you{border-color:var(--you-line);background:var(--you-bg);color:var(--you-ink)}
.chip-stop{border-color:var(--stop-line);background:var(--stop-bg);color:var(--stop-ink);
  font-weight:600;letter-spacing:.02em}
button.chip{min-height:32px;cursor:pointer}

/* ------------------------------------------------- picker trigger + sheet ---
   ONE list pattern for both review pages */
.picker{display:flex;align-items:center;gap:var(--s3);width:100%;
  min-height:var(--tap);padding:0 var(--s3);background:var(--g2);
  border:1px solid var(--g4);border-radius:var(--r1);color:var(--g9);
  font:var(--t-body);font-weight:600;cursor:pointer;text-align:left}
.picker .sub{font:var(--t-meta);font-weight:400;color:var(--g7)}
.chev{margin-left:auto;color:var(--g6);font-size:14px;flex:none}
.picker-txt{min-width:0;flex:1}
.picker-txt>div{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

.scrim{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:40;
  animation:fade var(--m-fast) var(--ease)}
@keyframes fade{from{opacity:0}to{opacity:1}}
.sheet{position:fixed;z-index:41;background:var(--g1);
  border:1px solid var(--g4);box-shadow:var(--e2);display:flex;flex-direction:column;
  left:0;right:0;bottom:0;max-height:86vh;border-radius:var(--r3) var(--r3) 0 0;
  padding-bottom:var(--safe-b);animation:up var(--m-sheet) var(--ease)}
@keyframes up{from{transform:translateY(14px);opacity:.6}to{transform:none;opacity:1}}
.sheet-head{display:flex;align-items:center;gap:var(--s2);padding:var(--s3);
  border-bottom:1px solid var(--g3);flex:none}
.sheet-head h3{font:var(--t-lead);color:var(--g9);flex:1}
.sheet input[type=search]{width:100%;min-height:var(--tap-min);padding:0 var(--s3);
  background:var(--g2);border:1px solid var(--g4);border-radius:var(--r1);
  color:var(--g9);font:var(--t-body);-webkit-appearance:none}
.sheet-filter{padding:var(--s2) var(--s3);flex:none;border-bottom:1px solid var(--g3)}
.sheet-list{overflow:auto;-webkit-overflow-scrolling:touch;padding:var(--s2) 0 var(--s4)}
.sheet-group{font:var(--t-micro);letter-spacing:var(--track);text-transform:uppercase;
  color:var(--g7);padding:var(--s3) var(--s4) var(--s1);position:sticky;top:0;
  background:var(--g1)}
.sitem{display:flex;align-items:center;gap:var(--s3);width:100%;min-height:56px;
  padding:var(--s2) var(--s4);background:none;border:0;border-bottom:1px solid var(--g3);
  color:var(--g8);font:var(--t-body);text-align:left;cursor:pointer}
.sitem:active{background:var(--g2)}
.sitem.on{background:var(--g2);box-shadow:3px 0 0 var(--act) inset}
.sitem .txt{flex:1;min-width:0}
.sitem .txt b{display:block;font-weight:600;color:var(--g9);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.sitem .txt span{display:block;font:var(--t-meta);color:var(--g7)}
.sitem .meter{margin-top:var(--s1)}
@media (min-width:821px){
  .sheet{right:auto;top:0;bottom:0;width:420px;max-height:none;
    border-radius:0 var(--r3) var(--r3) 0;animation:slide var(--m-sheet) var(--ease)}
  @keyframes slide{from{transform:translateX(-16px);opacity:.6}to{transform:none;opacity:1}}
}

/* ---------------------------------------------------- caption typography ---
   A caption is a string read character by character. It gets a measure, a
   reading size and a 1.6 line height; it is not a label and not a number. */
.cap{font:var(--t-read);max-width:var(--measure)}
.cap-box{display:block;width:100%;max-width:var(--measure);text-align:left;
  white-space:pre-wrap;overflow-wrap:anywhere;font:var(--t-read);
  font-family:var(--font);color:var(--g8);background:var(--g2);
  border:1px solid var(--g3);border-radius:var(--r1);padding:var(--s3);
  min-height:var(--tap-min);cursor:text}
.cap-box:active{border-color:var(--g5)}
.cap-box.empty{color:var(--g6);font-style:italic}
.editor{margin-top:var(--s2);max-width:var(--measure)}
.editor textarea{width:100%;min-height:132px;background:var(--g2);color:var(--g9);
  border:1px solid var(--act-hi);border-radius:var(--r1);padding:var(--s3);
  font:16px/1.6 var(--font);resize:vertical}

/* ----------------------------------------------------------------- layout ---
   phone first, then the monitor */
.wrap{padding:var(--s3) var(--s3) var(--s7)}
.col-main{min-width:0}
@media (min-width:1040px){
  /* Not a 400px column centred in 2560px, and not a 2000px line length either:
     a working column with a real measure plus a rail for what you glance at. */
  .wrap{display:grid;gap:0 var(--s5);padding:var(--s5) var(--s6) var(--s7);
    grid-template-columns:minmax(0,var(--col-main))
                          minmax(var(--col-rail-min),var(--col-rail-max));
    grid-template-areas:"main rail";justify-content:center}
  .col-main{grid-area:main}
  .col-rail{grid-area:rail;position:sticky;top:var(--s5);align-self:start;
    max-height:calc(100vh - var(--s6));overflow:auto}
}
@media (min-width:1700px){
  .wrap{--col-main:860px;--col-rail-min:340px;--col-rail-max:440px}
}

/* ------------------------------------------------------------------ toast ---*/
.toast{position:fixed;left:50%;z-index:50;
  bottom:calc(var(--thumb) + var(--s5) + var(--safe-b));
  display:flex;align-items:center;gap:var(--s3);
  padding:0 var(--s2) 0 var(--s4);min-height:var(--tap);
  background:var(--g2);border:1px solid var(--g5);border-radius:var(--rp);
  color:var(--g8);font:var(--t-body);box-shadow:0 8px 24px rgba(0,0,0,.5);
  transform:translate(-50%,12px);opacity:0;pointer-events:none;
  transition:opacity var(--m-base) var(--ease),transform var(--m-base) var(--ease)}
.toast.on{opacity:1;transform:translate(-50%,0);pointer-events:auto}
.toast .w{color:var(--g7)}
@media (min-width:821px){.toast{bottom:calc(var(--s5) + var(--safe-b))}}

/* ------------------------------------------------ epoch board, scene grid ---*/
.board{display:flex;flex-direction:column;gap:0}
.arow{display:grid;grid-template-columns:4.6em 1fr 3.4em 3.6em;gap:var(--s3);
  align-items:center;padding:var(--s2) 0;font:var(--t-meta)}
.arow+.arow{border-top:1px solid var(--g3)}
.arow .ep{font:var(--t-body);font-weight:600;color:var(--g9);
  font-variant-numeric:tabular-nums}
.arow .track{height:12px;background:var(--g2);border:1px solid var(--g3);
  border-radius:var(--rp);overflow:hidden}
.arow .track>i{display:block;height:100%;background:var(--live);
  transition:width var(--m-base) var(--ease)}
.arow.lead .track>i{background:var(--done)}
.arow .rate,.arow .low{text-align:right;font-variant-numeric:tabular-nums;color:var(--g8)}
.arow .low{color:var(--g9);font-weight:600}
.arow .note{grid-column:1/-1;font:var(--t-small);color:var(--g7);margin-top:2px}
.arow.lead .note{color:var(--done-ink)}
@media (max-width:440px){.arow{grid-template-columns:3.4em 1fr 3em 3.2em;gap:var(--s2)}}

/* the cross-tab: same seed down each column */
.gwrap{overflow-x:auto;-webkit-overflow-scrolling:touch;margin-top:var(--s2)}
.sgrid{border-collapse:collapse;font:var(--t-small);font-variant-numeric:tabular-nums}
.sgrid th,.sgrid td{width:var(--cell);height:var(--cell);min-width:var(--cell);
  text-align:center;padding:0;border:1px solid var(--g3);color:var(--g7)}
.sgrid th[scope=row]{width:3.4em;min-width:3.4em;text-align:right;
  padding-right:var(--s2);border:0;color:var(--g8);font-weight:600}
.sgrid td.k{color:var(--done-ink);background:var(--done-bg)}
.sgrid td.r{color:var(--stop-ink);background:var(--stop-bg)}
.sgrid td.u{color:var(--g6)}
.sgrid tr.lead th[scope=row]{color:var(--g9)}
.sgrid tr.lead td{border-top-color:var(--g5);border-bottom-color:var(--g5)}

/* --------------------------------------------------- action bar, fix bar ---
   the primary label states the consequence */
.actbar{position:fixed;left:var(--s2);right:var(--s2);
  bottom:calc(var(--s2) + var(--safe-b));z-index:30;
  background:var(--g1);border:1px solid var(--g4);border-radius:var(--r2);
  box-shadow:var(--e2);padding:var(--s2);display:flex;gap:var(--s2);
  align-items:center;flex-wrap:wrap}
.actbar .btn-primary{flex:1;min-width:0;min-height:var(--tap);
  font:var(--t-body);font-weight:600}
.actbar .chips{margin:0;flex:none}
.actbar .over{flex-basis:100%;font:var(--t-small);color:var(--you-ink)}
/* On a monitor the rail is already always visible, so nothing needs to float. */
@media (min-width:1040px){
  .actbar{position:static;left:auto;right:auto;bottom:auto;box-shadow:var(--e1);
    margin-bottom:var(--s2)}
}
.fixbar{position:fixed;left:var(--s2);right:var(--s2);
  bottom:calc(var(--s2) + var(--safe-b));z-index:31;
  background:var(--g1);border:1px solid var(--you-line);border-radius:var(--r2);
  box-shadow:var(--e2);padding:var(--s2) var(--s3);display:flex;
  align-items:center;gap:var(--s2)}
.fixbar .lbl{flex:1;min-width:0;font:var(--t-meta)}
.fixbar .lbl b{display:block;font:var(--t-body);font-weight:600;color:var(--g9)}
.fixbar .lbl span{color:var(--you-ink)}
.fixbar.done{border-color:var(--done-line)}
@media (min-width:1040px){.fixbar{left:auto;right:var(--s5);width:520px}}

/* ------------------------- findings, bars, facts, empty/error/loading, kbd ---*/
.findings{display:flex;flex-direction:column;gap:var(--s1)}
.finding{display:flex;gap:var(--s2);font:var(--t-meta);max-width:var(--measure)}
.finding .mark{flex:none;width:14px;text-align:center;font-weight:700}
.finding.pass .mark{color:var(--done)}
.finding.pass{color:var(--g7)}
.finding.fail .mark{color:var(--you)}
.finding.fail{color:var(--g8)}
details.report{background:var(--g1);border:1px solid var(--g3);border-radius:var(--r1);
  padding:var(--s2) var(--s3);margin:var(--s2) 0}
details.report>summary{cursor:pointer;list-style:none;font:var(--t-meta);color:var(--g7);
  min-height:var(--tap-min);display:flex;align-items:center}
details.report>summary::-webkit-details-marker{display:none}
details.report>summary::before{content:'\25B8\00a0';color:var(--g6)}
details.report[open]>summary::before{content:'\25BE\00a0'}

/* facts: a number that is also a filter */
.facts{display:flex;flex-wrap:wrap;gap:var(--s2);margin-top:var(--s3)}
.fact{display:inline-flex;align-items:center;gap:var(--s2);min-height:var(--tap-min);
  padding:0 var(--s3);border-radius:var(--r1);background:var(--g2);
  border:1px solid var(--g4);color:var(--g8);font:var(--t-meta);cursor:pointer}
.fact b{color:var(--g9);font-variant-numeric:tabular-nums}
.fact.on{border-color:var(--act);background:var(--live-bg);color:var(--g9)}
.fact.flag{border-color:var(--you-line);color:var(--you-ink)}
.fact.inert{cursor:default}

.bars{display:flex;flex-direction:column;gap:var(--s2);margin:var(--s4) 0}
.bar{display:grid;grid-template-columns:110px 1fr 92px;gap:var(--s3);align-items:center}
.bar .lab{font:var(--t-meta);color:var(--g8);font-variant-numeric:tabular-nums}
.bar .track{height:14px;background:var(--g2);border:1px solid var(--g3);
  border-radius:var(--r1);overflow:hidden}
.bar .track>i{display:block;height:100%;background:var(--live);
  transition:width var(--m-base) var(--ease)}
.bar.lead .track>i{background:var(--done)}
.bar .val{font:var(--t-meta);color:var(--g9);text-align:right;
  font-variant-numeric:tabular-nums}
@media (max-width:440px){.bar{grid-template-columns:84px 1fr 72px;gap:var(--s2)}}

.empty,.errbox{text-align:center;padding:var(--s6) var(--s4);border-radius:var(--r2);
  border:1px dashed var(--g4);color:var(--g7);background:var(--g1)}
.empty b,.errbox b{display:block;font:var(--t-lead);color:var(--g9);margin-bottom:var(--s2)}
.errbox{border-style:solid;border-color:var(--stop-line);background:var(--stop-bg);
  color:var(--stop-ink)}
.errbox .btn-row{justify-content:center;margin-top:var(--s4)}
/* First paint is the shape of the answer, not the word "loading". */
.skel{background:linear-gradient(90deg,var(--g1),var(--g2),var(--g1));
  background-size:200% 100%;animation:shim 1.1s linear infinite;border-radius:var(--r2);
  color:transparent}
@keyframes shim{to{background-position:-200% 0}}

.keys{display:none;gap:var(--s3);font:var(--t-small);color:var(--g7)}
kbd{font-family:var(--mono);font-size:11px;background:var(--g2);border:1px solid var(--g5);
  border-bottom-width:2px;border-radius:4px;padding:1px 5px;color:var(--g8)}
@media (min-width:821px) and (hover:hover){.keys{display:flex}}
"""

CSS = TOKENS + BASE + PARTS

# ---------------------------------------------------------------------- shell ---
# House rules, all three learned the hard way in this repo: no raw newlines in
# string literals (use SM.NL), no backslash escapes in JS strings, and nothing
# that needs doubling inside the Python string that holds it.
SHELL = r"""
const SM=(function(){
 const NL=String.fromCharCode(10);
 const ESC={'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'};
 const esc=s=>String(s==null?'':s).replace(/[<>&"']/g,c=>ESC[c]);

 /* ---- the status vocabulary. Nothing else may name a status. ---- */
 const STATUS={
   live:{word:'Running'}, next:{word:'Next up'}, wait:{word:'Waiting'},
   you:{word:'Needs you'}, stop:{word:'Stopped'}, done:{word:'Done'},
   unknown:{word:'Unknown'}};
 const RANK={stop:5,you:4,unknown:3,live:2,next:1,wait:0,done:0};
 const worst=list=>list.reduce((a,b)=>(RANK[b]||0)>(RANK[a]||0)?b:a,'done');
 function pill(status,word){
   const s=STATUS[status]?status:'unknown';
   return '<span class="pill '+s+'">'+esc(word||STATUS[s].word)+'</span>';
 }
 /* a token's colour, read from the stylesheet rather than retyped in JS -
    this is why no page holds a hex literal, in CSS or in script */
 const token=n=>getComputedStyle(document.documentElement)
   .getPropertyValue('--'+n).trim();

 /* ---- formatters ---- */
 const pad=n=>(n<10?'0':'')+n;
 const dur=s=>{ if(s==null) return '';
   s=Math.round(s); const h=Math.floor(s/3600), m=Math.floor(s%3600/60);
   return h?(h+'h '+pad(m)+'m'):(m?(m+'m'):(s+'s')); };
 const clock=ts=>{ const d=new Date(ts*1000);
   return pad(d.getHours())+':'+pad(d.getMinutes()); };
 const ago=v=>{ if(!v) return '';
   const t=typeof v==='number'?v*1000:new Date(v).getTime();
   const d=Math.max(0,(Date.now()-t)/1000);
   if(d<90) return 'just now';
   if(d<3600) return Math.round(d/60)+' minutes ago';
   if(d<86400) return Math.round(d/3600)+' hours ago';
   const n=Math.round(d/86400); return n+(n===1?' day ago':' days ago'); };
 const pct=f=>f==null?'':Math.round(f*100)+'%';

 /* ---- fetch that never lets a dead poll look like fresh data ---- */
 let lastOk=Date.now(), failures=0, onStale=null;
 async function getJSON(url){
   const r=await fetch(url,{cache:'no-store'});
   if(!r.ok) throw new Error('HTTP '+r.status+' from '+url);
   const j=await r.json(); lastOk=Date.now(); failures=0;
   if(onStale) onStale(0,null);
   return j;
 }
 async function postJSON(url,body){
   const r=await fetch(url,{method:'POST',headers:{'content-type':'application/json'},
     body:body===undefined?undefined:JSON.stringify(body)});
   const j=await r.json().catch(()=>({}));
   if(!r.ok) throw new Error(j.detail||('HTTP '+r.status));
   return j;
 }
 /* A poll loop that reports its own health instead of silently stopping, and
    that pauses while this frame is hidden. It backs off on failure and never
    gives up; nothing here is a deadline after which anything may proceed. */
 function poll(ms,fn){
   let stopped=false, awake=true, timer=null;
   const tick=async()=>{
     if(stopped) return;
     if(!awake){ timer=setTimeout(tick,ms); return; }
     try{ await fn(); }
     catch(e){ failures++;
       if(onStale) onStale(Math.round((Date.now()-lastOk)/1000),e.message); }
     if(!stopped) timer=setTimeout(tick,ms*Math.min(4,1+failures));
   };
   const wake=on=>{ awake=on; if(on){ clearTimeout(timer); tick(); } };
   on('shown',()=>wake(true)); on('hidden',()=>wake(false));
   document.addEventListener('visibilitychange',
     ()=>wake(document.visibilityState==='visible'));
   tick();
   return {stop(){stopped=true;clearTimeout(timer);},wake};
 }
 const staleHandler=fn=>{onStale=fn;};
 const ageOf=()=>Math.round((Date.now()-lastOk)/1000);

 /* ---- keyed list patch: no innerHTML on a live list ---- */
 function patch(host,items,keyOf,render){
   const have=new Map();
   for(const el of [...host.children]) have.set(el.dataset.k,el);
   const want=[];
   for(const it of items){
     const k=String(keyOf(it));
     let el=have.get(k);
     if(el){ have.delete(k); } else { el=document.createElement('div'); el.dataset.k=k; }
     if(el.dataset.locked!=='1') render(el,it);
     want.push(el);
   }
   for(const el of have.values()) el.remove();
   want.forEach((el,i)=>{
     if(host.children[i]!==el) host.insertBefore(el,host.children[i]||null); });
 }
 /* write HTML only when it changed: no reflow, no selection loss */
 function set(el,sel,html){
   const t=sel?el.querySelector(sel):el; if(!t) return;
   if(t.innerHTML!==html) t.innerHTML=html;
 }

 /* ---- the one picker ---- */
 const GROUPS=[['needs','Needs you'],['progress','In progress'],['done','Done']];
 function sheet(opts){
   /* opts: {title, items:[{id,title,sub,status,progress,group}], current, onPick} */
   const scrim=document.createElement('div'); scrim.className='scrim';
   const box=document.createElement('div'); box.className='sheet';
   box.setAttribute('role','dialog'); box.setAttribute('aria-modal','true');
   const close=()=>{scrim.remove();box.remove();
     document.removeEventListener('keydown',key);};
   const key=e=>{ if(e.key==='Escape') close(); };
   box.innerHTML='<div class=sheet-head><h3>'+esc(opts.title)+'</h3>'
     +'<button class="btn btn-ghost btn-icon" aria-label="close">&#10005;</button></div>'
     +'<div class=sheet-filter><input type=search placeholder="Filter" '
     +'autocomplete=off autocorrect=off spellcheck=false></div>'
     +'<div class=sheet-list></div>';
   const list=box.querySelector('.sheet-list'), find=box.querySelector('input');
   const paint=()=>{
     const q=find.value.trim().toLowerCase();
     const rows=opts.items.filter(s=>!q
       ||(s.title+' '+(s.sub||'')).toLowerCase().includes(q));
     let h='';
     for(const g of GROUPS){
       const inG=rows.filter(s=>s.group===g[0]);
       if(!inG.length) continue;
       h+='<div class=sheet-group>'+g[1]+' &middot; '+inG.length+'</div>';
       for(const s of inG){
         h+='<button class="sitem'+(s.id===opts.current?' on':'')
           +'" data-id="'+esc(s.id)+'">'
           +'<span class=txt><b>'+esc(s.title)+'</b><span>'+esc(s.sub||'')+'</span>'
           +(s.progress==null?'':'<span class="meter meter-thin"><i style="width:'
              +Math.round(s.progress*100)+'%"></i></span>')
           +'</span>'+pill(s.status)+'</button>';
       }
     }
     list.innerHTML=h
       ||'<div class=empty><b>Nothing matches</b>Clear the filter to see them all.</div>';
   };
   find.addEventListener('input',paint);
   list.addEventListener('click',e=>{
     const b=e.target.closest('.sitem'); if(!b) return;
     close(); opts.onPick(b.dataset.id);
   });
   box.querySelector('.sheet-head .btn').addEventListener('click',close);
   scrim.addEventListener('click',close);
   document.addEventListener('keydown',key);
   document.body.append(scrim,box); paint();
   /* a keyboard only where there is a pointer: a phone gets no surprise keyboard */
   if(window.matchMedia('(hover:hover)').matches) find.focus();
   return close;
 }

 /* ---- toast, with one optional action ---- */
 let toastT=null, toastEl=null;
 function toast(word,action){
   if(!toastEl){ toastEl=document.createElement('div');
     toastEl.className='toast'; toastEl.setAttribute('role','status');
     toastEl.setAttribute('aria-live','polite'); document.body.append(toastEl); }
   toastEl.innerHTML='<span class=w>'+esc(word)+'</span>'
     +(action?'<button class="btn btn-sm">'+esc(action.label)+'</button>':'');
   if(action) toastEl.querySelector('.btn').onclick=()=>{hideToast();action.run();};
   toastEl.classList.add('on');
   clearTimeout(toastT); toastT=setTimeout(hideToast,4000);
 }
 function hideToast(){ if(toastEl) toastEl.classList.remove('on'); }

 /* ---- the versioned frame protocol (v1) ---- */
 const standalone=()=>window.parent===window;
 const handlers={};
 function post(msg){
   if(standalone()) return;
   try{ parent.postMessage(Object.assign({sm:1},msg),location.origin); }catch(e){}
 }
 function on(t,fn){ (handlers[t]=handlers[t]||[]).push(fn); }
 window.addEventListener('message',e=>{
   if(e.origin!==location.origin) return;
   const m=e.data; if(!m||m.sm!==1) return;   /* a stale cached frame is ignorable */
   for(const fn of (handlers[m.t]||[])) fn(m);
 });
 const nav=(tab,ref)=>{
   if(standalone()){
     location.href='/'+(tab==='gpu'?'queue':tab)+(ref?'#'+ref:''); return; }
   post({t:'go',tab:tab,ref:ref||null});
 };
 const ctx=p=>post(Object.assign({t:'ctx'},p));
 const chrome=mode=>post({t:'chrome',mode:mode});
 const recount=()=>post({t:'counts'});

 return {NL,esc,pill,STATUS,worst,token,dur,clock,ago,pct,getJSON,postJSON,poll,
         staleHandler,ageOf,patch,set,sheet,toast,hideToast,
         post,on,nav,ctx,chrome,recount,standalone};
})();
"""


def page(title: str, body: str, script: str, own_css: str = "", head: str = "",
         *, viewport: str = "width=device-width,initial-scale=1,viewport-fit=cover") -> str:
    """Assemble a page the one way every page is assembled.

    Two script tags, both of which `test_page_js.py` parses: the shared shell and
    the page's own. `own_css` goes last so a page can only ever add to the system,
    never reorder it.

    `head` is for a meta a page genuinely needs and nothing else does - the hub's
    `theme-color`. Note that it may hold no colour either: a `content="#0b0c0e"`
    is a quoted hex literal, which is exactly what the vocabulary test forbids,
    so the hub ships the tag empty and fills it from `SM.token()` on load.
    """
    return ("<!-- " + title + " -->"
            "<title>" + title + "</title>"
            '<meta name=viewport content="' + viewport + '">'
            + head
            + "<style>" + CSS + own_css + "</style>"
            + body
            + "<script>" + SHELL + "</script>"
            + "<script>" + script + "</script>")
