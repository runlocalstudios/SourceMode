# INVENTORY

Read-only survey of the source repos and local installs, 2026-08-30. Sources were NOT modified.

## 1. e2egen (`C:\dev\e2egen`)

**Stack:** Python 3.11.9 (plain package, run via `python -m e2egen.cli`, no pyproject/tests) + a Next.js 14 web UI (`webui/`, port 3900). Deps: requests, Pillow, PyYAML (declared); opencv-python-headless, numpy, psutil (undeclared but used). External runtime deps: ComfyUI at `http://127.0.0.1:8188`, ffmpeg, RTX 5090. `vendor/` holds sd-scripts and musubi-tuner with their own venvs (gitignored).

**Entry points:** `e2egen/cli.py` — subcommands `prep`, `train`, `generate`, `genset` (JSON SetSpec → batch), `genvideo` (chained Wan 2.2 I2V), `refs`, `sheet`, `score`, `characters`, `loras`, `run`. Web UI spawns `python -m e2egen.cli genset|genvideo` via a FIFO queue.

**Prompt compilation** (split across four unshared implementations — consolidated in our `prompts/` module):
- `e2egen/sets.py` — the production compiler: `SetSpec` dataclass (17 defaulted fields) → `build_spec_prompts(trigger, spec) -> list[{shot, prompt}]`, rotating expression/framing/lighting vocabularies by index so a set varies while fixed attributes stay constant. **The compiler↔driver contract is `list[dict]` with `shot` and `prompt` keys.**
- `e2egen/shot_library.py` — minimal API shape: `build_prompt(trigger, shot) -> str` = `f"a photo of {trigger}, {shot}, {STYLE_SUFFIX}"`.
- `e2egen/validation_shots.py` — scoring ruler v2.1: 8 CORE_SHOTS (scored, frontal-only by design) + 2 DIAGNOSTIC_SHOTS (never scored), versioned via `SHOTS_VERSION`.
- `prompts/shot_plan.json` + `prompts/gen_shot_plan.py` — generated 60-shot plan (5 tiers × 12) with compose format `{identity_block} {framing}, {angle}, {expression}, hair {hair}, {wardrobe_clause}{setting}, {lighting}. {suffix}` and a structural hair rotation `(i + 5*t) % 12`.
- `scripts/caption_florence.py:35-79` — pure-regex caption cleaning (`clean`, `clean_concept`, `_strip_traits`) that strips generic subject phrases and invariant traits so identity binds to the trigger token.
- `scripts/suggest_invariants.py:40-75` — pure-regex trait mining (`TRAIT_PATTERNS`, `mine()`, ≥60% threshold).
- `e2egen/video.py` — **no video prompt compilation exists**; Wan legs are free operator text. Only structure: 4n+1 frame snapping, ≤81 frames.

**Encoded prompt-engineering findings carried into our templates:**
- Hair COLOR must be restated in every prompt (trained-in colors don't reappear unless prompted); hair style optional; "messy" is a texture not an updo.
- Flux ignores `(text:weight)` emphasis — state camera distance as directive prose up front.
- Framing and head angle must be explicit primary fields or models collapse to head-and-shoulders.
- Identity block ≤ ~30 words or the generator drops the framing instruction.
- Wide framings need 1536px or the face starves (0.773@1024 → 0.854@1536).
- Scored shots must be frontal/near-frontal; expressive stress poses are diagnostic-only.
- High identity mean + low pose diversity is a warning sign, not success.

**Config:** `config/settings.yaml` (deep-merged with gitignored `settings.local.yaml`, `./`→absolute path resolution in `e2egen/config.py`). Heavily commented with measured constants, incl. negative prompts (chroma :129, flux2 :154, reference :188, wan :221) and the Wan 2.2 block (i2v 14B fp8, lightx2v 4-step distill LoRA, 720p buckets, fps 16).

**Tests:** none anywhere in e2egen (verified repo-wide). Empirical scoring gates stand in (SFace cosine vs reference set, impostor-anchored calibration).

**Reusable for `prompts/` (ported/adapted):** `sets.py` (structure + rotation trick), `shot_library.py` (API shape), `validation_shots.py` (ruler structure), `caption_florence.py` pure functions, `suggest_invariants.py` pure functions, the compose/identity-block/suffix templates and rules from `shot_plan.json`/`SKILL_SPEC.md`, and the settings.yaml findings above.
**Not ported:** `workflow.py` (574 lines ComfyUI-node-specific — we template JSON workflows instead), `generate.py`/`video.py`/`comfy_client.py` (infra, reimplemented thin), webui, sunny_* one-offs, trainer scripts.

## 2. character-identity-dev (`C:\Epic Games\Files\cnc info\codex\character-identity-dev`)

**Stack:** Python ≥3.11, src-layout, Pydantic v2 + Typer + Rich; package `character_identity` v0.1.0. Full CLI (`doctor`, `init-character`, `preprocess`, `fit`, `render-approval`, `approve` → frozen `identity/vNNN/`, `create-shot`, `export-generation-job`, `audit`, `status`) with meaningful exit codes.

**Identity-package schema:** `src/character_identity/schemas/identity.py` (+ `common.py` base). Root model `IdentityPackage` (StrictModel, `extra="forbid"`): schema_version, character_id, display_name, identity_version (`^v\d{3,}$`), created_at, previous_version, references (exactly one authoritative), shared_shape (3DMM), per_image, canonical_renders, embeddings (list of EmbeddingRecord: path/dim/sha256/embedder BackendInfo), fitter/renderer/embedder backends, is_real_reconstruction, flame_version, warnings, conventions, approval (ApprovalRecord), validation (ValidationConfig: identity_similarity_pass/warn, pose_tolerance_deg, min_blur_score, `calibrated: bool`, calibration_note), invariants (`dict[str,str]`), package_sha256 (tamper-checked on load).

**Schema → CharacterSource mapping:**
| CharacterSource | IdentityPackage source | Notes |
|---|---|---|
| character_id | character_id | id regex `^[a-z0-9][a-z0-9_-]{0,63}$` (from CharacterState) adopted |
| name | display_name | rename |
| version | identity_version | keep `^v\d{3,}$`; bump logic ~ `utils.next_version_name` |
| invariants | invariants dict | flattened to `list[str]` ("hair: ...") |
| reference_images | references[].provenance | narrowed to paths |
| approved_sheet | canonical_renders + approval contact sheet | new explicit field |
| identity_embedding_path | embeddings[].path | narrowed to one path |
| identity_threshold | validation.identity_similarity_pass | carried the `calibrated` honesty concept: threshold is None until calibrated |
| trigger_token, wardrobe_states, negative_block, voice, lora_paths | **none — new fields** | negative_block existed only as a global constant in `generation/jobs.py:79-82`; wardrobe only as free-text per-shot |

**Gwen v002** (`characters\gwen\identity\v002\`): the only version with invariants —
`hair: long wavy copper-red, centre parted` / `eyes: green-hazel, dark winged liner` / `skin: fair with freckles across nose and cheeks`. Approved by jeremy 2026-08-27, mock geometry + mock 576-d embeddings, thresholds uncalibrated (0.55/0.40 defaults). **Gwen v004** is the current version: real DECA/FLAME-2020 fit + real 512-d insightface-buffalo_l embeddings, but `invariants: {}`. Port takes **references + invariants from v002**; embeddings are recomputed by our own calibration (v004's .npy kept as reference data only).

**Gwen reference images** (5 PNG, 1 authoritative + 4 supporting, ~11.4 MB, read-only frozen copies):
`...\characters\gwen\identity\v002\references\ref-00-canonical.png` (1024×1536) through `ref-04-supporting.png`. Byte-identical copies at `...\characters\gwen\references\`. Approved contact sheet: `...\characters\gwen\approval\fit-20260827T060613Z-mock-procedural-head\cand-01\contact_sheet.png`.

**Export-jobs format:** `schemas/generation.py` `GenerationJob` — job_id `{character_id}-{shot_id}-a{attempt:02d}`, embedded ShotSpec, prompt (min 20 chars), negative_prompt, invariants, identity_references (≥1 authoritative), control_images, OutputSpec, AuditRequirements, Budget (attempt caps, refuses past budget). Written to `characters/<id>/jobs/`, never overwritten. Exemplar: `...\characters\gwen\jobs\gwen-gwen-set06-05-a02.json`. Its negative prompt (the repo's only negative block, adopted as Gwen's default `negative_block`):
`face patch, seams, halo, ghosting, duplicated features, plastic skin, waxy skin, beauty filter, copied reference background, text, watermark, logo, distorted hands, extra limbs`.

**Tests:** 12 files/1,592 lines pytest; `test_schemas.py` assertions (authoritative-ref invariant, bounded semantic controls, JSON-schema round-trip) informed our `source/` tests.

## 3. ComfyUI

**Found: `C:\ComfyUI`**, version **0.25.1** (`comfyui_version.py`), Python 3.11 venv at `C:\ComfyUI\venv311`, started via `start.bat` (`python main.py --auto-launch` → default port **8188**; not running at inventory time — nothing listening on 8188).

Wan 2.2 models present in `C:\ComfyUI\models\`:
- `diffusion_models\wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors` (13.3 GB) + `_fp16` (26.6 GB)
- `diffusion_models\wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors` (13.3 GB) + `_fp16` (26.6 GB)
- also t2v_low_noise fp16, s2v bf16
- `vae\wan2.2_vae.safetensors` (5B-only) and `vae\wan_2.1_vae.safetensors` (**the correct VAE for 14B models**)
- `text_encoders\umt5_xxl_fp8_e4m3fn_scaled.safetensors` + `umt5_xxl_fp16.safetensors`
- Wan 2.2 I2V high/low-noise LoRA pair exists as an example (`Wan 2.2 I2V k1ssl1ck_*.safetensors` in loras/)
- No Qwen-Image DiT present yet (Qwen3 text encoders exist: `qwen3vl_8b_fp8_scaled`, `qwen_3_8b`); InsightFace models dir exists at `models\insightface`.

Config recorded in `engine/config.toml`: host 127.0.0.1, port 8188.

## ComfyUI models present

Surveyed 2026-08-30 (running instance: ComfyUI 0.25.1, frontend 1.45.15, Python 3.11.9, torch 2.10.0+cu128, RTX 5090 32GB). 544 GB free on C: before the Qwen downloads. Only pipeline-relevant files listed; the loras/ dir also holds ~30 legacy e2egen/personal LoRAs (chroma/flux/wan, not used by SourceMode).

**diffusion_models/** (pipeline-relevant)
- `wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors` 13.3 GB + `_fp16` 26.6 GB
- `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors` 13.3 GB + `_fp16` 26.6 GB
- `wan2.2_t2v_low_noise_14B_fp16.safetensors` 26.6 GB (no t2v high-noise, no t2v fp8 — the wan22_i2v "real" export referenced these, see DECISIONS #4)
- `wan2.2_s2v_14B_bf16.safetensors` 30.4 GB
- `qwen_image_edit_2511_fp8mixed.safetensors` 20.5 GB — **downloaded 2026-08-30** (Comfy-Org/Qwen-Image-Edit_ComfyUI; 2511 has no fp8_e4m3fn variant)
- `qwen_image_2512_fp8_e4m3fn.safetensors` 20.4 GB — **downloaded 2026-08-30** (Comfy-Org/Qwen-Image_ComfyUI)
- non-pipeline: Chroma1-HD 16.6 GB, flux-2-klein 16.9 GB (non-commercial — never used), ideogram4 ×2 17.2 GB, wan22Remix 13.3 GB
- No Z-Image present (Qwen-Image 2512 is the sole keyframe model).

**text_encoders/**: `umt5_xxl_fp8_e4m3fn_scaled.safetensors` 6.3 GB, `umt5_xxl_fp16.safetensors` 10.6 GB, `qwen_2.5_vl_7b_fp8_scaled.safetensors` 9.4 GB (**downloaded 2026-08-30**), plus qwen3vl_8b/qwen_3_8b/gemma4 (unused by pipeline).

**vae/**: `wan_2.1_vae.safetensors` 0.2 GB (correct for Wan 2.2 14B), `wan2.2_vae.safetensors` 1.3 GB (5B-only), `qwen_image_vae.safetensors` 0.25 GB (**downloaded 2026-08-30**).

**loras/** (pipeline-relevant)
- `wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors` 1.1 GB (already present)
- `wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors` 1.1 GB (already present)
- `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors` 0.85 GB — **downloaded 2026-08-30** (lightx2v/Qwen-Image-Edit-2511-Lightning)
- `Qwen-Image-2512-Lightning-4steps-V1.0-bf16.safetensors` 0.85 GB — **downloaded 2026-08-30** (lightx2v/Qwen-Image-2512-Lightning)

**clip_vision/**: only flux/sdxl encoders (unused; Wan 2.2 I2V 14B needs no clip_vision).

**Identity gate backend:** InsightFace buffalo_l via onnxruntime **CPUExecutionProvider** in the engine venv (CUDA EP doesn't register there; acceptable for QC — see BACKLOG). Decision record: DECISIONS #7.

## 4. musubi-tuner

**Found (vendored): `C:\dev\e2egen\vendor\musubi-tuner`**, version **0.3.4** (pyproject.toml), own `.venv` present. Read-only — SourceMode invokes it in place. No standalone AI-Toolkit or diffusion-pipe install found anywhere (searched C:\dev, C:\tools, C:\AI, user dirs); fluxgym exists under Pinokio but targets Flux (non-commercial license — banned by our license invariant). **musubi-tuner trains BOTH LoRAs** — it ships full Qwen-Image LoRA support (`docs/qwen_image.md`), so no second trainer is needed.

**Exact Qwen-Image LoRA training CLI (verified in `docs/qwen_image.md` + `qwen_image_train_network.py` argparse, 2026-08-31):**
- Latent caching: `python src/musubi_tuner/qwen_image_cache_latents.py --dataset_config <toml> --vae <qwen_image_vae.safetensors> --model_version original` (ComfyUI's VAE file IS accepted; `--model_version original` covers the 2512 checkpoint — same architecture, no 2512-specific code exists in 0.3.4).
- Text-encoder caching: `python src/musubi_tuner/qwen_image_cache_text_encoder_outputs.py --dataset_config <toml> --text_encoder <qwen_2.5_vl_7b.safetensors> --batch_size 1 --model_version original`.
- Training: `accelerate launch --num_cpu_threads_per_process 1 --mixed_precision bf16 src/musubi_tuner/qwen_image_train_network.py --dit <bf16 DiT> --vae <vae> --text_encoder <VL> --model_version original --dataset_config <toml> --sdpa --mixed_precision bf16 --fp8_base --fp8_scaled --network_module networks.lora_qwen_image --timestep_sampling shift --weighting_scheme none --discrete_flow_shift 2.2 ...` — docs recommend shift 2.2 for Qwen-Image (inference uses dynamic ~2.2 @ 1M px; `qwen_shift` is the dynamic alternative).
- **fp8_scaled / fp8_e4m3fn model FILES cannot be used for training** (`--fp8_base --fp8_scaled` quantize the bf16 file at load; ~30 GB VRAM @ 1024/bs1, `--blocks_to_swap 16` → 24 GB).
- **musubi's Wan T5 loader cannot read ComfyUI's umt5_xxl safetensors** — HF-style keys (`encoder.block.N...`, verified against the file header) vs musubi's custom naming (`blocks.N.attn...`); the official `models_t5_umt5-xxl-enc-bf16.pth` (Wan-AI/Wan2.1-I2V-14B-720P, 10.6 GB) is required. Wan VAE: ComfyUI's `wan_2.1_vae.safetensors` is explicitly supported.
- Sampling during training: `--sample_prompts <file> --sample_every_n_epochs 1`; prompt-file line options `--w --h --d seed --s steps --l cfg_scale --n negative` (`training/sampling_prompts.py`); samples land in `<output_dir>/sample/{name}_e{epoch:06d}_{prompt:02d}_{ts}_{seed}.png`. Checkpoints: `{name}-{epoch:06d}.safetensors`.
- Training-grade files downloaded 2026-08-31: `diffusion_models/qwen_image_2512_bf16.safetensors` (38.1 GB), `text_encoders/qwen_2.5_vl_7b.safetensors` (15.4 GB), `text_encoders/models_t5_umt5-xxl-enc-bf16.pth` (10.6 GB).

**Exact Wan 2.2 LoRA training CLI (verified in `docs/wan.md` and argparse source, not from memory):**
- Latent caching: `python src/musubi_tuner/wan_cache_latents.py --dataset_config <toml> --vae <wan_2.1_vae>` — add `--i2v` for I2V models; Wan 2.2 needs no `--clip`.
- Text-encoder caching: `python src/musubi_tuner/wan_cache_text_encoder_outputs.py --dataset_config <toml> --t5 <umt5-xxl> --batch_size 16`.
- Training: `accelerate launch --num_cpu_threads_per_process 1 --mixed_precision bf16 src/musubi_tuner/wan_train_network.py` with:
  `--task i2v-A14B` (Wan 2.2 14B I2V; `t2v-A14B` for T2V), `--dit <model>` (fp16/bf16 — **fp8_scaled model files are NOT supported**; `--fp8_base` + `--fp8_scaled` flags quantize at load), `--dataset_config <toml>`, `--sdpa`, `--mixed_precision bf16`, `--fp8_base`, `--fp8_scaled`, `--optimizer_type adamw8bit`, `--learning_rate 1.6e-4`, `--gradient_checkpointing`, `--network_module networks.lora_wan`, `--network_dim 32`, `--network_alpha 16`, `--network_args loraplus_lr_ratio=4` (**LoRA+ ratio is a network_args kwarg, not a top-level flag** — `networks/lora.py:477`), `--timestep_sampling sigmoid` (valid choice per `training/parser_common.py:444`), `--discrete_flow_shift 5.0` (official I2V inference shift), `--min_timestep 0 --max_timestep 875` (low expert; **docs table recommends 900 for I2V low / 875 is the T2V boundary** — we default 875 per spec, configurable), `--preserve_distribution_shape` (recommended when single-expert training with a timestep range), `--save_every_n_steps N`, `--output_dir`, `--output_name`, `--seed`.
  High expert: `--min_timestep 875 --max_timestep 1000` (docs: 900–1000 for I2V high).
- Resolution is set in the dataset TOML (`resolution = [1024, 1024]` in `[[datasets]]`), NOT a CLI flag.
- Dual-expert alternative: `--dit <low> --dit_high_noise <high> --timestep_boundary 900` (single run, both experts).

## 5. Ported

(Ported files listed per module; sources were copied, never moved.)

- `characters/gwen/references/ref-00-canonical.png … ref-04-supporting.png` ← `C:\Epic Games\Files\cnc info\codex\character-identity-dev\characters\gwen\identity\v002\references\` (write bit restored after copy)
- `characters/gwen/approved_sheet/contact_sheet.png` ← `...\characters\gwen\approval\fit-20260827T060613Z-mock-procedural-head\cand-01\contact_sheet.png`
- `characters/gwen/source.json` ← synthesized from `...\identity\v002\identity.json` (invariants, approval lineage, negative block from `generation/jobs.py`) per the mapping table above
- `engine/sourcemode/prompts/compile.py` ← logic adapted from `C:\dev\e2egen\e2egen\sets.py` (SetSpec rotation pattern) and `prompts/shot_plan.json` (compose rules)
- `engine/sourcemode/prompts/captions.py` ← pure functions from `C:\dev\e2egen\scripts\caption_florence.py:35-79`
- ID regex + version-bump semantics ← `character_identity/schemas/character.py`, `utils.next_version_name`
- Negative block default ← `character_identity/generation/jobs.py:79-82`
