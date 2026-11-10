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
| Deepthroat POV | same | "deepthroat: ... all the way inside her mouth and throat, her lips pressed to its base, her nose touching his belly" | **tip only, twice** - text-to-image will not go past the head; "naked from the waist down" did fix his bare thighs. Deep goes through the edit path. | `qwen4play__deep__r2_s0.png` |
| Pants off POV (release) | same | | **failed** - put her sitting in his chair with the penis at her own lap. Release goes through the edit path (`free`). | `qwen4play__release__r2_s0.png` |
| Anal facing him, deep | from above his head | `c0wg1rl, ` + "he lies on his back on the cream wool rug, naked from the waist down, she squats over him facing him, feet planted, knees wide, skirt up, lowered all the way down with his thick erect penis deep inside her anus, her wet vagina fully visible above it, her face to the camera flushed with pleasure, eyes heavy-lidded, lips parted in a soft moan" | **works** - inside her anus, pussy visible above, attached, her face hers (0.52), a moan not a grin | `qwen4play__anal__r2_s0.png` |
| **The rug section as a story section** (`--section q`, rug half, j1370) | from above his head | tip (hand guiding the head in), deep, pleasured (hands on her own breasts), anal tip (hand guiding the head to her anus), anal deep | **5 of 5 first try** (0.47-0.63): inside her, his lower half bare, pussy visible, moans not grins. One continuity miss: anal deep put his white shirt on her, retried once | `library/fiona/2026-11-10_video_office-story/q0*__a1.png` |
| **The desk-squat half** (j1371) | from beside the desk, him lying on the desk | desk tip, desk deep, desk anal deep, desk anal squirt, rug anal squirt | **4 of 6 first try** (0.50-0.66): squatting on the desktop over him, penetration and the squirt stream drawn. Misses: desk tip staged his body oddly under her; desk anal squirt put his white shirt on her again ("shirt on her" in the negative is not enough - say "her torso bare" in the positive). One retry each | `q05_desk_deep__a1.png`, `q09_desk_anal_deep__a1.png`, `q08_rug_anal_squirt__a1.png` |
| Cowgirl facing him, round 2 | same | same wording with "naked from the waist down" and the pleasure expression | **works** again (0.59), moan instead of grin | `qwen4play__cowgirl__r2_s0.png` |
| Her back on the desk tip / anal, pullout, cum | "photographer at the side of the desk level with her hips, her head toward the far end" | `m15510n4ry, ` + ... | **framing failed, acts worked**: the camera went to the foot of the desk looking over her upside-down head every time (0.13-0.18), whatever the wording said. But he is bare below the waist, the tip is at her vagina, the pullout holds his penis above her pussy and the cum shot drew ropes of semen on her stomach and face, not a bucket. | `qwen4play__cum__r3_s0.png`, `qwen4play__pullout__r3_s0.png` |
| Her back on the desk, anal deep, POV | `pov, ` + "close point-of-view photo from the eyes of the man standing at the end of the desk between her raised legs, looking down the length of her body at her, his bare thighs at the bottom of the frame, his face out of frame; she lies on her back on the big walnut desk, her legs spread wide and held up, her face looking up at the camera" | + "skirt up, his thick erect penis deep inside her anus, her wet vagina in full view above it, her face flushed with pleasure, eyes heavy-lidded, lips parted in a soft moan" | **works** - face upright and hers (0.52), inside her anus with her pussy above, stockinged legs up, the office behind her. The desk section's recipe. | `qwen4play__desk_anal_pov__r4_s0.png` |
| The cum shot, POV | same POV framing | + "her hand jerking his thick erect penis held just above her vagina as he ejaculates, ropes of thick white semen landing across her stomach, her breasts and her face, her eyes on the camera, loving it" | **works** - ropes across her stomach and chest, his penis above her pussy, her face hers (0.59); nothing landed on her face | `qwen4play__cum_pov__r4_s0.png` |
| Her back on the desk, anal deep, side view | `m15510n4ry, ` + "picture from the side of the desk, the desk running left to right across the frame: she lies on her back along the desk with her head on the left and her legs raised and spread on the right, her face turned toward the camera; he stands at the right end of the desk between her legs" | same act wording | **works** as the photographer's angle - whole scene, him bare below the waist, her face to the camera (0.34 in near-profile, hers by eye) | `qwen4play__desk_anal_side__r4_s0.png` |
| The cum shot, side view | same side framing | same cum wording | **works** - ropes on her stomach and chest, his penis at her crotch | `qwen4play__cum_side__r4_s0.png` |
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
| spit | "all included" | "She holds his thick erect penis in one hand and spits onto the head of it, a string of saliva running from her lips to the penis, her eyes on the camera. Keep ..." | **works** - a string of saliva from her tongue to the head, playful face, 0.69 | `allin__spit__s0.png` |
| hands (both) | "all included" | "both of her hands wrapped around it one above the other" | **one hand only**, the other stayed on the rug; face 0.67. Retry: "two hands stacked" wording | `allin__hands__s0.png` |
| balls | "all included" | "her other hand cups and gently squeezes his balls" | **balls not drawn**, one hand at the base; face 0.69. Retry: name the balls as visible below the shaft | `allin__balls__s0.png` |
| deepthroat | "all included" | "Deepthroat: ... all the way into her mouth and throat, lips pressed to its base" | **tip only**, and the edit zoomed in on her face (0.41, eyes closed). Neither path has drawn deep yet. Retry: the LoRA's own word `throating` and "half the shaft inside her mouth" | `allin__deep__s0.png` |
| **The chain as a story section** (`office_story.py --section=p`, j1368) | "all included" | topless -> free (realistic size) -> spit, one-hand stroke, two hands, lick, tip (-> suck variants) | **7 of 10 first-try**: topless, free, spit, stroke, two hands, lick, tip all her (0.42-0.69) with the room and pose held through eight edits. Misses: balls (no testicles, third plate try), suck with hands on thighs and suck with two hands both kept one hand on the shaft. Retried once with the hands placed first. | `library/fiona/2026-11-10_video_office-story/p0*__a1.png` |
| balls, hands on thighs, two hands + mouth (retries, j1369) | "all included" | "Add his testicles, visible below the base ...; she holds the penis up with one hand and cups his testicles in the palm of her other hand"; "Move both of her hands onto the tops of his thighs, palms flat ..., no hand touching the penis; the head stays in her mouth"; from the two-hands render: "She keeps both hands stacked on the shaft and lowers her mouth onto it" | **all three work** on the retry (0.44-0.69). Lesson: name the hands' place first, then the mouth; name a missing part as an addition | `p05_balls__a2.png`, `p09_suck_hands_on_legs__a2.png`, `p10_suck_two_hands__a2.png` |
| free, realistic size | "all included" | "His erect penis, proportionate to his body and of realistic size, stands up from between his thighs ..." | **works** - smaller, still big, attached, 0.70; chain later steps from this one | `allin__free2__s0.png` |
| hands, both (round 3) | "all included" | "handjob: two hands - both of her hands grip the shaft of his erect penis, stacked one above the other, the head showing above her top hand ..." | **works**, two hands stacked, 0.71 | `allin__hands2__s0.png` |
| deepthroat (round 3) | "all included" | "throating: half of the shaft inside her mouth ..." | **failed worse**: a second penis head at her lips with his still at his lap, because her face is a foot above his lap in this plate. Round 4: move her down to his lap, and a second start from the text-to-image tip render where her mouth is already on it | `allin__deep2__s0.png` |
| balls (round 3) | "all included" | "cups his balls, which hang visible below the shaft" | **not drawn again** (they are hidden in the plate). Round 4: "testicles", lifting the penis to show them; last try | `allin__balls2__s0.png` |
| balls (round 4) | "all included" | "She holds his erect penis up with one hand so his testicles are visible below it, and cups his testicles in her other hand" | **testicles drawn** below the shaft, 0.70; her hand did not cup them. One more step from this render ("her hand cups his testicles") is the last allowed try | `allin__balls3__s0.png` |
| lick | "all included" | "Her tongue is out, licking the head of his thick erect penis, one hand holding it at the base, her eyes heavy-lidded looking up into the camera" | **works**, 0.63 | `allin__lick__s0.png` |
| deepthroat (round 4) | "all included" | bending her down to his lap; and a second start from the text-to-image tip render | **tip only, both** - six tries across both paths (text x2, edit x4) never went past the head. **Closed**: deep is out of reach of these LoRAs; a dedicated deepthroat LoRA is the only next step | `allin__deep3__s0.png`, `allin__deep_tip__s0.png` |

Edit LoRAs: `nsfw/qedit_mcnl_nsfw.safetensors` (MCNL) and
`nsfw/qedit2511_all_included_v2.safetensors` (act words: fellatio, handjob,
throating, semen, anal). Both spliced after her LoRA at 0.8
(`pov_edit_probe.splice_lora`), as `nsfw_lora_test.py` did.
