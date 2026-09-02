# Pose transfer

Takes an existing `*_standing.webp` character asset and produces the same
character, in the same outfit, in a new pose. No character LoRA required —
identity comes from the source image, which is the point for the characters
that don't have one.

## Run it

```
cd C:\dev\sourcemode\engine
uv run sourcemode pose list
uv run sourcemode pose transfer kneeling \
    --assets "C:/dev/chillafterdark/art-source/characters/maya/game-asset-gen/output/weekly_casual"
```

The tooling lives in SourceMode. The game repo holds none of it and is pointed
at with `--assets`, so the dependency runs the right way.

Results are RGBA webp on the source's pixel grid. Copy them into the game repo
yourself once you've reviewed them.

Useful flags:

| flag | effect |
|---|---|
| pose argument | `kneeling`, `kneeling_wide`, `standing_rear`, `standing_rear_glance`, `squat_deep_hands_knees`, `squat_deep_hands_knees_rear`, `squat_deep_hands_floor`, `squat_deep_hands_floor_rear` |
| `--variant arms_behind` | pin one arm variant instead of choosing at random |
| `--candidates 4` | renders per image; the best-scoring one wins |
| `--pattern '*_standing.png'` | which source files to pick up |
| `--limit 3` | how many of them |
| `--hair "two low pigtails"` | **only for tied hairstyles** — see below |
| `--shoes "..."` / `--no-shoes` | override or disable the footwear chosen from the outfit |
| `--dry-run` | show what would run |

`sourcemode pose make-ref <pose>` regenerates a pose's reference photos.

Requires ComfyUI running on 127.0.0.1:8188. About 20 s per candidate, so
~80 s per image at the default of 4.

## How it works

1. The RGBA asset is composited onto a flat grey plate.
2. Qwen-Image-Edit-2511 + the **AnyPose** LoRA pair (base + helper, both 0.7)
   on the 4-step lightning path. `image1` is the character, `image2` is the
   pose reference photo from `pose-library/`.
3. Four candidates are rendered and scored on two axes — how well the skeleton
   matches the reference (`pose_gate.py`, MediaPipe joint angles) and whether
   the wardrobe survived (torso-band colour palette). Weighted 60/40.
4. rembg restores the alpha cutout; the result is rescaled to the source size.

## Adding a new pose

One entry in the `POSES` dict in `engine/sourcemode/pose/library.py`. No new script.

```python
"sitting_floor": {
    "suffix": "sitting_floor",
    "variants": {"hands_behind": "...", "knees_hugged": "..."},
    "ref_prompt":   "camera description first, then the body...",
    "ref_negative": "everything that must not appear",
    # optional extra gates specific to this pose
    "ref_target": {"thigh_angle": 78.0},
    "ref_limits": {"thigh_angle": (60.0, 100.0)},
},
```

Then `sourcemode pose make-ref sitting_floor` renders six candidate references,
measures each, and keeps the best one that passes every gate. Then run it
against a character.

### The four squat poses

Built. `squat_deep_hands_knees`, `squat_deep_hands_knees_rear`,
`squat_deep_hands_floor`, `squat_deep_hands_floor_rear`.

Unlike the kneeling family these are shot **level and straight on**, not from
above, and they are **glamour poses, not exercise photographs**. Both had to be
said explicitly. An overhead camera plus a neutral description produced fitness
stock — a muscular athlete mid-workout under flat gym light — so the negative
now carries `gym, fitness, workout, weightlifting, muscular, bodybuilder,
grimacing, straining` and the prompt asks for a slim, poised figure under soft
glamour lighting. The wardrobe stays plain grey because the real outfit comes
from `image1`; the styling that had to change is posture and lighting.

Depth also had to be described **against the body**, not against geometry.
"Hips below the level of her knees" is true of a shallow-looking gym squat;
"bottom hovering just above her heels, the backs of her thighs folded against
her calves" is something the model can actually see. Nothing is said about
heels — forcing them flat fights the depth.

#### Calibration, and why it is camera-bound

These bands were calibrated twice, because the camera moved. That is the single
most useful thing recorded here:

| metric | from overhead | from eye level |
|---|---|---|
| `squat_depth`, hands on knees | +0.41 … +0.55 | −0.06 … −0.13 |
| `foreshorten` | 0.65 … 0.77 | 1.22 … 1.30 |
| `gaze` | −0.20 … −0.30 | −0.08 … −0.12 |

Same pose, same depth, every number different — one of them inverted. The first
set of bands was written from anatomical intuition ("deep means hips at or below
the knees, so gate at ≤ 0") and **rejected six out of six correct references**,
because from above the knees project lower in frame than the hips. At eye level
the sign is finally the intuitive one. The bands belong to the camera, not to
the pose: move the camera and re-measure.

#### `hand_height`, and the metric that looked right and wasn't

What separates hands-on-knees from hands-on-floor is `hand_height` — wrists
against ankles, in thigh lengths:

| pose | measured |
|---|---|
| hands on knees | 0.77 … 0.91 |
| hands on floor | −0.27 … −0.20 |

A full 1.0 of separation with no overlap, and a test asserts the two bands can
never accept each other's pose.

`torso_bend` was the obvious choice and is **useless** here. Reaching down to
the floor out of a deep squat leaves the shoulder-hip line vertical: it measured
0.2–1.3° in *both* poses, so the plausible band of (10, 55) would have rejected
every correct reference. It was caught only by measuring before trusting it.

### Seven rules, all learned the hard way

1. **Never name a physical object to describe the camera.** "Photograph taken
   from a stepladder" put an actual stepladder in every reference, and AnyPose
   copied it into every output. Say "looking down from above her head height".
2. **State the camera first.** Whatever leads the prompt dominates it. Burying
   the angle at the end produced worm's-eye renders shot from floor level.
3. **Measure the head against SHOULDER WIDTH, not torso.** Shooting from above
   foreshortens the torso while the head keeps its size, so head/torso rises
   with camera height for real perspective reasons. A torso-based gate rejected
   18 out of 18 perfectly good references before this was spotted.
4. **Add a gate for whatever is specific to the pose.** `kneeling_wide` adds a
   thigh-spread angle; the rear poses add `body_facing` and `head_turn`; the
   squats add `squat_depth` and `hand_height`.
   Without one, a reference passes on framing while getting the pose itself wrong.
5. **A pose's `ref_target` REPLACES the base set, it does not merge.** Limits
   calibrated on a kneeling figure are meaningless for a standing one — a
   standing torso measures ~1.8-2.3 against shoulder width where a kneeling one
   measures ~0.8. Merging silently inherited the wrong numbers and rejected 6
   out of 6 good rear references. Declare every gate a pose needs, explicitly.
6. **Every metric measures the PICTURE, not the person — calibrate, never
   assume.** Three metrics have now been set from intuition and all three were
   wrong. `thigh_angle`: a real ~60° kneeling stance measures 76–99 from
   overhead. `squat_depth`: a real deep squat measures **+0.4 to +0.55** from
   above, not negative, because perspective puts the knees lower in frame than
   the hips — and **−0.06 to −0.36** for the same pose at eye level.
   `torso_bend`: the obvious way to detect hands reaching the floor, and it
   reads 0.2–1.3° whether the hands are on the floor or on the knees, because
   the torso stays vertical either way. Each band rejected every correct
   reference. Generate a handful, print the numbers, *then* set the band — and
   where a band separates two poses, generate the other pose too and check the
   clusters actually separate.
7. **A band belongs to a camera, not to a pose.** Moving the squats from an
   overhead to an eye-level camera changed every threshold, one of them in sign.
   Re-measure whenever a `ref_prompt`'s camera changes; a test asserts the squat
   prompts never quietly reintroduce a high angle.

### The metrics

| metric | what it means | typical values |
|---|---|---|
| `head` | ear span / shoulder width — proportions, invariant to camera pitch | source 0.39; bobblehead 0.53 |
| `foreshorten` | torso / shoulder width — camera height | kneeling 0.7-1.0; standing 1.8-2.3 |
| `gaze` | nose vs ear line — chin up or down. Front poses only | 0 level; +ve chin at the ceiling |
| `thigh_angle` | apparent angle between thighs, widened by an overhead camera | knees together 24-28; open 76-99 |
| `torso_bend` | shoulder-hip line off vertical | 0 upright, 90 horizontal |
| `body_facing` | **+1.00 facing camera, −1.00 facing away**, no overlap | derived from anatomical left/right shoulder order flipping |
| `head_turn` | nose offset from ear midpoint, in ear spans | ~0 head square; 1.0-2.5 glancing back |
| `squat_depth` | hips vs knees in thigh lengths, **as projected** | eye level: deep −0.06 to −0.36. Overhead: the same pose reads +0.41 to +0.55 |
| `hand_height` | wrists vs ankles in thigh lengths | hands on floor −0.27 to −0.20; hands on knees 0.77-0.91 |

`body_facing` exists because MediaPipe's `visibility` field is useless for this:
the Tasks API returns 1.0 for every landmark, including a fully turned-away back.

Note that `thigh_angle` is the *apparent* angle from an overhead camera, which
perspective widens — a roughly 60-degree real stance measures 75–95 here. Tune
against what you see, not against the anatomical number.

## Dead ends — don't retry these

- **Plain instruct-editing without AnyPose.** Invented shoes, mangled hands,
  left a dark void at the chest, and smeared a 0.08% teal earring into 0.95%
  cyan patches. AnyPose exists precisely because 2511 lost the pose control
  2509 had.
- **ControlNet img2img via ForgeUI.** At low denoise the pose never moved; at
  high denoise the face became a different person. No denoise value held both,
  because the init image says "standing" while the skeleton says "kneeling" and
  they fight. Would need IP-Adapter FaceID to anchor identity.

## Files

| path | what |
|---|---|
| `pose_transfer.py` | the tool |
| `pose_gate.py` | skeleton comparison, standalone |
| `pose-library/` | reference photos, one per pose+variant |
| `pose-library/_approved_kneeling/` | backup of the signed-off narrow kneel |
| `pose-transfer-review/` | output, for review before it reaches src/assets |
| `.tools/mediapipe-models/` | pose landmarker (30 MB, re-downloadable) |

Note `/art-source/` is gitignored, so none of this is version-controlled. If
you want the tool tracked, it needs a `!art-source/*.py` exception or a move.


## The airbrushed face

Every output has smoother skin than its source. Measured as high-frequency
energy in the face crop, over 24 assets:

| | face texture | vs source |
|---|---|---|
| source asset | 0.1841 | — |
| after the pose pass | 0.1527 | **-17%** |
| after pose + refine | 0.1442 | **-22%** |

Worst cases lose 31-35%, and they are all Sunny — whose sources have the most
texture to lose (freckles). Vivienne's low-texture sources lose almost nothing.
The loss is proportional to how much detail was there, which is the signature of
a resampling/regeneration problem rather than a settings problem.

### What was ruled out, with numbers

**Sampling steps are not the cause.** The obvious suspect was the 4-step
lightning distillation. Running the same asset at `--pass medium` (40 steps, no
lightning, CFG 4.0) changed texture not at all — 0.1581 vs 0.1574 — for roughly
**15x the render time** (440 s vs ~30 s). It does improve face identity
(0.638 -> 0.697), so the option is kept, but it is not the fix for this.

**Resolution is a real but minor cause.** `FluxKontextImageScale` snaps to a
~1MP bucket (832x1248) while the assets are 1.57MP (1023x1537), so ~35% of the
pixels are discarded before the model runs and LANCZOS cannot restore them.
Rendering near native at 1024x1536 recovers only part of it:

| | bucket | native |
|---|---|---|
| workout_03 | -35% | -31% |
| fancy_town_03 | -33% | -27% |

**The remaining ~27-31% is inherent to regenerating the face.** Any pipeline
that redraws the figure through this model will smooth the skin.

### What actually matters

The absolute smoothness may matter less than the MISMATCH. Standing assets never
go through this pipeline, so a crisp standing render sits next to a smooth
kneeling one and the character's skin changes when she kneels. That
inconsistency is what reads as wrong.

Unexplored options, roughly in order of promise:

1. **Frequency-separation transfer** — lift the high-frequency residual from the
   source face and add it back onto the output. Deterministic, no new model, no
   licence. Needs the two faces aligned, which a pose change makes non-trivial.
2. **Match the standing assets to the posed ones** rather than the reverse, so
   the whole cast is consistent. Cheap, and attacks the mismatch rather than the
   smoothness.
3. **A detail-restoring upscaler** (SeedVR2 and similar). Licence needs checking
   before it can touch shipped assets.
4. **Per-character identity LoRA** — a face LoRA carries pores and asymmetry that
   nothing embedding-based preserves.

## Graft-then-heal: how the face is actually kept

The generation-based attempts topped out low, and the sweep showed why: with
geometry in the init latent, identity only transferred above ~0.85 denoise —
exactly where the model also re-framed the crop and turned the head, so every
strong candidate failed the pose gate. Identity import and geometry override
switch on together; no denoise value holds both.

So the dependency is flipped. `--refine` now:

1. **Grafts the real source face onto the posed head** — a landmark affine
   (nose, eyes, mouth; ears excluded, their projection shears with yaw) warps
   the source's actual pixels into place. Pores and freckles come along because
   they are literally the same pixels; no generation pass ever reproduced them.
2. **Heals the crop at moderate denoise** (0.35/0.45/0.55 sweep) — perspective,
   lighting, seams. The heal never has to invent identity, only repair
   geometry, which is the part diffusion is good at here.
3. **Gates every candidate on the full composite** — identity must beat the
   un-refined image by a real margin and pose similarity must hold. The raw
   graft competes too, and the original still wins if nothing beats it.

The graft mask is two-zone, learned in three steps: a generous ellipse carried
backdrop-tinted hair edges in as magenta halos; a skin-only ellipse killed the
halos and the identity with it (forehead and jaw carry face shape). The inner
70% grafts unconditionally, the rim only what passes a strict chroma test, and
kept pixels still tinted toward the backdrop are despilled to their own
luminance.

Measured on the four worst shipped faces:

| | shipped | graft + heal | texture shipped → new (source) |
|---|---|---|---|
| sunny / workout_03 | 0.638 | **0.795** | 0.158 → **0.223** (0.242) |
| sunny / fancy_town_03 | 0.569 | **0.852** | 0.175 → **0.222** (0.260) |
| sunny / casual_date_03 | 0.622 | **0.856** | 0.162 → **0.194** (0.241) |
| vivienne / work_03 | 0.401 | **0.853** | flat-texture source, ~level |

For scale: Gwen's genuine same-person frontal mean was 0.81. These are at or
above it, with the pose gate passing, and the freckles are visibly back.
Remaining known artifact: occasional faint pale wisps at hair tips where
despilled strands meet the feather — small, review-level, not halo-level.

## Facial identity

Immersion is the bar: a character who kneels and reads as a stranger breaks the
scene. Two fixes, both measured, both commercially clean.

### 1. Mask the reference's face (default, free)

The pose reference is **a photograph of a different woman**, and it is handed to
the model as image2 on every single render. Her face competes with the
character's for the whole generation. Nothing in the prompt out-argues an actual
photograph of a different face.

`mask_reference_face()` greys out the inner face of the reference before upload.
Only the inner face — ears, head silhouette and hair edges stay, because the
prompt asks for the reference's head TILT and gaze, and those cues live in the
outline. Mask the whole head and the head angle goes with it.

Gates still measure the ORIGINAL reference: the thresholds were calibrated on a
reference that has a face, and the mask exists for the generator, not the ruler.

Disable with `--no-mask-ref` (A/B only).

### 1b. `--skeleton`: a stick figure as image3 (opt-in, free)

A skeleton is the only pose conditioning with **zero identity** in it — no face,
no hair, no body type, no skin. Rendered from the MediaPipe landmarks already
computed for gating, so no DWPose or ControlNet-aux dependency.

It is passed as **image3 alongside** the masked photo, not instead of it. The
photo carries depth, foreshortening and how a body actually folds; a stick
figure carries none of that, which is precisely why AnyPose exists — its author
built it to skip OpenPose because skeleton conditioning "can still result in
depth being incorrect or the pose not fully matching". 2511 also regressed the
skeleton conditioning 2509 had. Photo for form, skeleton for joints, mask for
identity.

It measured better on both characters, on face *and* pose:

| | face | pose match |
|---|---|---|
| vivienne — masked photo only | 0.458 | 0.938 |
| vivienne — **+ skeleton** | 0.481 | 0.935 |
| sunny — masked photo only | 0.552 | 0.917 |
| sunny — **+ skeleton** | **0.612** | **0.946** |

The skeleton draws no eyes and no mouth — only nose and ears, and only to place
and tilt the head circle. Drawing a face would reintroduce exactly what masking
removed, and a test enforces it.

### 2. `--refine`, second pass (opt-in, ~2x time)

See below. It stacks with masking.

### Measured, two characters, same seed and variant

| | vivienne / work_03 | sunny / casual_date_03 |
|---|---|---|
| as shipped in the batch | 0.373 | 0.378 |
| A — reference face visible | 0.388 | 0.485 |
| B — reference face masked | 0.458 | 0.552 |
| C — masked + refine | 0.534 | 0.565 |
| D — masked + skeleton | 0.481 | 0.612 |
| E — **masked + skeleton + refine** | **0.525** | **0.637** |

For scale: cross-character scores land near 0.27, and a *verified same-person*
off-frontal render scored 0.62 during the original gate calibration. Sunny's
0.637 is at that mark; the shipped batch at 0.378 was not close.

Masking is worth about **+0.07 on both**, for no extra generation time. Refine
adds more on top, and visibly restores the smile and face shape — the batch
renders had neutralised both.

### What was rejected, and why

**InstantID, PuLID, IP-Adapter FaceID** — the usual best-in-class answers, and
all three are built on **InsightFace, whose weights are non-commercial**. This
output ships in the game. Per CLAUDE.md, InsightFace stays QC-only: it scores
which candidate to keep, it never generates a shipped pixel. A test parses
`face.py`'s imports to enforce that.

**Anything Flux-based** (InfiniteYou, PuLID-FLUX) — Flux dev is non-commercial.

Still open, and the strongest remaining option: a **per-character identity
LoRA**. A face LoRA carries texture — pores, asymmetry, freckles — that
embedding methods average away. SourceMode already trains these (musubi-tuner,
Qwen-Image, proven on gwen and bianca), and the AnyPose workflow already has an
unused `LORA_PATH` slot wired for exactly this. It costs a training run per
character.

## `--refine`: a second pass for the face

The pose pass regenerates the whole figure, so the face is redrawn from scratch
every time and drifts from the source. `--refine` adds an opt-in second pass:

- **image1** is the posed result — it pins the pose, body and wardrobe
- **image2** is the original asset — it supplies the face and hair

It runs `qwen_image_edit_ref`, deliberately **not** the AnyPose graph. AnyPose
exists to move a pose and is exactly what must not happen here; a test asserts
its LoRAs can never load in this pass.

**It can decline, and often should.** Candidates are scored on face similarity
to the source, and a candidate is only accepted if it beats the first pass by a
real margin *and* leaves pose similarity within `REFINE_POSE_TOLERANCE`. A pass
that fixes the face while quietly straightening the pose is a regression. With
no scorer available it returns the first-pass image rather than guessing.

Measured on four kneeling results:

| asset | face before | after |
|---|---|---|
| vivienne / work_03 | 0.376 | **0.499** |
| vivienne / fancy_town_03 | 0.440 | **0.555** |
| vivienne / workout_06 | 0.618 | declined |
| sunny / work_08 | 0.551 | declined |

Note what this is and isn't for. It was built to fix hairstyle loss, and that
turned out to be a false alarm (see below) — hair already survives. What it
actually buys is **face identity**, which drifts considerably further than hair
does: a first-pass face at 0.376 similarity is a visibly different person.

InsightFace does the scoring. Its weights are non-commercial, so this stays
tooling: it selects which generated image to keep and never ships inside one.

### Tied hair: a false alarm worth recording

A batch review reported that most tied hairstyles were lost. **That was a
measurement error.** Re-checking all 23 tied-hair assets properly: Sunny 9 of 9
held, Vivienne 13 of 14. Pigtails, buns, braids, clips and a bow all survive a
front-facing kneel.

The bad check cropped a fixed fraction of the FRAME (top 34%). The kneeling
figure sits smaller and lower in frame than the standing source, so that crop
cut the pigtails off entirely, and at thumbnail size they simply were not there
to see. Crop relative to the subject's alpha bounding box, not the frame.

Hair preservation is also **seed-dependent** — the same asset lost its pigtails
in one run and kept them in another. Candidate scoring currently weighs pose and
outfit only, so nothing steers it toward the candidate that kept the hairstyle.
That is the real remaining gap.

## Footwear

These assets are cropped for the game UI, so feet are usually missing or cut
mid-boot. The model then copies whatever the pose reference did — every barefoot
reference produced barefoot results, and zara's half-visible boots became
detached brown blobs once a kneeling pose swung her feet behind her.

Footwear is therefore **chosen from the outfit**, by a plain mapping in
`transfer.py`:

| outfit | footwear |
|---|---|
| `weekly_casual` | clean white low-top sneakers |
| `casual_date` | black platform shoes |
| `work`, `work_alternates`, `work_options` | plain black high-heeled court shoes |
| `fancy_town`, `fancy_dining_gallery` | elegant strappy high-heeled sandals |
| `workout` | clean white athletic running trainers |
| anything else | simple plain flat shoes |

Three things about that table are deliberate.

It is a **mapping, not a model call** — free, and more importantly deterministic,
so one outfit wears the same pair in every pose and every rerun. An outfit whose
shoes change between poses is worse than one wearing the wrong shoes.

**Boots never appear in it.** Boots are only right when the source already shows
them, and that case is handled by preservation instead. A test enforces this.

**`workout` is listed before `work`** and matched longest-first, because `work`
is a substring of `workout` and trainers would otherwise become court shoes.

Anything visible in the source still wins outright — the hint keeps visible
footwear first and only *then* names a pair for feet the source never showed.
`--shoes "..."` overrides the mapping; `--no-shoes` disables the clause entirely
and leaves feet to the source and the reference, exactly as before the feature.

Verified: priya's `work` squat went from bare feet to clean black court heels,
and zara's boots went from shapeless brown masses to structured boots with
visible soles and buckles. The tan reads darker than the source, which is the
remaining rough edge — heavily occluded feet are still the hardest case.

## Rule 8 — never name a thing you want preserved

Naming a specific noun makes the model draw it, regardless of surrounding
grammar. "Photograph taken from a stepladder" (meaning camera position) put a
stepladder in every reference. "If her hair is in a braid, keep the braid"
(meaning don't restyle) put a braid on characters whose hair was loose — the
conditional did nothing, the model just saw the noun.

The same trap runs in reverse in the negative list: putting "braid" there would
strip braids from characters who genuinely have one.

So a preservation instruction may only ASSERT that something is unchanged. It
may never enumerate what that thing might be, in either list.

### The exception: `--hair`

Rule 6 forbids naming a style the model must *guess* about. It does not forbid
telling it something true that it cannot see.

How hair is GATHERED lives on the side a front-facing source never shows, so a
rear view has to invent it — and it always invents the same thing, a single
tail. Maya's two low pigtails came back as one ponytail every time, with the
generic "her hair is unchanged" instruction doing nothing, because the
instruction is only about *not restyling* what is visible.

`--hair "two low pigtails, one on each side, tied at jaw level"` appends a
clause naming the real style and forbidding the observed failure (merging,
regathering, letting it down). Verified on a full rear view, where both tails
have to be visible: single ponytail before, two correct pigtails after.

Two constraints keep it honest:

- **Only pass it when it is true.** It is the stepladder noun with the safety
  off — describing pigtails that aren't there will produce pigtails.
- **It is opt-in.** With no `--hair`, the prompt is byte-identical to the
  un-hinted one, so loose-haired characters cannot regress. That is asserted in
  `test_hair_hint_absent_by_default`.

Loose hair needs nothing. This is only for tied styles.

## Files

| path | what |
|---|---|
| `engine/sourcemode/pose/library.py` | pose definitions and their gates |
| `engine/sourcemode/pose/metrics.py` | landmark measurements |
| `engine/sourcemode/pose/transfer.py` | the pipeline |
| `pose-library/` | reference photos, one per pose+variant |
| `pose-library/_approved_kneeling/` | backup of the signed-off narrow kneel |
| `engine/models/pose_landmarker_heavy.task` | 30 MB, gitignored, re-downloadable |
| `workflows/qwen_image_edit_anypose.json` | the two-image + AnyPose graph |
