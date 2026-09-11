"""Native single-pass character generation. The pipeline that works.

ONE model pass. The source asset supplies wardrobe and framing, a trained
character LoRA supplies identity, the prompt supplies the pose. Nothing is cut
out, downscaled, warped, grafted, healed, pasted or keyed — so none of those
stages can leave an artifact.

Measured on 30 generations per character, scored against the source face:

    sunny      mean 0.820   27/30 above 0.75
    vivienne   mean 0.834   30/30 above 0.75

For scale: cross-character similarity sits near 0.27, and a genuine same-person
frontal set measured 0.81. Volume plus selection is the intended workflow —
generate 30, keep the best few — not perfecting a single render.

WHAT THIS REPLACED, and why each stage had to go. Every one of these was built,
measured, and defeated by an artifact it could not fix without creating another.
Recorded so they are not rebuilt:

  1. AnyPose transfer with a reference PHOTOGRAPH of another woman.
     Her identity competed with the character's on every render — masking her
     face was worth +0.07 identity, which is the measure of how much damage the
     unmasked reference was doing. But the whole approach regenerates the entire
     figure, so the face was redrawn from the model's prior every time. Result:
     0.61 mean identity and universally airbrushed skin.

  2. Whole-frame refine pass.
     Editing the full image to fix the face gives the face a few hundred pixels
     of a 1MP budget. Identity moved by hundredths. Useless.

  3. Face-crop refine (regenerate the crop, reference-conditioned).
     Identity only transferred above ~0.85 denoise, which is exactly where the
     model re-framed the crop and turned the head, so every strong candidate
     failed the pose gate. Identity import and geometry override switch on
     together; no denoise value held both.

  4. Landmark-affine GRAFT of the source face, then heal.
     Reached 0.87 identity and looked wrong: a 2D affine cannot rotate a face in
     3D, so a frontal source warped onto a head tilted up to camera smears. Cost
     three iterations of mask design (generous ellipse -> magenta halos;
     skin-only ellipse -> lost the identity with them; two-zone + despill), and
     the geometry was never fixable.

  5. Regenerate-and-paste with a character LoRA.
     Closest of the surgical attempts. Still produced bobbleheads, because at the
     denoise it needs the model re-frames the face inside its crop and pasting
     back at the crop's scale enlarges the head. Scale-alignment fixed that, then
     green-screen backdrop bled into hair on chroma-keyed sources. Each fix
     revealed the next seam.

The pattern across all five: every stage compensated for damage done by the
previous stage, and every compensation had its own failure mode. The stack never
converged because the architecture had too many seams, not because any single
stage was wrong. Deleting the seams deleted the artifacts.

The one thing given up: outfits are PROMPT-DESCRIBED here, so they are faithful
in character but not pixel-identical. Guaranteeing exact wardrobe is the entire
reason the surgical stack existed, and that guarantee is what cost the image
quality.
"""

from __future__ import annotations

from pathlib import Path

# Selected by scoring candidates through this pipeline, not by training loss.
LORA_STRENGTH = 0.85
# The 1MP bucket FluxKontextImageScale snaps to is where skin texture died:
# assets are ~1.57MP, the bucket is 832x1248, and LANCZOS cannot restore what
# the downscale removed. Render near native instead.
NATIVE_W, NATIVE_H = 1024, 1536

LOOK = ("Photorealistic, natural skin texture with visible pores and freckles, sharp focus, "
        "soft even studio lighting, plain light grey background. Natural realistic human "
        "proportions, correct anatomy, a normal sized head.")
NEGATIVE = (
    "different person, different face, changed hair, deformed, distorted hands, extra limbs, "
    "airbrushed, smoothed skin, plastic skin, doll-like, bobblehead, oversized head, "
    # No nudity terms here by design (2026-09-11): the negative block is for
    # QUALITY and identity drift only. Wardrobe — including its absence — is
    # stated in the positive prompt by the caller, per shot.
    "green tint, colour cast, blurry, low quality, cartoon, anime, watermark, text"
)


def build_native_workflow(cfg: dict, image_name: str, prompt: str, seed: int, prefix: str,
                          *, lora: str, lora_strength: float = LORA_STRENGTH,
                          render_pass: str = "medium",
                          width: int = NATIVE_W, height: int = NATIVE_H) -> dict:
    """Single-pass edit graph: one image in, one sampler, character LoRA loaded.

    Deliberately the plain qwen_image_edit graph — no AnyPose, no reference
    photograph, no second pass. Lightning is off: this path is about quality,
    and the distilled 4-step preset exists for iteration speed.
    """
    from ..config import workflows_dir  # noqa: PLC0415
    from ..render.workflow import load_template, prune_placeholder_loras, substitute  # noqa: PLC0415

    preset = cfg["render"][render_pass]
    settings = {
        "MODEL": cfg["models"]["qwen_edit"],
        "TEXT_ENCODER": cfg["models"]["qwen_text_encoder"],
        "VAE": cfg["models"]["qwen_vae"],
        "POSITIVE": prompt,
        "NEGATIVE": NEGATIVE,
        "IMAGE": image_name,
        "LORA_PATH": lora, "LORA_STRENGTH": lora_strength,
        "LIGHTNING": "", "LIGHTNING_STRENGTH": 0.0,
        "SHIFT": float(cfg["render"]["qwen_shift"]),
        "SEED": seed,
        "STEPS": int(preset["qwen_edit_steps"]),
        "CFG": float(preset["qwen_edit_cfg"]),
        "FILENAME_PREFIX": prefix,
    }
    nodes = prune_placeholder_loras(
        substitute(load_template(workflows_dir(cfg), "qwen_image_edit"), settings))
    # Swap the ~1MP bucket scaler for a fixed near-native scale.
    for nid, node in list(nodes.items()):
        if node["class_type"] == "FluxKontextImageScale":
            nodes[nid] = {"class_type": "ImageScale",
                          "inputs": {"image": node["inputs"]["image"],
                                     "upscale_method": "lanczos",
                                     "width": width, "height": height, "crop": "disabled"}}
    loaded = {n["inputs"].get("lora_name") for n in nodes.values()
              if n["class_type"] == "LoraLoaderModelOnly"}
    assert lora in loaded, f"character LoRA did not load: {loaded}"
    return nodes


def compose_prompt(trigger: str, pose_text: str, outfit_text: str) -> str:
    """trigger + pose + outfit + house look. Order matters: the trigger leads."""
    return f"{trigger}. {pose_text} She is {outfit_text}. {LOOK}"


def generate(cfg, client, source: Path, trigger: str, pose_text: str, outfit_text: str,
             lora: str, out_dir: Path, *, count: int = 30, seed: int = 5500,
             lora_strength: float = LORA_STRENGTH, render_pass: str = "medium",
             scorer=None, log=print) -> list[dict]:
    """Generate `count` candidates and score each against the source face.

    Returns rows sorted best-first. Selection is the point: the caller keeps the
    top few and discards the rest, which is why nothing here tries to salvage a
    weak generation.
    """
    from .transfer import composite_on_plate  # noqa: PLC0415

    out_dir = Path(out_dir)
    work = out_dir / "_work"
    work.mkdir(parents=True, exist_ok=True)

    plate = work / f"{source.stem}_plate.png"
    composite_on_plate(source, plate)
    image_name = client.upload_image(plate)
    prompt = compose_prompt(trigger, pose_text, outfit_text)

    ref = scorer(source) if scorer else None
    rows = []
    for i in range(count):
        s = seed + i * 137
        nodes = build_native_workflow(cfg, image_name, prompt, s,
                                      prefix=f"native/{source.stem}", lora=lora,
                                      lora_strength=lora_strength, render_pass=render_pass)
        files = client.outputs(client.wait(client.submit(nodes)))
        if not files:
            log(f"  seed {s}: no output")
            continue
        dest = out_dir / f"{source.stem}_s{s}.png"
        client.fetch(files[0], dest)
        score = None
        if scorer and ref is not None:
            cand = scorer(dest)
            score = float(cand @ ref) if cand is not None else None
        rows.append({"file": dest.name, "seed": s, "face": round(score, 4) if score else None})
        log(f"  seed {s}: {'face %.3f' % score if score else 'generated'}")

    scored = [r for r in rows if r["face"] is not None]
    scored.sort(key=lambda r: -r["face"])
    return scored or rows
