# SourceMode engine

Quickstart (from `engine/`):

1. `uv sync` — base install (Python 3.11). Extras: `--extra gates` (InsightFace QC), `--extra voice` (Chatterbox), `--extra db` (Neon sync).
2. `uv run sourcemode doctor` — check ComfyUI, models, musubi-tuner, gates, GPU, ffmpeg.
3. `uv run sourcemode source show gwen` — inspect a CharacterSource.
4. `uv run sourcemode gates calibrate gwen` — per-character identity threshold (needs `--extra gates`).
5. `uv run sourcemode prompts compile gwen --brief "..."` — brief → scene.yaml with compiled prompts.
6. `uv run sourcemode run gwen --brief "..." --pass draft --dry-run` — full pipeline, no GPU.
7. `uv run sourcemode train wan-cmd gwen --dataset <dir> --expert low` — print the musubi-tuner sequence (`--run` to execute).
8. `uv run sourcemode bootstrap sheet gwen --dry-run` — Qwen-Image-Edit sheet job list.
9. `uv run pytest` — tests (GPU-dependent tests skip cleanly without the extras).
10. Config: `config.toml`, overridable via `SOURCEMODE_*` env vars. Gates annotate, never block — `--no-gate` bypasses everywhere.
