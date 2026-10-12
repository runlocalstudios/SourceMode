# SourceMode

A fully local pipeline that makes consistent characters for Chill After Dark:
one LoRA per character on Qwen-Image-2512, trained with musubi-tuner, rendered
through ComfyUI on the RTX 5090. Video (Wan 2.2) and voice (Chatterbox) are next.

There is one interface: the monitor, at **http://127.0.0.1:8787**.

| Tab | What it is for |
|---|---|
| GPU | The queue. Everything heavy runs here, one job at a time, in order. |
| Judge | Blind keep/reject on every set: sweeps, shoots, packs, A/Bs. Your verdicts are the ground truth. |
| Training sets | Each training image beside its caption. Approving a set is what lets it train. |
| Shoots | Pick shoots and packs for a character and queue them as one job. |
| Characters | Appearance, style per outfit type, jobs, hair options, locked LoRA, packs. New characters start here. |

Three logon tasks keep it running: **SourceMode ComfyUI**, **SourceMode Monitor**
and **SourceMode GPU Runner** (`engine/scripts/register-autostart.ps1`).

## A character, start to finish

1. **Gather and caption** - `engine/scripts/character_chain.ps1`, queued:
   gather, gaze, VL captions and hair confirmation, then a preview on the Training sets tab.
2. **Approve** the set on the Training sets tab.
3. **Train** - `engine/scripts/train_character.ps1`, queued. It saves every epoch
   and sweeps the late epochs when it finishes.
4. **Judge the sweep**, and run the tiebreaker set (`--scenes tiebreaker`) if it is close.
5. **Lock the winner** - `sourcemode lora lock <char> --file ... --epoch N`. The lock
   goes into `characters/loras.json` and the file is vaulted in `library/loras/`.
6. **Shoots and packs** from the Shoots tab; judge them; keepers are linked into `kept/`.
   The in-game asset pack needs her 28 looks first: draft, edit and approve them under
   her card on the Characters tab. "Mix your own" on Shoots combines any scene, wardrobe
   (including her job outfit) and pose pack into one shoot.

## Where things are

```
characters/          appearance.json, wardrobe.json, loras.json (the locks), ages.json
library/<character>/<date>_<kind>_<name>/
                     every set you might open again: shoot, selfies, sweep, ab,
                     wardrobe, video, voice. kept/ holds your keepers; set.json says
                     what it is and which judge sets point at it.
library/_experiments/   one-off probes, same naming
library/loras/       the vault of locked LoRAs (prune never touches it)
engine/              the Python engine (uv project, `sourcemode` CLI)
  sourcemode/        assets, gpu, monitor, train, render, pose, voice, gates, library.py
  scripts/eval/      sweeps, A/Bs, shoots, redo - run through the queue
  scripts/prep/      gather, captions, gaze, hair confirmation, previews
  scripts/video/     selfie video and voice experiments
  outputs/           pipeline internals: lora-datasets, judge, gpu-queue, logs,
                     game-assets staging, training
workflows/           ComfyUI API-format templates
pose-library/        pose reference photos (pose transfer)
imagegen/            the OpenAI Images tool, parked
devassets/, devresources/   local drop folders, gitignored
docs/                POSE_TRANSFER.md; archive/ holds the August-era docs
```

## Commands

From `engine/`:

```
uv run sourcemode gpu list                          what is running and what is next
uv run sourcemode gpu add <kind> <label> -- <cmd>   queue work (never run heavy work outside it)
uv run sourcemode train preview <dir> --trigger <name>
uv run sourcemode lora status | verify | lock
uv run sourcemode library plan | apply | prune     file sets by character; delete what a lock made redundant
uv run sourcemode assets plan | render | cutout | place
uv run sourcemode doctor
uv run pytest -m "not gpu"
```

Rules, licenses and conventions are in [CLAUDE.md](CLAUDE.md).
