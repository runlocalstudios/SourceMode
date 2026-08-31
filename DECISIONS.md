# Decisions

Append-only. Newest first.

## #3 — 2026-08-30: Hybrid image-anchored consistency architecture

Character consistency comes from image LoRA keyframes fed into Wan 2.2 I2V with a low-noise-expert LoRA, not from video-only training. Identity is measured via face embeddings calibrated against the character's own approved sheet (threshold = mean − 2·std of pairwise similarity, floor 0.30) rather than fixed universal thresholds.

## #2 — 2026-08-30: Preview gate fails closed

If `PREVIEW_PASSWORD` is unset, empty, or `CHANGE_ME`, every route returns 401. No page is ever reachable without a real password.

## #1 — 2026-08-30: Single monorepo

Consolidated e2egen (prompt compilation) and character-identity (identity packages) into one monorepo instead of separate repos — one schema, one config, one CLI. Original repos left untouched as fallback.
