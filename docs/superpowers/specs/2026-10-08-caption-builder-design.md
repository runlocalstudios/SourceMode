# One caption builder with a precedence table

Status: DRAFT for Jeremy's review. Nothing in the pipeline changes until the
table below is confirmed.

## Why

Twelve scripts write training captions today. The prep chain rewrites every
caption five times in sequence (gather, captions, hair confirm, hair recheck,
re-assemble) and the only rule for which value wins is the order the scripts
happen to run in. That is how:

- the re-assemble wrote the plan's braids back over the image-read hair (Nisha);
- the plan's hair was written although Codex had recorded a substitution (Casey);
- a second chain run let hair confirm overwrite the recheck's verdicts (Casey);
- "half pinned back" was written for every image no question matched (Rivera);
- 45 of 69 captions said nothing about hair and the set trained anyway (Gabi).

## What changes

Each image gets one **facts record**. Every script that today writes a caption
writes facts instead. One function, `build_caption(facts)`, turns the record
into the caption, applying the precedence table once. It never invents a value:
an attribute with no fact is left out and flagged on the Training sets page.

Hand edits on the page are stored beside the facts, not inside the caption, so
a rebuild never loses them and they always win.

```
outputs/lora-datasets/<ds>/facts/<image>.json      written by the measuring and asking steps
outputs/lora-datasets/<ds>/overrides.json          Jeremy's edits, per image, per attribute
image_src/<image>.txt                              OUTPUT ONLY - rebuilt from the two above
```

## Sources, from strongest to weakest

| source | what it is | written by |
|---|---|---|
| **hand** | an edit Jeremy made on the Training sets page | the page |
| **measured** | numbers from the image: face box, yaw, pitch, gaze residual, jaw open | gather, gaze |
| **image yes/no** | a binary VL answer to one question about this image ("is her hair in a braid?") | hair confirm, hair recheck, teeth |
| **asked** | what the generator was told to make: the shot plan, plus Codex's recorded substitutions | gather, from the plan and the run record |
| **image described** | a VL free-form or closed-list answer | the caption VL passes |
| *(none)* | nothing above answered | caption omits the clause, page shows a chip |

Each fact carries its source and, for VL answers, the exact question asked, so a
wrong clause can be traced to the question that produced it.

## Precedence, per attribute

| attribute | wins, in order | notes |
|---|---|---|
| hair style | hand > image yes/no > Codex substitution > plan > closed list > omit | a plan clause the image contradicts is recorded as a conflict, never written |
| hair length words | never written | identity trait; bound to the trigger |
| outfit | hand > plan > described > omit | "nothing visible" omits |
| expression | hand > measured mouth-open > described (+ teeth yes/no) > omit | |
| gaze | hand > measured > plan off/away > omit | measured is calibrated to the set's own median |
| setting | hand > plan > described > omit | stated with a preposition, always |
| lighting | hand > plan > described > omit | |
| framing, body angle, head angle | measured only | never from text |
| identity (hair colour, eyes, skin, age, build, freckles, highlights) | never written | rule b: a captioned trait stays variable |

## The chain, after

```
gather   -> facts: measured (geometry), asked (plan + run record), provenance
gaze     -> facts: measured gaze, jaw
ask      -> facts: image described (closed list + clauses), image yes/no (hair, teeth)
assemble -> image_src/*.txt from facts + overrides      ONE step, idempotent
verify   -> every image has a caption; every caption names hair; conflicts listed
preview  -> page shows the caption, the chips, and which source each clause came from
```

Re-running any step only adds or refreshes facts for images that lack them;
`assemble` is the only writer of `.txt` and can be re-run at any time.

## What does not change

- The questions, wordings and thresholds that have measured well (bun 4/4,
  braid 7/7, teeth 12/12, the loose question) are kept verbatim.
- The Training sets page keeps its editor; it writes to `overrides.json` and
  calls assemble for that image.
- Approval fingerprints still cover images + captions, so a rebuild that changes
  a caption still revokes approval.

## Migration

Existing sets keep their current captions. The first `assemble` on an old set
treats the existing `.txt` as **hand** facts for every clause it cannot
reproduce from facts, so nothing already approved changes text.

## Open questions for Jeremy

1. Is the hair order right: **image yes/no > Codex substitution > plan**?
   (The alternative - plan over the image - is what produced Casey's ponytails.)
2. When nothing answers for hair, omit and flag (proposed), or write a generic
   clause? Omitting means the set can reach the page with a hair chip on some
   images; it cannot reach training until they are filled, because verify
   refuses a set past a tenth of captions silent on hair.
3. Should your page edits be per clause (hair, outfit, ...) rather than the whole
   caption, so an edit to the hair survives a later VL re-ask of the outfit?
