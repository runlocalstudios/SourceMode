# Backlog

## Open

- **Gwen sheet awaiting approval (training gate):** 36-image dataset at `characters/gwen/dataset/` (local, gitignored); review `engine/outputs/review/gwen_sheet_contact.png` + `.csv`. 26/36 flagged advisory (pose/lighting score dips, no identity outliers). Approve → wan/image LoRA training next session.
- Director Mode UI (3 screens)
- Draft/Final two-pass renders
- Dailies continuity card
- Wardrobe-state LoRA variants
- Expression library
- Voice speaker-embedding check (deferred — likely unnecessary)
- 3-shot regression benchmark
- Image-LoRA trainer: neither AI-Toolkit nor diffusion-pipe installed; implement build_image_lora_cmd against musubi-tuner's qwen_image_train_network.py (Qwen-Image is Apache 2.0) and set [training].image_trainer_path
- Gates run on CPUExecutionProvider (onnxruntime-gpu didn't register CUDA in the engine venv); acceptable for QC, investigate if throughput matters
- Identity gate is pose-sensitive (same-person profile scored 0.62 vs 0.7365 threshold): consider pose-bucketed thresholds or a frontal-only scoring ruler (e2egen's approach) before trusting scores on profile/extreme poses
- Record/select Gwen's voice reference clip (source.voice.reference_clip is null)
- Vercel preview-ENVIRONMENT env vars (PREVIEW_USERNAME/PREVIEW_PASSWORD) couldn't be added via CLI (non-TTY branch-prompt bug) — add in dashboard; production + development are set, and the gate fails closed regardless
- musubi docs recommend max_timestep 900 for the I2V low expert (we default to the spec'd 875) — revisit after first training run

## Done

- 2026-08-31: wan22_i2v re-verified against Jeremy's real I2V graph (workflows/real/wan22_i2v_ui.json); per-stage CFG added, his settings adopted (shift 8, 28 steps, cfg 2.2/1.8, 24fps, max_frames 145) — DECISIONS #8
- 2026-08-31 (78d5c74): all three workflow templates verified against real ComfyUI 0.25.1 exports + live /object_info and smoke-rendered on GPU (qwen_image_edit 20s, wan22_i2v 26s, qwen_image_t2i 12s). Qwen models + lightning LoRAs downloaded; draft pass = 4-step lightning.
- 2026-08-31 (be1ee60): identity gate calibrated live with negative-face separation (0.8135 intra vs 0.1002 negative); gates report CSV + contact sheet.
- 2026-08-31 (f70eef9): bootstrap sheet live path + manifest; Gwen 36-image sheet rendered; source sync → Neon; dashboard shows gwen v002 behind the gate.
