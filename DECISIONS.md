# Decisions

Append-only. Newest first.

## #7 — 2026-08-30: Identity-gate embedding backend = InsightFace buffalo_l (CPU provider)

Option (a) from the backend ladder won on the first try: `insightface` + `onnxruntime-gpu` import and run in the engine venv (CUDA EP doesn't register there, CPU EP is fast enough for QC — see BACKLOG). `FaceAnalysis(name="buffalo_l")` detects and embeds all 5 Gwen refs. No deepface fallback needed. Weights are non-commercial: internal QC only, never shipped.

## #6 — 2026-08-30: Distill LoRAs get their own strength class (cap 1.0)

The LoRA composition rule capped every non-identity LoRA at 0.6 so style/motion LoRAs can't fight identity. Lightning/lightx2v 4-step LoRAs are timestep-distillation adapters — they carry no subject/style content and are designed to run at 1.0 (both verified exports run them at strength 1). `validate_lora_stack` now takes `is_distill` with `MAX_DISTILL_STRENGTH = 1.0`; the 0.6 cap on style/motion LoRAs is unchanged.

## #5 — 2026-08-30: Templates are linear; the engine owns steps/cfg/LoRA switching; unset LoRA slots are pruned

The real ComfyUI exports drive draft/final via ComfySwitchNode + Primitive nodes and load LoRAs unconditionally. ComfyUI validates every node's `lora_name` against files on disk even on never-executed branches, so a template can't ship a dummy LoRA slot. Instead: templates keep the exports' verified model chains but drop the switch scaffolding (config `[render.draft]/[render.final]` decides steps/cfg/lightning at build time), and `prune_placeholder_loras` removes any LoraLoaderModelOnly whose `lora_name` is empty, rewiring consumers to the node's model input. The export's always-on `QWEN_EDIT_ACTION_V1` style LoRA was dropped as not wanted for character sheets; that slot is where the character's image LoRA will go after training.

## #4 — 2026-08-30: wan22_i2v built from the T2V export's structure + verified WanImageToVideo path

The provided `workflows/real/wan22_i2v.api.json` is actually a **T2V** graph: `wan2.2_t2v_*` UNETs (t2v high-noise fp8 not present on this machine), `EmptyHunyuanLatentVideo`, no image input, and t2v-v1.1 lightning LoRAs that aren't downloaded. It cannot run here as exported. The verified I2V template keeps the export's two-stage KSamplerAdvanced split (leftover-noise handoff), per-stage lightning LoRA placement, ModelSamplingSD3 shift 5.0, and CreateVideo→SaveVideo output, but swaps in the present I2V fp8 models + i2v lightning LoRAs and conditions via WanImageToVideo (schema read from the live /object_info, not memory). If a real I2V export lands later, re-verify against it.

## #3 — 2026-08-30: Hybrid image-anchored consistency architecture

Character consistency comes from image LoRA keyframes fed into Wan 2.2 I2V with a low-noise-expert LoRA, not from video-only training. Identity is measured via face embeddings calibrated against the character's own approved sheet (threshold = mean − 2·std of pairwise similarity, floor 0.30) rather than fixed universal thresholds.

## #2 — 2026-08-30: Preview gate fails closed

If `PREVIEW_PASSWORD` is unset, empty, or `CHANGE_ME`, every route returns 401. No page is ever reachable without a real password.

## #1 — 2026-08-30: Single monorepo

Consolidated e2egen (prompt compilation) and character-identity (identity packages) into one monorepo instead of separate repos — one schema, one config, one CLI. Original repos left untouched as fallback.
