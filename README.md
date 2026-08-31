# SourceMode

Source-based asset generation — a fully-local pipeline for professional-grade AI video of consistent characters (consistent faces AND voices) on an RTX 5090 with ComfyUI + Wan 2.2, wrapped in a Next.js control panel on Vercel + Neon Postgres.

- **Web control panel:** repo root (Next.js, App Router). `npm run dev`
- **Pipeline engine:** [`engine/`](engine/README.md) (Python 3.11, uv, Typer). `cd engine && uv run sourcemode --help`
- Conventions and invariants: [CLAUDE.md](CLAUDE.md) · decisions: [DECISIONS.md](DECISIONS.md) · backlog: [BACKLOG.md](BACKLOG.md)

Every route on the deployed site is behind an HTTP Basic Auth preview gate that fails closed (401 until `PREVIEW_PASSWORD` is set to a real value).
