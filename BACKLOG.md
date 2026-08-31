# Backlog

## Open

- Try 6-8 lightning steps in [render.medium] (currently 4): distill LoRAs tolerate it and it may buy motion smoothness for ~50% more render time.
- **Aesthetic/artifact gate:** identity scoring misses visually-bad renders (the kitchen keyframe scored 0.554 mid-pack while being the one Jeremy rejected). Add a jank check (e.g., an aesthetic scorer or VLM pass) alongside identity, or lean on multi-candidate re-rolls.

- **Wan low-noise LoRA: drop or retune (v001 is mildly identity-NEGATIVE, DECISIONS #11/#12):** the clean face-forward full-res A/B (2026-08-31, gwen_e2e_v002) scored no-LoRA min 0.314/mean 0.417 vs with-LoRA 0.220/0.365 — third consistent loss. Dropping it = null lora_paths.wan_low_noise. Retune recipe: lower LR (8e-5), drop loraplus_lr_ratio (fp16 stability — training diverged after epoch 5), max_timestep 900 (musubi docs), add short motion clips to the dataset.
- **Wan HIGH-noise expert LoRA (deferred):** only the low-noise expert is trained (identity/detail); the high-noise expert (composition/motion) uses base weights. Train with `sourcemode train wan gwen --expert high --run` (timesteps 875-1000) if identity drifts during large motion.
- **Face-visibility-aware video scoring:** frames where the subject faces away score ~0 and dominate the min — score only frames with a detected face above a size floor and report visible-frame coverage separately (the e2e tracking-from-behind shot min-scored 0.03-0.11 regardless of LoRA).
- **Keyframe scoring penalizes small faces:** full-body/wide keyframes score 0.28-0.43 vs 0.55-0.63 for close-ups of the SAME LoRA (face region too small at 1-1.5MP). Consider scoring an upscaled face crop, or shot-size-bucketed thresholds, alongside the existing pose-bucket idea below.
- Director Mode UI (3 screens)
- Draft/Final two-pass renders
- Dailies continuity card
- Wardrobe-state LoRA variants (wardrobe_states schema exists; train per-state image LoRAs or prompt-suffix states)
- Expression library
- Voice speaker-embedding check (deferred — likely unnecessary)
- 3-shot regression benchmark
- Gates run on CPUExecutionProvider (onnxruntime-gpu didn't register CUDA in the engine venv); acceptable for QC, investigate if throughput matters
- Identity gate is pose-sensitive (same-person profile scored 0.62 vs 0.7365 threshold): consider pose-bucketed thresholds or a frontal-only scoring ruler (e2egen's approach) before trusting scores on profile/extreme poses
- Record/select Gwen's voice reference clip (source.voice.reference_clip is null)
- Vercel preview-ENVIRONMENT env vars (PREVIEW_USERNAME/PREVIEW_PASSWORD) couldn't be added via CLI (non-TTY branch-prompt bug) — add in dashboard; production + development are set, and the gate fails closed regardless
- musubi docs recommend max_timestep 900 for the I2V low expert (we default to the spec'd 875) — revisit after first training run

## Done

- 2026-08-31 (3757ca2): Wan low-noise LoRA trained (fp16 fix; cut at epoch 10/14), min-score selection over 10 real I2V drafts, winner epoch 1 installed as gwen_wan22_low_v001; identity-neutral finding recorded (DECISIONS #11)
- 2026-08-31: e2e proof: `run gwen --pass final --sync-db` → outputs/review/gwen_e2e_v001 (+ _noLoRA A/B) with mp4, keyframes, scored frame strips, results.yaml; scene synced to Neon
- 2026-08-31 (ffdf210): image-LoRA trainer = musubi-tuner's qwen_image_train_network.py; dataset emitter + caption validation + checkpoint ranking shipped, training-grade model files downloaded (INVENTORY §4)
- 2026-08-31 (85258ed): Gwen sheet approved → image LoRA trained (early-stopped epoch 8/14, winner epoch 7, frontal mean 0.596); source v003 with lora_paths.image_lora; 8-keyframe proof render + contact sheet
- 2026-08-31 (309dc4e): frame-strip review artifact, run --no-wan-lora A/B, mp4 filenames
- 2026-08-31: wan22_i2v re-verified against Jeremy's real I2V graph (workflows/real/wan22_i2v_ui.json); per-stage CFG added, his settings adopted (shift 8, 28 steps, cfg 2.2/1.8, 24fps, max_frames 145) — DECISIONS #8
- 2026-08-31 (78d5c74): all three workflow templates verified against real ComfyUI 0.25.1 exports + live /object_info and smoke-rendered on GPU (qwen_image_edit 20s, wan22_i2v 26s, qwen_image_t2i 12s). Qwen models + lightning LoRAs downloaded; draft pass = 4-step lightning.
- 2026-08-31 (be1ee60): identity gate calibrated live with negative-face separation (0.8135 intra vs 0.1002 negative); gates report CSV + contact sheet.
- 2026-08-31 (f70eef9): bootstrap sheet live path + manifest; Gwen 36-image sheet rendered; source sync → Neon; dashboard shows gwen v002 behind the gate.
