# Story shoot recipes

The combinations that have been proven to render, one per pose, so that story
shoots (office sex story, roommate sex story, ...) can be added to the shot
creator as model + clothing + scene + storyline. Jeremy, 2026-11-10: "When you
have poses and prompts that work I want you to start a list of those
combinations."

A recipe is added only after a render was looked at in full and passed by eye:
her identity (face, hair, body), point of view, physical realism, body-part
accuracy (attached, and inside when it should be), sexiness, surroundings,
perspective and angle. `Status` says how far it got. The proof is a file path.

Every recipe renders with her locked LoRA at 1.0 through Qwen-Image 2512 T2I
(`render.t2i_workflow`), 1024x1536, `render.natural` prompt style:
`<trigger>, <her appearance clause>, <hair>, <shot>. <scene>. Photorealistic,
natural skin texture, sharp focus.` Expressions: pleasure is heavy-lidded eyes,
parted lips and a flushed face. Never tears, watering eyes or a toothy grin
(those are in the negative).

## Act LoRA

| LoRA | File | Strength | Triggers | Verdict |
|---|---|---|---|---|
| QWEN 4 PLAY 2512 v2 (DR34MSC4PE) | `nsfw/qimage2512_qwen4play_v2.safetensors` | 1.0 | `pov`, `bl0wj0b`, `c0wg1rl`, `r3v3rs3_c0wg1rl`, `m15510n4ry`, `d0gg13` first in the prompt | **The one.** Attaches the penis to him and draws penetration (2026-11-10 probe, 4 of 4). Her face holds at 0.44-0.57. |
| + Penis LoRA v2 / pussy-anus v2 | `nsfw/qimage2512_penis_v2.safetensors`, `nsfw/qimage2512_pussy_anus_v2.safetensors` | 0.8 after it | none | More explicit genital detail, but her face drifts (0.40) and the penis balloons. Not used. |
| GNASS (`s3x_2512_qwen`) | `nsfw/qimage2512_gnass.safetensors` | 0.6 | none | Pose and her face fine; the penis floats between her thighs attached to nothing on every contact shot. Retired for acts. |

1.0 on a second LoRA is above the shoot composition cap (0.6); the probe sets
the strength on the act LoRA's node after the graph is built
(`act_lora_probe.workflow`). Carry that into the shot creator deliberately.

## Office sex story (Fiona, 2026-11-10)

Scene: `shoots.OFFICE_IN` (executive office, walnut desk, city at dusk, cream
wool rug). Clothing stages: office desk set outfit -> topless + red pencil mini
skirt + sheer black stockings -> skirt pushed up around her waist. Hair: the
set's one hair (wavy curls). Him: a fit man in a white dress shirt, sleeves
rolled, naked from the waist down once his pants are off.

| Pose | Camera | Wording that worked | Status | Proof |
|---|---|---|---|---|
| Showing off: front, back, topless front, vest open | photographer, 3/4 or waist up | `office_story.py` a01-a07 | works (her LoRA alone, GNASS 0.6 for topless) | `library/fiona/2026-11-10_video_office-story/a01_front__a1.png`, `a05_topless_front__a1.png` |
| Cowgirl facing him, deep | from above his head looking at her | `c0wg1rl, ` + "he lies on his back on the cream wool rug, she squats over his hips facing him with her feet planted flat on the rug either side of him and her knees spread wide, skirt up, lowered all the way down with his thick erect penis deep inside her vagina, her stretched labia fully visible, her face to the camera" | **works** - inside her, attached, her face hers; expression was a grin (fixed to pleasure wording, unproven), his trousers stayed on (fixed to "naked from the waist down", unproven) | `library/fiona/2026-11-10_video_act-lora-probe/qwen4play__cowgirl__s0.png` |
| Blowjob POV, tip | from his eyes, seated in the leather chair, his thighs along the bottom of the frame, his face out of frame | `pov, bl0wj0b, ` + "she kneels on the rug right between his spread knees, close, facing the camera, topless, the head of his thick erect penis between her lips, looking up into the camera" | **works for the tip** - attached, in her lips, her face hers; deep was not achieved with "most of it in her mouth", and tears were drawn when asked for watering eyes (never again) | `library/fiona/2026-11-10_video_act-lora-probe/qwen4play__deep__s0.png` |
| Deepthroat POV | same | "deepthroat: ... all the way inside her mouth and throat, her lips pressed to its base, her nose touching his belly" | round 2 pending (j1360) | |
| Pants off POV (belt, unzip, release) | same, trousers still on for belt/unzip | round 2 pending for release | pending | |
| Anal facing him, deep | from above his head | `c0wg1rl, ` + the cowgirl wording with "deep inside her anus, her wet vagina fully visible above it" | round 2 pending | |
| Her back on the desk, him standing beside it; the finish | photographer beside the desk | | **failed** on GNASS: her head hung off the near edge upside down, the penis floated, the cum shot was a bucket of milk. Needs: camera at the side of the desk with her face upright, QWEN 4 PLAY, cumshot wording | `library/fiona/2026-11-10_video_office-story/e02_desk_deep__a1.png`, `f02_cum__a3.png` |

## Edit path (Qwen-Image-Edit 2511 from an office POV plate) - the POV winner

`pov_edit_probe.py`: a plate from the office POV shoot (her between his knees,
his boxer shorts at the bottom of the frame), her LoRA at 1.0 on the Edit
graph, an NSFW edit LoRA spliced after it at 0.8, `render_pass` medium. Each
step edits the previous step's output, so the face, the room and the pose carry
through untouched. Identity is capped by the plate, and the plate is already
her: this path scores 0.68-0.70 where text-to-image scores 0.44-0.57.

| Step | Edit LoRA | Instruction that worked | Status | Proof |
|---|---|---|---|---|
| topless | MCNL or "all included" | "Remove her blazer and her bra so she is topless with her bare breasts showing, and change her skirt to red. Keep her face, her hair, her pose, the room and the man's legs exactly as they are." | **works**, both LoRAs, 0.70 | `library/fiona/2026-11-10_video_pov-edit-probe/allin__topless__s0.png` |
| free (his shorts gone, her hand on him) | "all included" (`nsfw/qedit2511_all_included_v2.safetensors`); MCNL draws a smoother, less real penis | "Remove the man's navy shorts. His thick erect penis stands up from between his thighs at the bottom of the frame, and she wraps one hand around it, looking up into the camera. Keep her face, her hair, her bare breasts, the room and the man's legs exactly as they are." | **works**, 0.70, attached, same face and room as the plate | `allin__free__s0.png` |
| tip | both | "She leans in and takes just the head of his thick erect penis between her lips, her eyes looking up into the camera. Keep ..." | **works**, lips on the head, hand on the shaft, her face (0.48-0.54, tilted); the penis is oversized on every step - "thick" is enough, never "eight-inch" | `mcnl__tip__s0.png`, `allin__tip__s0.png` |
| deep, hands, spit, balls | "all included" | from `free` | round 2 pending | |

Edit LoRAs: `nsfw/qedit_mcnl_nsfw.safetensors` (MCNL) and
`nsfw/qedit2511_all_included_v2.safetensors` (act words: fellatio, handjob,
throating, semen, anal). Both spliced after her LoRA at 0.8
(`pov_edit_probe.splice_lora`), as `nsfw_lora_test.py` did.
