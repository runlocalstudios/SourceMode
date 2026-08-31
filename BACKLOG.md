# Backlog

## Open

- Director Mode UI (3 screens)
- Draft/Final two-pass renders
- Dailies continuity card
- Wardrobe-state LoRA variants
- Expression library
- Voice speaker-embedding check (deferred — likely unnecessary)
- 3-shot regression benchmark
- Verify workflow JSONs against a real ComfyUI export (both shipped templates are TEMPLATE-UNVERIFIED: workflows/wan22_i2v.json, workflows/qwen_image_t2i.json)
- Image-LoRA trainer: neither AI-Toolkit nor diffusion-pipe installed; implement build_image_lora_cmd against musubi-tuner's qwen_image_train_network.py (Qwen-Image is Apache 2.0) and set [training].image_trainer_path
- Download Qwen-Image DiT + VAE into C:\ComfyUI\models (only the Qwen3 text encoders are present) and fill [models].qwen_* config keys
- bootstrap sheet live path: needs a verified Qwen-Image-Edit workflow template (currently --dry-run only); wire a render_sheet_job client adapter
- Lightning/distill LoRA for the draft pass ([render.draft].lightning_lora is empty — draft currently just runs low steps)
- Gates run on CPUExecutionProvider (onnxruntime-gpu didn't register CUDA in the engine venv); acceptable for QC, investigate if throughput matters
- Record/select Gwen's voice reference clip (source.voice.reference_clip is null)
- Vercel preview-ENVIRONMENT env vars (PREVIEW_USERNAME/PREVIEW_PASSWORD) couldn't be added via CLI (non-TTY branch-prompt bug) — add in dashboard; production + development are set, and the gate fails closed regardless
- musubi docs recommend max_timestep 900 for the I2V low expert (we default to the spec'd 875) — revisit after first training run
