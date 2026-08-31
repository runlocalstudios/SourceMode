# SourceMode

Fully-local pipeline for professional-grade AI video of consistent characters — consistent faces AND voices — on an RTX 5090 with ComfyUI + Wan 2.2, wrapped in a Next.js control panel deployed on Vercel with Neon Postgres.

Next.js coding guidance for agents: @AGENTS.md

## Stack

- **Web (repo root):** Next.js 16 (TypeScript, App Router), Vercel (team `runlocalstudios`, project `sourcemode`), Neon Postgres via `@neondatabase/serverless`.
- **Engine (`engine/`):** Python 3.11, uv, Typer CLI (`sourcemode`), Pydantic. Talks to a local ComfyUI (default `127.0.0.1:8188`) and musubi-tuner for Wan 2.2 LoRA training.

## Layout

```
/                     Next.js control panel (App Router)
/engine/              Python pipeline (uv project)
/engine/sourcemode/   package: source, gates, prompts, render, train, bootstrap, voice, orchestrate
/engine/tests/
/engine/evals/        checked-in eval cases
/migrations/          numbered SQL, forward-only, IF NOT EXISTS
/workflows/           ComfyUI API-format workflow JSON templates
/characters/          CharacterSource files + assets (gwen/ ...)
/scripts/             web tooling (migrate.ts)
/devresources/        local-only, gitignored
/devassets/           local-only, gitignored
```

## Invariants

- **Gates are pure scorers, never blocking by default.** A gate is `(asset, source) -> score`; it annotates. Blocking requires an explicit flag; every gate has a `--no-gate` bypass and a config toggle.
- **CharacterSource is the single source of truth.** Every render records `source_version` + `prompt_hash` + settings.
- **Migrations: forward-only, numbered, IF NOT EXISTS.** Never edit a committed migration.
- **Evals live in `engine/evals/`, checked in.**
- **Commercial licenses only:** Wan 2.2 (Apache 2.0), Qwen-Image/Qwen-Image-Edit (Apache 2.0), Z-Image (Apache 2.0), Chatterbox (MIT), Higgs Audio v2 (Apache 2.0). Never Flux dev/Kontext dev, XTTS-v2, F5-TTS, Fish Speech. InsightFace pretrained weights are non-commercial: internal QC tooling only, never shipped in the game.

## Rules

- Git identity in this repo MUST be `Run Local Studios <runlocalstudios@gmail.com>` (repo-local config; Vercel won't deploy otherwise). Vercel CLI commands need `--scope runlocalstudios`.
- Secrets never in code or commits. `.env.local` is gitignored.
- Scoped `git add` only, never `git add -A`.
- Every GPU-dependent step (ComfyUI, musubi-tuner, InsightFace, Chatterbox) has a `--dry-run` path and is unit-testable without a GPU.
- Windows paths with spaces are quoted everywhere.
- Read-only source repos (never modify): `C:\dev\e2egen`, `C:\Epic Games\Files\cnc info\codex\character-identity-dev`.

## Commands

- Web: `npm run dev` / `npm run build` / `npm test` / `npm run migrate`
- Engine: `cd engine && uv run pytest` / `uv run sourcemode --help` / `uv run sourcemode doctor`
