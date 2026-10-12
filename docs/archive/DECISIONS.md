# Decisions

Append-only. Newest first.

## #14 — 2026-09-01: Second character (Bianca) validates the pipeline and exposes two real bugs

Bianca ported from e2egen (34 real curated photos, `LORApicked` provenance) as the second character. **The pipeline generalised with zero code changes to run it** — only a port script. Gate calibrated to 0.7149 intra / threshold 0.6178, with Gwen scoring 0.2964 as a negative (clean separation, so the scorer discriminates between two same-style photoreal characters). Training: 34 imgs x 5 repeats = 170 steps/epoch, plateaued by epoch 4 (0.682/0.698/0.695/0.683) — **faster and higher than Gwen** (best 0.596), evidence that a real-photo dataset beats a bootstrapped Qwen-Edit sheet. Winner e5 (mean 0.695, min 0.628); 8-keyframe proof mean 0.628 with 4/8 over threshold vs Gwen's 0/8, and her profile scored 0.686 despite the dataset containing no profiles.

Two bugs the second character exposed, both fixed:
1. **Checkpoint selection ranked on raw mean** (2a88493): e4 led e5 by 0.003 (noise on 4 samples) while its worst sample was 0.106 lower. Scores within `SCORE_TOLERANCE` now tie and break on the other statistic, then toward the earlier epoch.
2. **Keyframe template put environment before framing** (7c21eae): a strong compositional noun hijacked the subject slot — "cafe window in the late afternoon" rendered a *window* with a tiny unrecognisable person in all 4 candidates (0.30-0.43, all fail). Framing-first on the identical brief: **0.716-0.747, all pass.** This affected every scene-compiled keyframe including Gwen's (her e2e keyframes scored 0.558/0.602 vs 0.72+ for hand-written framing-first prompts) and matches e2egen's recorded finding that framing must be an explicit primary field.

Also measured: single keyframe renders have a **per-seed LoRA-activation lottery** — 2 of 8 proof renders came back as a different person entirely. Both a reseed and the next checkpoint fixed them (6/6 diagnostic renders passed), and the gate caught both. The 4-candidate + best-score design in `run_scene` is the mitigation, and it held on the fixed e2e (all 4 candidates 0.69-0.75).

## #13 — 2026-08-31: Medium is the working pass; character video LoRA unplugged; video LoRA slots stay generic

Jeremy's calls, executed same evening. **[render.medium]** = final-quality keyframes (50-step Qwen, identity lives there) + 4-step lightning video at full 1024x1280: measured 634 s for the 6 s proof shot AND it out-scored the 2.4 h final on identity (min 0.441/mean 0.540 vs 0.314/0.417 — distilled sampling drifts the face less over 145 frames). Full final stays for hero shots. **gwen v003 approved** (new `source approve` command) and synced to Neon. **lora_paths.wan_low_noise nulled** per the three-loss A/B record; the wan22_i2v template keeps both per-stage LoRA slots — a character LoRA (if retrained) takes the slot at 1.0, else a generic style/motion LoRA from `[video].lora_high/lora_low` fills it capped at MAX_OTHER_STRENGTH 0.6 (per-slot strengths: LORA_STRENGTH_HIGH/LOW).

## #12 — 2026-08-31: Video quality was the prompt pipeline, not the LoRA; final-pass 1024x1280 verified good but costs ~2.4 h per 6 s shot

Jeremy called the 832x480 e2e "AI slop" in both A/B variants — root causes were pipeline, not model: the rule decomposer emitted garbled English ("…at night, the slowly,") and crammed a two-phase camera move into one I2V shot, and the resolution default ignored the proven graph's 1024x1280 (b2c53d0 fixed all three; briefs now split on "then" into single-move shots). The face-forward re-run at 1024x1280 final looks like a real shoot (stable identity, clean push-in) and scored min 0.220/mean 0.365 vs the market shot's 0.026/0.203. Cost discovered: two-stage 28-step final at 1.3 MP x 145 frames runs ~305 s/step ≈ 2.4 h/shot on the 5090 (480p was ~3 min). Final quality at this res is real but not an iteration loop — draft = lightning at full res (~20 min), final = overnight, or drop frames/res (BACKLOG). Also: a transient /history poll failure killed a run mid-render — client.wait now tolerates dropped polls (30ba2ce).

## #11 — 2026-08-31: Wan low-noise LoRA v001 installed but measured identity-NEUTRAL; selection caught real divergence

The min-score selection worked as designed: epochs 6–10 collapsed (min 0.43→0.03) after an fp16 loss spike at ~epoch 6 (avr_loss 0.001→0.03), and the ranking surfaced it immediately. Winner = epoch 1 (min 0.4334 draft / 0.3500 final). But controls show v001 buys nothing yet: same-seed baseline WITHOUT the LoRA scored min 0.4609 draft / 0.3379 final, and the e2e A/B (identical keyframes) scored no-LoRA min 0.106/mean 0.246 vs with-LoRA 0.026/0.203. Installed anyway as the plumbing proof (slot wiring, selection, A/B are now real); identity today comes from the image-LoRA keyframe + Wan's natural preservation. Retune knobs backlogged: lower LR / drop loraplus ratio (fp16 stability), max_timestep 900, motion clips in the dataset. Also learned: a tracks-her-from-behind shot inherently zeroes face-identity frames — min-score on such shots measures shot design, not the LoRA (BACKLOG: face-visibility-aware video scoring).

## #10 — 2026-08-31: LoRA checkpoint selection — frontal mean for image, worst-frame min for video, ties to the earlier epoch

Image-LoRA checkpoints are ranked by MEAN identity over 4 fixed frontal sample prompts (the scorer is pose-sensitive — DECISIONS/BACKLOG — so only same-pose samples are comparable), with a brightness-spread "prompt inertia" check flagging checkpoints whose 4 varied-lighting prompts render near-identically (overfit signal). Wan-LoRA checkpoints are ranked by MIN identity across sampled frames of one real I2V draft each: a video is only as good as its worst frame — a face that collapses mid-motion is a broken shot regardless of the average. All ties (3 decimals) break toward the EARLIER checkpoint: same score, less overfit risk.

## #9 — 2026-08-31: musubi-tuner trains BOTH LoRAs (Qwen-Image + Wan 2.2); training-grade model files are separate downloads

musubi-tuner 0.3.4 ships full Qwen-Image LoRA support (`qwen_image_train_network.py`), so one trainer + one dataset-config format covers the image and video LoRAs — AI-Toolkit/diffusion-pipe never got installed. Two file facts drove downloads (INVENTORY §4): musubi cannot train from fp8_scaled/fp8_e4m3fn FILES (needs `qwen_image_2512_bf16` + non-fp8 `qwen_2.5_vl_7b`; `--fp8_base --fp8_scaled` quantize at load), and musubi's Wan T5 loader cannot read ComfyUI's umt5 safetensors (HF-style keys — verified against the header), requiring the official `models_t5_umt5-xxl-enc-bf16.pth`. Both experts of the Wan pair train on task **i2v-A14B** (not t2v): inference is I2V, and the LoRA must match the expert weights it will patch. Only the low-noise expert is trained for now — it renders fine detail/identity; the high-noise expert (composition/motion) is deferred (BACKLOG).

## #7 — 2026-08-30: Identity-gate embedding backend = InsightFace buffalo_l (CPU provider)

Option (a) from the backend ladder won on the first try: `insightface` + `onnxruntime-gpu` import and run in the engine venv (CUDA EP doesn't register there, CPU EP is fast enough for QC — see BACKLOG). `FaceAnalysis(name="buffalo_l")` detects and embeds all 5 Gwen refs. No deepface fallback needed. Weights are non-commercial: internal QC only, never shipped.

## #6 — 2026-08-30: Distill LoRAs get their own strength class (cap 1.0)

The LoRA composition rule capped every non-identity LoRA at 0.6 so style/motion LoRAs can't fight identity. Lightning/lightx2v 4-step LoRAs are timestep-distillation adapters — they carry no subject/style content and are designed to run at 1.0 (both verified exports run them at strength 1). `validate_lora_stack` now takes `is_distill` with `MAX_DISTILL_STRENGTH = 1.0`; the 0.6 cap on style/motion LoRAs is unchanged.

## #5 — 2026-08-30: Templates are linear; the engine owns steps/cfg/LoRA switching; unset LoRA slots are pruned

The real ComfyUI exports drive draft/final via ComfySwitchNode + Primitive nodes and load LoRAs unconditionally. ComfyUI validates every node's `lora_name` against files on disk even on never-executed branches, so a template can't ship a dummy LoRA slot. Instead: templates keep the exports' verified model chains but drop the switch scaffolding (config `[render.draft]/[render.final]` decides steps/cfg/lightning at build time), and `prune_placeholder_loras` removes any LoraLoaderModelOnly whose `lora_name` is empty, rewiring consumers to the node's model input. The export's always-on `QWEN_EDIT_ACTION_V1` style LoRA was dropped as not wanted for character sheets; that slot is where the character's image LoRA will go after training.

## #8 — 2026-08-31: wan22_i2v re-verified against Jeremy's working I2V graph; his settings adopted

`workflows/real/wan22_i2v_ui.json` (from `C:\ComfyUI\user\default\workflows\img2vid wan2.2 2026 w LORA.json`) is a genuine I2V graph and confirms the #4 rebuild node-for-node: UNET → per-stage LoRA chain → ModelSamplingSD3 → two-stage KSamplerAdvanced (boundary = steps/2) with WanImageToVideo conditioning. Adopted its measured settings as final-pass/video defaults: **shift 8.0** (over the official 5.0), **28 steps**, **per-stage CFG 2.2 high / 1.8 low** (template gained CFG_HIGH/CFG_LOW — a single shared CFG was wrong), **24 fps**, **max_frames 145** (config-capped; the ported 81 cap stays the code default). Output stays CreateVideo→SaveVideo mp4-h264 rather than the graph's WEBP/WEBM (pipeline consumes mp4). Re-smoked live on the final pass: 92.4s for 2s @ 480px.

## #4 — 2026-08-30: wan22_i2v built from the T2V export's structure + verified WanImageToVideo path

The provided `workflows/real/wan22_i2v.api.json` is actually a **T2V** graph: `wan2.2_t2v_*` UNETs (t2v high-noise fp8 not present on this machine), `EmptyHunyuanLatentVideo`, no image input, and t2v-v1.1 lightning LoRAs that aren't downloaded. It cannot run here as exported. The verified I2V template keeps the export's two-stage KSamplerAdvanced split (leftover-noise handoff), per-stage lightning LoRA placement, ModelSamplingSD3 shift 5.0, and CreateVideo→SaveVideo output, but swaps in the present I2V fp8 models + i2v lightning LoRAs and conditions via WanImageToVideo (schema read from the live /object_info, not memory). If a real I2V export lands later, re-verify against it.

## #3 — 2026-08-30: Hybrid image-anchored consistency architecture

Character consistency comes from image LoRA keyframes fed into Wan 2.2 I2V with a low-noise-expert LoRA, not from video-only training. Identity is measured via face embeddings calibrated against the character's own approved sheet (threshold = mean − 2·std of pairwise similarity, floor 0.30) rather than fixed universal thresholds.

## #2 — 2026-08-30: Preview gate fails closed

If `PREVIEW_PASSWORD` is unset, empty, or `CHANGE_ME`, every route returns 401. No page is ever reachable without a real password.

## #1 — 2026-08-30: Single monorepo

Consolidated e2egen (prompt compilation) and character-identity (identity packages) into one monorepo instead of separate repos — one schema, one config, one CLI. Original repos left untouched as fallback.
