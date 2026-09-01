# Pose transfer

Takes an existing `*_standing.webp` character asset and produces the same
character, in the same outfit, in a new pose. No character LoRA required —
identity comes from the source image, which is the point for the characters
that don't have one.

## Run it

```
cd C:\dev\chillafterdark
uv run --project C:/dev/sourcemode/engine python art-source/pose_transfer.py \
    --character maya --pose kneeling --limit 3
```

Results are RGBA webp on the source's pixel grid. Copy them into the game repo
yourself once you've reviewed them.

Useful flags:

| flag | effect |
|---|---|
| `--pose ...` | `kneeling`, `kneeling_wide`, `standing_rear`, `standing_rear_glance` |
| `--variant arms_behind` | pin one arm variant instead of choosing at random |
| `--candidates 4` | renders per image; the best-scoring one wins |
| `--outfits casual_01_standing,bar_02_standing` | specific outfits |
| `--make-ref` | regenerate this pose's reference photos |
| `--dry-run` | show what would run |

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

### Backlog — four squat poses

Not built. Approved for a later session:

| pose | notes |
|---|---|
| `squat_deep_hands_knees` | very deep squat, hands resting on knees, facing camera |
| `squat_deep_hands_knees_rear` | same, seen from behind |
| `squat_deep_hands_floor` | very deep squat, hands down on the floor, facing camera |
| `squat_deep_hands_floor_rear` | same, seen from behind |

The rear pair reuses `body_facing` (≈ −1). What all four still need is a
**squat-depth** gate — none of the existing metrics distinguish a deep squat
from a shallow one. The measurement to add is hip height relative to knee
height, normalised by thigh length: hips at or below the knees is a deep
squat, hips well above them is a half-squat. Without it a reference passes on
framing while standing half way up, which is the same failure the thigh-spread
gate was added to catch.

The front/rear pairs are otherwise cheap, since `standing_rear` already proves
the rear branch works.

### Four rules, all learned the hard way

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
   squats will need a depth measure. Without one, a reference passes on framing
   while getting the pose itself wrong.
5. **A pose's `ref_target` REPLACES the base set, it does not merge.** Limits
   calibrated on a kneeling figure are meaningless for a standing one — a
   standing torso measures ~1.8-2.3 against shoulder width where a kneeling one
   measures ~0.8. Merging silently inherited the wrong numbers and rejected 6
   out of 6 good rear references. Declare every gate a pose needs, explicitly.

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


## Rule 6 — never name a thing you want preserved

Naming a specific noun makes the model draw it, regardless of surrounding
grammar. "Photograph taken from a stepladder" (meaning camera position) put a
stepladder in every reference. "If her hair is in a braid, keep the braid"
(meaning don't restyle) put a braid on characters whose hair was loose — the
conditional did nothing, the model just saw the noun.

The same trap runs in reverse in the negative list: putting "braid" there would
strip braids from characters who genuinely have one.

So a preservation instruction may only ASSERT that something is unchanged. It
may never enumerate what that thing might be, in either list.

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
