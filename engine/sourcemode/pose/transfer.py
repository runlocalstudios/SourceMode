"""Pose transfer: same character, same outfit, new pose. No character LoRA.

Qwen-Image-Edit-2511 + the AnyPose LoRA pair (base + helper, both 0.7) on the
4-step lightning path. image1 is the character, image2 is a reference photo of
the target pose. AnyPose is trained for pose transfer and needs no ControlNet
or OpenPose skeleton, which matters because 2511 regressed the skeleton
conditioning 2509 had.

Identity comes from image1, so this works for characters that have no LoRA —
which is the whole point. Body ORIENTATION is part of a pose, so a rear-facing
reference produces a rear-facing character with the unseen side of the garment
inferred; no per-outfit rear assets are needed.

Tried and rejected, so they are not tried again:
  - plain instruct-editing without AnyPose: invented shoes, mangled hands, left
    a void at the chest, and smeared a 0.08% teal detail into 0.95% cyan patches
  - ControlNet img2img: at low denoise the pose never moved, at high denoise the
    face became a different person. No denoise value held both.
"""

from __future__ import annotations

import random
import time
from pathlib import Path

from .library import POSES, gates
from .metrics import measure, pose_similarity, score_against

ANYPOSE_BASE = r"anypose\2511-AnyPose-base-000006250.safetensors"
ANYPOSE_HELPER = r"anypose\2511-AnyPose-helper-00006000.safetensors"
ANYPOSE_STRENGTH = 0.7  # per the AnyPose model card

# The pose is the headline ask, but keeping the wardrobe is why this exists.
POSE_WEIGHT, OUTFIT_WEIGHT = 0.6, 0.4
PLATE = (128, 128, 128)  # neutral against light and dark wardrobes alike
REF_CANDIDATES = 6

# Body of the instruction is verbatim from the AnyPose model card — blunt and
# repetitive on purpose; gentler prose consistently under-moved the pose.
# The HAIR clause is an addition: the card's prompt protects the pose but says
# nothing about hair, and on rear views the hair is exactly what drifts, since
# the source never showed the back of it. Pigtails came apart and lengths
# shortened until this was stated.
#
# It must NOT name any hairstyle. A first attempt said "if her hair is tied in
# pigtails, a ponytail or a braid, keep that style intact" and the model put a
# braid on characters whose hair was loose in the source — the same failure as
# naming a stepladder to describe a camera position. Assert only that the hair
# is unchanged; never enumerate styles, in the positive or the negative, or
# they get introduced or stripped depending on which list they land in.
INSTRUCTION = (
    "Make the person in image 1 do the exact same pose of the person in image 2. "
    "Changing the style and background of the image of the person in image 1 is "
    "undesirable, so don't do it. The new pose should be pixel accurate to the pose "
    "we are trying to copy. The position of the arms and head and legs should be the "
    "same as the pose we are trying to copy. Change the field of view and angle to "
    "match exactly image 2. Head tilt and eye gaze pose should match the person in image 2. "
    "Her hair is exactly as it is in image 1 and must not be restyled: identical length, "
    "identical parting, identical colour, falling the same way. Hair that is long in image 1 "
    "is equally long at the back of her head."
)
NEGATIVE = (
    "different outfit, different clothing, wardrobe change, changed colours, "
    "restyled hair, different hairstyle, changed hair, shorter hair, cropped hair, "
    "hair length changed, different hair colour, "
    "nude, explicit, worst quality, low quality, deformed, ugly, extra limbs, "
    "distorted hands, blurry, cartoon, anime, watermark, text"
)


def composite_on_plate(src: Path, dest: Path) -> tuple[int, int]:
    """RGBA cutout -> flat grey plate. Returns the source size."""
    from PIL import Image  # noqa: PLC0415

    img = Image.open(src).convert("RGBA")
    plate = Image.new("RGB", img.size, PLATE)
    plate.paste(img, mask=img.getchannel("A"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    plate.save(dest)
    return img.size


def cut_out(src: Path, dest: Path, size: tuple[int, int] | None = None) -> None:
    """Restore the alpha cutout and put it back on the source's pixel grid.

    alpha_matting is on because a plain cut left coloured fringing along hair
    and clothing edges; matting refines the boundary band instead of keying it.
    """
    from PIL import Image  # noqa: PLC0415
    from rembg import remove  # noqa: PLC0415

    out = remove(
        Image.open(src).convert("RGBA"),
        alpha_matting=True,
        alpha_matting_foreground_threshold=240,
        alpha_matting_background_threshold=10,
        alpha_matting_erode_size=10,
    )
    if size and out.size != size:
        # Qwen rescales to ~1MP; restore the asset grid so results drop straight in
        out = out.resize(size, Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.save(dest)


def outfit_fidelity(source: Path, candidate: Path) -> float:
    """Palette similarity over the torso band (0..1).

    A whole-figure colour histogram does NOT work and was tried: two genuinely
    different outfits scored 0.635 while real candidates scored 0.39-0.59,
    because the histogram is dominated by how much skin and background shows,
    and changing the pose moves that far more than changing clothes does.
    Looking only at the torso band, and at WHICH colours are present rather
    than how much of each, separates them properly.
    """
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    def palette(path: Path, k: int = 10):
        im = Image.open(path).convert("RGBA")
        im.thumbnail((200, 200))
        a = np.array(im)
        ys, xs = np.where(a[..., 3] > 200)
        if len(ys) < 200:
            return None
        y0, height = ys.min(), ys.max() - ys.min()
        band = (ys > y0 + 0.20 * height) & (ys < y0 + 0.62 * height)  # skip head and legs
        rgb = a[..., :3][ys[band], xs[band]].astype(float)
        if len(rgb) < 50:
            return None
        q = (rgb // 32).astype(int)
        counts = np.bincount(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2], minlength=512)
        top = [t for t in np.argsort(counts)[::-1][:k] if counts[t] > 0]
        cols = np.array([[(t // 64) * 32 + 16, ((t // 8) % 8) * 32 + 16, (t % 8) * 32 + 16] for t in top], float)
        w = np.array([counts[t] for t in top], float)
        return cols, w / w.sum()

    a, b = palette(source), palette(candidate)
    if a is None or b is None:
        return 0.0
    src_cols, src_w = a
    cand_cols, _ = b
    return float(sum(
        w * max(0.0, 1.0 - float(np.linalg.norm(cand_cols - c, axis=1).min()) / 120.0)
        for c, w in zip(src_cols, src_w)
    ))


def build_workflow(cfg: dict, init_name: str, ref_name: str, seed: int, prefix: str) -> dict:
    from ..config import workflows_dir  # noqa: PLC0415
    from ..render.workflow import load_template, prune_placeholder_loras, substitute  # noqa: PLC0415

    preset = cfg["render"]["draft"]  # AnyPose is tuned for the 4-step lightning path
    settings = {
        "MODEL": cfg["models"]["qwen_edit"],
        "TEXT_ENCODER": cfg["models"]["qwen_text_encoder"],
        "VAE": cfg["models"]["qwen_vae"],
        "POSITIVE": INSTRUCTION, "NEGATIVE": NEGATIVE,
        "IMAGE": init_name, "REF_IMAGE": ref_name,
        "LORA_PATH": "", "LORA_STRENGTH": 1.0,  # no character LoRA -> slot pruned
        "ANYPOSE_BASE": ANYPOSE_BASE, "ANYPOSE_BASE_STRENGTH": ANYPOSE_STRENGTH,
        "ANYPOSE_HELPER": ANYPOSE_HELPER, "ANYPOSE_HELPER_STRENGTH": ANYPOSE_STRENGTH,
        "LIGHTNING": preset["qwen_edit_lightning"], "LIGHTNING_STRENGTH": 1.0,
        "SHIFT": float(cfg["render"]["qwen_shift"]),
        "SEED": seed,
        "STEPS": int(preset["qwen_edit_steps"]),
        "CFG": float(preset["qwen_edit_cfg"]),
        "FILENAME_PREFIX": prefix,
    }
    nodes = prune_placeholder_loras(substitute(load_template(workflows_dir(cfg), "qwen_image_edit_anypose"), settings))
    loaded = {n["inputs"]["lora_name"] for n in nodes.values() if n["class_type"] == "LoraLoaderModelOnly"}
    assert ANYPOSE_BASE in loaded and ANYPOSE_HELPER in loaded, f"AnyPose LoRAs missing: {loaded}"
    return nodes


def make_reference(cfg, client, pose_key: str, variant: str, library: Path,
                   model_path: str, seed: int, log=print) -> Path:
    """Render candidate references, measure each, keep the best that passes."""
    from ..render.passes import build_keyframe_workflow  # noqa: PLC0415
    from ..source import CharacterSource  # noqa: PLC0415

    pose = POSES[pose_key]
    target, limits, weights = gates(pose)
    blank = CharacterSource(character_id="poseref", name="Pose Ref", version="v001",
                            trigger_token="poseref")
    work = library / "_candidates"
    work.mkdir(parents=True, exist_ok=True)

    ranked, measured = [], []
    for c in range(REF_CANDIDATES):
        nodes, _ = build_keyframe_workflow(
            cfg, blank,
            positive=pose["ref_prompt"].format(arms=pose["variants"][variant]),
            negative=pose["ref_negative"],
            seed=seed + c * 137, render_pass="medium", width=896, height=1152,
        )
        files = client.outputs(client.wait(client.submit(nodes)))
        if not files:
            continue
        dest = work / f"{pose_key}_{variant}_c{c}.png"
        client.fetch(files[0], dest)
        m = measure(dest, model_path)
        measured.append((dest, m))
        s = score_against(m, target, limits, weights) if m else None
        if m:
            shown = " ".join(f"{k}={m[k]:.2f}" for k in target if k in m)
            log(f"    c{c}: {shown}  {'REJECT' if s is None else f'score={s:.3f}'}")
        if s is not None:
            ranked.append((s, dest, m))

    if not ranked:
        # Never lose a whole run to one stubborn variant: fall back to the
        # nearest candidate and say so loudly so it gets reviewed.
        scored = [(sum(abs(m[k] - target[k]) for k in target if k in m), p, m) for p, m in measured if m]
        if not scored:
            raise RuntimeError(f"{pose_key}/{variant}: no candidate could be measured")
        scored.sort(key=lambda t: t[0])
        _, best, m = scored[0]
        log(f"  !! {variant}: every candidate failed the gates; using the closest — REVIEW THIS ONE")
        ranked = [(999.0, best, m)]

    ranked.sort(key=lambda t: t[0])
    s, best, m = ranked[0]
    final = library / f"{pose_key}_{variant}.png"
    final.parent.mkdir(parents=True, exist_ok=True)
    if final.exists():  # an approved reference is the expensive artefact here
        (library / "_prev").mkdir(exist_ok=True)
        (library / "_prev" / f"{final.stem}_{time.strftime('%H%M%S')}.png").write_bytes(final.read_bytes())
    final.write_bytes(best.read_bytes())
    log(f"  -> {variant}: score={s:.3f} " + " ".join(f"{k}={m[k]:.2f}" for k in target if k in m))
    return final


def transfer(cfg, client, sources: list[Path], pose_key: str, library: Path, out_dir: Path,
             model_path: str, *, variant: str | None = None, candidates: int = 4,
             seed: int = 8801, log=print) -> int:
    """Run pose transfer over a list of source assets. Returns the success count."""
    pose = POSES[pose_key]
    variants = pose["variants"]
    rng = random.Random(seed)
    tmp, cand_dir = out_dir / "_work", out_dir / "_candidates"
    for d in (out_dir, tmp, cand_dir):
        d.mkdir(parents=True, exist_ok=True)

    uploaded_refs: dict[str, str] = {}
    ref_metrics: dict[str, dict] = {}
    ok = 0

    for i, path in enumerate(sources):
        started = time.monotonic()
        chosen = variant or rng.choice(list(variants))
        ref_path = library / f"{pose_key}_{chosen}.png"
        if not ref_path.exists():
            log(f"  !! missing reference {ref_path.name} — run make-ref first")
            continue
        if chosen not in uploaded_refs:
            uploaded_refs[chosen] = client.upload_image(ref_path)
            ref_metrics[chosen] = measure(ref_path, model_path)

        plate = tmp / f"{path.stem}_plate.png"
        size = composite_on_plate(path, plate)
        init_name = client.upload_image(plate)

        rendered: list[Path] = []
        for c in range(max(1, candidates)):
            nodes = build_workflow(cfg, init_name, uploaded_refs[chosen],
                                   seed=seed + i * 100 + c, prefix=f"posetransfer/{path.stem}")
            files = client.outputs(client.wait(client.submit(nodes)))
            if not files:
                continue
            dest = cand_dir / f"{path.stem}_{chosen}_c{c}.png"
            client.fetch(files[0], dest)
            rendered.append(dest)

        if not rendered:
            log(f"  !! no output for {path.name}")
            continue

        best, detail = rendered[0], ""
        if len(rendered) > 1 and ref_metrics.get(chosen):
            scored = {}
            for cand in rendered:
                m = measure(cand, model_path)
                p_s = pose_similarity(m, ref_metrics[chosen])["score"] if m else 0.0
                o_s = outfit_fidelity(path, cand)
                scored[cand] = POSE_WEIGHT * p_s + OUTFIT_WEIGHT * o_s
            best = max(scored, key=scored.get)
            others = sorted((v for k, v in scored.items() if k != best), reverse=True)
            detail = f"  score {scored[best]:.3f} (beat {', '.join(f'{s:.2f}' for s in others)})"

        final = out_dir / f"{path.stem.replace('_standing', '')}_{pose['suffix']}_{chosen}.webp"
        cut_out(best, final, size)
        ok += 1
        log(f"  [{ok}/{len(sources)}] {chosen:20} {final.name}{detail}  {time.monotonic() - started:.0f}s")

    return ok
