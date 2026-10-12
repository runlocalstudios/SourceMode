# SourceMode

Fully-local pipeline for consistent characters - faces now, video and voices next - on an RTX 5090 with ComfyUI, Qwen-Image LoRAs and Wan 2.2. The only interface is the monitor on `127.0.0.1:8787`. The Next.js/Vercel/Neon web app was retired on 2026-10-11. How it all fits together: [README.md](README.md).

## Stack

- **Engine (`engine/`):** Python 3.11, uv, Typer CLI (`sourcemode`), FastAPI monitor. Talks to a local ComfyUI (default `127.0.0.1:8188`) and musubi-tuner for LoRA training.

## Layout

```
/engine/              Python pipeline (uv project)
/engine/sourcemode/   package: assets, gpu, monitor, train, render, pose, voice, gates, library
/engine/scripts/      eval/ (sweeps, A/Bs, shoots), prep/ (gather, captions), video/
/engine/tests/
/engine/outputs/      pipeline internals (lora-datasets, judge, gpu-queue, logs, game-assets), gitignored
/library/<character>/<date>_<kind>_<name>/   every set he might open again, gitignored
/characters/          appearance.json, wardrobe.json, loras.json (locks), ages.json
/workflows/           ComfyUI API-format workflow JSON templates
/pose-library/        pose reference photos
/imagegen/            OpenAI Images tool, parked
/devresources/        his drop folder, gitignored - keep it
/devassets/           his drop folder, gitignored - keep it
/docs/archive/        the August-era docs, superseded
```

New sets go in the library, never a new top-level `outputs/` folder: `library.find_set(cfg, character, kind, name, create=True)`.

## Invariants

- **Gates are pure scorers, never blocking by default.** They annotate; blocking requires an explicit flag.
- **`characters/*.json` is the single source of truth** for appearance, wardrobe and the locked LoRA.
- **Commercial licenses only:** Wan 2.2 (Apache 2.0), Qwen-Image/Qwen-Image-Edit (Apache 2.0), Z-Image (Apache 2.0), Chatterbox (MIT), Higgs Audio v2 (Apache 2.0). Never Flux dev/Kontext dev, XTTS-v2, F5-TTS, Fish Speech. InsightFace pretrained weights are non-commercial: internal QC tooling only, never shipped in the game.

## Rules

- Git identity in this repo MUST be `Run Local Studios <runlocalstudios@gmail.com>` (repo-local config).
- Secrets never in code or commits. `.env*` is gitignored.
- Scoped `git add` only, never `git add -A`.
- Every GPU-dependent step (ComfyUI, musubi-tuner, InsightFace, Chatterbox) has a `--dry-run` path and is unit-testable without a GPU.
- Windows paths with spaces are quoted everywhere.
- Read-only source repos (never modify): `C:\dev\e2egen`, `C:\Epic Games\Files\cnc info\codex\character-identity-dev`.

## Commands

- Engine: `cd engine && uv run pytest -m "not gpu"` / `uv run sourcemode --help` / `uv run sourcemode doctor`
  - Plain `uv run pytest` also runs the GPU integration tests against a live ComfyUI — never while a training run holds the card.
- Assets (game wardrobe packs, contract from `chillafterdark/docs/character-asset-organization.md`): `assets plan` decides `<category>_<NN>` look identities up front → `assets render --plan` (N shots per look, 2:3, keyable grey background, sidecars carry the slot) → `assets cutout --game` (RGBA WebP + alpha report, annotates never blocks) → `assets place --plan --cutouts` (best per look, named and sorted into `<out>/<char>/outfits/`, mapping sheet, `wardrobePacks.js` line). Nothing writes into the game repo; copy the staged folder yourself.
- Monitor (the whole UI: GPU, Judge, Training sets, Shoots, Characters): `uv run sourcemode monitor serve` (:8787), `uv run sourcemode monitor status` for one JSON sample.
- **GPU work goes through the queue, never straight at the card.** `sourcemode gpu add <kind> <label> [--requires-approval <ds>] -- <command>` appends a job; `gpu list` shows what is running and what is next; `gpu move` reorders; `gpu hold` is the only way the runner skips a job it is waiting on. One runner (`SourceMode GPU Runner` logon task) takes one job at a time **in queue-file order**, waits indefinitely while anything else uses the card, and refuses to start if another runner holds `outputs/gpu-queue/runner.lease`. **No wait anywhere may time out and proceed** - that is how two LoRA trainings ran at once on 2026-10-03. A session asks for work by adding a job; it does not write its own launcher script.
- **Nor does it run heavy work outside the queue at all - CPU included.** Jeremy, 2026-10-04: "don't run anything like that outside the queue again." A `gather_character.py` dry run started by hand burned 5,846 CPU-seconds across every core before it was noticed, because InsightFace on CPU saturates the machine and nothing was managing the process. The queue is not only about the card; it is the one place a long job is visible, estimable and killable. **If a command loads a model - InsightFace, Qwen, a VL pass, Chatterbox - it goes through `gpu add`, whatever hardware it ends up using.** Ad-hoc checks are for things that read files: a source listing answers "what would this gather?" in under a second, and that is what should have been run.
- Always-on: `engine/scripts/register-autostart.ps1` registers ComfyUI, the monitor and the GPU runner as logon tasks (`unregister-autostart.ps1` undoes it). Training logs go in `engine/outputs/training/*.log` so the monitor can track them. PowerShell's `*>` redirect writes UTF-16; the monitor decodes by BOM, but prefer `Start-Process -RedirectStandardOutput` (raw UTF-8) in task scripts.
