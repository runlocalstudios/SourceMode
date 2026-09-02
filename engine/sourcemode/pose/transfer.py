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

from .face import crop_face, mask_reference_face, paste_face
from .library import POSES, gates
from .skeleton import draw_skeleton
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
    "identical parting, identical colour, falling the same way. It keeps exactly the length "
    "it has in image 1, at the back of her head as well as the front, neither lengthened nor "
    "shortened."
)

# How the hair is GATHERED is a structural detail on the side the source never
# shows, so a rear view has to invent it — and it defaults to a single tail.
# Two low pigtails reliably collapsed into one ponytail with the generic
# instruction above. The style therefore cannot be inferred; it has to be
# stated per asset, and only when it is actually true: naming a style that is
# not there introduces it (see the braid incident in git history).
HAIR_HINT = (
    " In image 1 her hair is worn in {hair}, and it stays in exactly that style from every "
    "angle, including from behind. Do not gather it differently, do not merge it, do not let "
    "it down."
)
NEGATIVE = (
    "different outfit, different clothing, wardrobe change, changed colours, "
    "restyled hair, different hairstyle, changed hair, shorter hair, cropped hair, "
    "hair length changed, different hair colour, "
    "nude, explicit, worst quality, low quality, deformed, ugly, extra limbs, "
    "distorted hands, blurry, cartoon, anime, watermark, text"
)


# --- second pass: put the original head back --------------------------------
# The pose pass regenerates the whole figure, so the face and hair are redrawn
# from scratch every time. Hair is where that shows: pigtails came back loose on
# roughly 8 of 11 checked assets, and a hair bow vanished. Saying it harder in
# the pose prompt does not fix it — by then the model is solving a different
# problem (match this pose) and the hair is collateral.
#
# So identity is restored in a SEPARATE pass. image1 is the posed result, which
# pins the pose, body and wardrobe; image2 is the original asset, which supplies
# the face and hair. It runs through qwen_image_edit_ref, NOT the AnyPose graph:
# AnyPose exists to move a pose and is exactly what must not happen here.
#
# Still no hairstyle is ever named — the reference image carries the style, and
# naming one introduces it (see the braid incident).
REFINE_INSTRUCTION = (
    "Image 1 and image 2 are the same woman. Keep image 1 exactly as it is: the same pose, the "
    "same position of her arms and legs, the same clothing and shoes, the same framing, the "
    "same background. Do not move her and do not change her outfit. "
    "Correct only her head. Her face must match image 2 exactly — the same facial features, "
    "the same face shape, the same skin tone. Her hair must match image 2 exactly: worn the "
    "same way, gathered exactly as image 2 shows it, the same length, the same colour, the same "
    "parting, and any hair ties, clips or accessories in image 2 are present and identical."
)
REFINE_NEGATIVE = (
    "different pose, moved arms, moved legs, changed body position, different clothing, "
    "different outfit, changed background, different person, different face, different "
    "hairstyle, changed hair colour, blurry, deformed, distorted hands, extra limbs, "
    "cartoon, anime, watermark, text"
)
# A refine that improves the face but quietly straightens the pose is a
# regression, so pose similarity is allowed to fall only this far.
REFINE_POSE_TOLERANCE = 0.05
# InsightFace scores which candidate to keep. Its weights are non-commercial, so
# this is tooling only: it selects an image, it never ships inside one.
REFINE_MIN_GAIN = 0.005


def build_refine_workflow(cfg: dict, posed_name: str, source_name: str, seed: int,
                          prefix: str) -> dict:
    """Two-image identity restore. Deliberately NOT the AnyPose graph."""
    from ..config import workflows_dir  # noqa: PLC0415
    from ..render.workflow import load_template, prune_placeholder_loras, substitute  # noqa: PLC0415

    preset = cfg["render"]["draft"]
    settings = {
        "MODEL": cfg["models"]["qwen_edit"],
        "TEXT_ENCODER": cfg["models"]["qwen_text_encoder"],
        "VAE": cfg["models"]["qwen_vae"],
        "POSITIVE": REFINE_INSTRUCTION,
        "NEGATIVE": REFINE_NEGATIVE,
        "IMAGE": posed_name, "REF_IMAGE": source_name,
        "LORA_PATH": "", "LORA_STRENGTH": 1.0,
        "LIGHTNING": preset["qwen_edit_lightning"], "LIGHTNING_STRENGTH": 1.0,
        "SHIFT": float(cfg["render"]["qwen_shift"]),
        "SEED": seed,
        "STEPS": int(preset["qwen_edit_steps"]),
        "CFG": float(preset["qwen_edit_cfg"]),
        "FILENAME_PREFIX": prefix,
    }
    nodes = prune_placeholder_loras(
        substitute(load_template(workflows_dir(cfg), "qwen_image_edit_ref"), settings))
    loaded = {n["inputs"].get("lora_name") for n in nodes.values()
              if n["class_type"] == "LoraLoaderModelOnly"}
    assert ANYPOSE_BASE not in loaded, "refine must not run the AnyPose LoRAs"
    return nodes


def refine_head(cfg, client, posed: Path, source_plate: Path, source_asset: Path,
                work: Path, model_path: str, *, candidates: int = 3, seed: int = 0,
                log=print) -> tuple[Path, str]:
    """Restore face and hair from the source. Returns (best, note).

    Returns the ORIGINAL posed image when no candidate is a genuine improvement.
    A second pass that makes things worse is worse than no second pass, and this
    one can decline.
    """
    from ..gates.identity import cosine, embed_image, insightface_available  # noqa: PLC0415

    if not insightface_available():
        return posed, "refine skipped (no insightface)"

    ref_emb = embed_image(source_asset)
    base_emb = embed_image(posed)
    if ref_emb is None:
        return posed, "refine skipped (no face in source)"
    base_id = cosine(ref_emb, base_emb) if base_emb is not None else 0.0
    base_pose = measure(posed, model_path)

    posed_name = client.upload_image(posed)
    source_name = client.upload_image(source_plate)

    best, best_id = posed, base_id
    tried = []
    for c in range(max(1, candidates)):
        nodes = build_refine_workflow(cfg, posed_name, source_name, seed + c * 61,
                                      prefix=f"poserefine/{posed.stem}")
        files = client.outputs(client.wait(client.submit(nodes)))
        if not files:
            continue
        cand = work / f"{posed.stem}_refine{c}.png"
        client.fetch(files[0], cand)

        emb = embed_image(cand)
        if emb is None:
            tried.append("noface")
            continue
        ident = cosine(ref_emb, emb)
        # reject anything that straightened the pose while fixing the face
        pose_keep = 1.0
        m = measure(cand, model_path)
        if m and base_pose:
            pose_keep = pose_similarity(m, base_pose)["score"]
        tried.append(f"{ident:.3f}{'' if pose_keep >= 1 - REFINE_POSE_TOLERANCE else '/posedrift'}")
        if pose_keep < 1 - REFINE_POSE_TOLERANCE:
            continue
        if ident > best_id + REFINE_MIN_GAIN:
            best, best_id = cand, ident

    if best is posed:
        return posed, f"refine declined (face {base_id:.3f}; tried {', '.join(tried) or 'none'})"
    return best, f"refine {base_id:.3f}->{best_id:.3f}"


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


# Directory names that describe the pipeline rather than the subject, so they
# never help identify whose asset this is.
_GENERIC_DIRS = {"output", "outputs", "game-asset-gen", "cutouts", "candidates",
                 "assets", "art-source", "characters"}


def asset_label(source: Path) -> str:
    """Name the collection a source asset belongs to, e.g. 'priyanka_weekly_casual'.

    Results used to be named from the source FILENAME alone, which silently
    destroyed work: maya and priyanka both have weekly_casual/casual_01_standing,
    so the second run overwrote the first result and nothing said so. Found by
    running the pose across the cast.

    The label is the nearest ancestor directory that names something real (the
    character) plus the immediate folder (the outfit), skipping pipeline
    directories in between.
    """
    outfit = source.parent.name
    for ancestor in source.parent.parents:
        name = ancestor.name
        if name and name.lower() not in _GENERIC_DIRS:
            return f"{name}_{outfit}" if name != outfit else name
    return outfit or "unlabelled"


# Footwear is the other thing the source cannot show. These assets are cropped
# for the game UI, so feet are usually missing or half-cut, and the model then
# takes whatever the reference did — every barefoot reference produced barefoot
# results, and zara's half-visible boots became detached brown blobs beside her
# hips once the pose moved her feet behind her.
#
# So footwear is CHOSEN from the outfit rather than guessed per render. A plain
# mapping, not a model call: it costs nothing, and more importantly it is
# deterministic, so one outfit gets the same shoes in every pose and every rerun.
# That consistency is the point — an outfit that changes shoes between poses is
# worse than one wearing the wrong shoes.
#
# Boots are deliberately absent: they are only correct when the source actually
# shows them, and in that case the "keep what is visible" clause already wins.
# Slippers are here for the at-home outfits that don't exist yet.
FOOTWEAR = {
    "workout": "clean white athletic running trainers",       # before "work" — substring clash
    "work": "plain black high-heeled court shoes",
    "work_alternates": "plain black high-heeled court shoes",
    "work_options": "plain black high-heeled court shoes",
    "fancy_dining_gallery": "elegant strappy high-heeled sandals",
    "fancy_town": "elegant strappy high-heeled sandals",
    "casual_date": "black platform shoes",
    "weekly_casual": "clean white low-top sneakers",
}
FOOTWEAR_DEFAULT = "simple plain flat shoes"
# Vocabulary the mapping is allowed to draw from, per the brief: sneakers,
# slippers, platforms, high heels, and boots only when already visible.
FOOTWEAR_VOCAB = ("sneakers", "trainers", "slippers", "platform", "heel", "flat")

# Ordered so that anything genuinely visible in image 1 wins outright; the
# chosen pair only fills in feet the source never showed.
FOOTWEAR_HINT = (
    " Whatever footwear can be seen in image 1 is kept exactly as it is there — the same "
    "style, the same colour, the same height — and is completed naturally where the pose now "
    "shows more of it. Only where image 1 shows no footwear at all does she wear {shoes}. "
    "Her shoes are a matching pair, both the same, and sit properly on her feet."
)


def footwear_for(source: Path) -> str:
    """Pick the footwear for an asset from its outfit folder. Deterministic."""
    outfit = source.parent.name.lower()
    if outfit in FOOTWEAR:
        return FOOTWEAR[outfit]
    # longest first, so "workout" is never matched by "work"
    for key in sorted(FOOTWEAR, key=len, reverse=True):
        if key in outfit:
            return FOOTWEAR[key]
    return FOOTWEAR_DEFAULT


def build_workflow(cfg: dict, init_name: str, ref_name: str, seed: int, prefix: str,
                   hair: str | None = None, shoes: str | None = None,
                   skeleton_name: str | None = None, render_pass: str = "draft") -> dict:
    from ..config import workflows_dir  # noqa: PLC0415
    from ..render.workflow import load_template, prune_placeholder_loras, substitute  # noqa: PLC0415

    # AnyPose's card recommends the 4-step lightning path, and that is the
    # default. But distillation is also where skin texture goes: the pose pass
    # alone strips ~17% of the face's high-frequency detail against the source,
    # which is the "airbrushed" look. render_pass="medium" drops lightning and
    # runs full steps at real CFG so that can be traded off deliberately.
    preset = cfg["render"][render_pass]
    settings = {
        "MODEL": cfg["models"]["qwen_edit"],
        "TEXT_ENCODER": cfg["models"]["qwen_text_encoder"],
        "VAE": cfg["models"]["qwen_vae"],
        "POSITIVE": (INSTRUCTION + (HAIR_HINT.format(hair=hair) if hair else "")
                     + (FOOTWEAR_HINT.format(shoes=shoes) if shoes else "")),
        "NEGATIVE": NEGATIVE,
        "IMAGE": init_name, "REF_IMAGE": ref_name,
        "LORA_PATH": "", "LORA_STRENGTH": 1.0,  # no character LoRA -> slot pruned
        "ANYPOSE_BASE": ANYPOSE_BASE, "ANYPOSE_BASE_STRENGTH": ANYPOSE_STRENGTH,
        "ANYPOSE_HELPER": ANYPOSE_HELPER, "ANYPOSE_HELPER_STRENGTH": ANYPOSE_STRENGTH,
        # empty lightning prunes the node entirely (see prune_placeholder_loras)
        "LIGHTNING": preset.get("qwen_edit_lightning", ""),
        "LIGHTNING_STRENGTH": 1.0 if preset.get("qwen_edit_lightning") else 0.0,
        "SHIFT": float(cfg["render"]["qwen_shift"]),
        "SEED": seed,
        "STEPS": int(preset["qwen_edit_steps"]),
        "CFG": float(preset["qwen_edit_cfg"]),
        "FILENAME_PREFIX": prefix,
    }
    nodes = prune_placeholder_loras(substitute(load_template(workflows_dir(cfg), "qwen_image_edit_anypose"), settings))
    if skeleton_name:
        # image3 = stick figure. Added here rather than in the template so the
        # template stays valid when no skeleton is used: an unfilled LoadImage
        # would fail the whole graph. Mirrors the existing
        # LoadImage -> FluxKontextImageScale -> image slot wiring.
        nodes["902"] = {"class_type": "LoadImage", "inputs": {"image": skeleton_name}}
        nodes["903"] = {"class_type": "FluxKontextImageScale", "inputs": {"image": ["902", 0]}}
        for nid, node in nodes.items():
            if node["class_type"] == "TextEncodeQwenImageEditPlus":
                node["inputs"]["image3"] = ["903", 0]
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
             seed: int = 8801, hair: str | None = None, shoes: str | None = None,
             no_shoes: bool = False, refine: bool = False, mask_reference: bool = True,
             skeleton: bool = False, render_pass: str = "draft", log=print) -> int:
    """Run pose transfer over a list of source assets. Returns the success count."""
    pose = POSES[pose_key]
    variants = pose["variants"]
    rng = random.Random(seed)
    tmp, cand_dir = out_dir / "_work", out_dir / "_candidates"
    for d in (out_dir, tmp, cand_dir):
        d.mkdir(parents=True, exist_ok=True)

    uploaded_refs: dict[str, str] = {}
    uploaded_skels: dict[str, str] = {}
    ref_metrics: dict[str, dict] = {}
    ok = 0

    for i, path in enumerate(sources):
        started = time.monotonic()
        chosen = variant or rng.choice(list(variants))
        # Explicit --shoes wins; otherwise the outfit decides, deterministically,
        # so the same outfit wears the same pair in every pose. --no-shoes leaves
        # feet entirely to the source and the reference, as before.
        pick_shoes = None if no_shoes else (shoes or footwear_for(path))
        ref_path = library / f"{pose_key}_{chosen}.png"
        if not ref_path.exists():
            log(f"  !! missing reference {ref_path.name} — run make-ref first")
            continue
        if chosen not in uploaded_refs:
            # The reference is a photograph of a DIFFERENT woman, and her face
            # is handed to the model on every render, competing with the
            # character's. Mask it. Gates still measure the ORIGINAL, which
            # still has the face the metrics were calibrated on.
            to_upload = ref_path
            if mask_reference:
                masked = tmp / f"{ref_path.stem}_masked.png"
                if mask_reference_face(ref_path, masked, model_path):
                    to_upload = masked
                else:
                    log(f"  !! no face found in {ref_path.name}; using it unmasked")
            uploaded_refs[chosen] = client.upload_image(to_upload)
            ref_metrics[chosen] = measure(ref_path, model_path)
            if skeleton:
                skel = tmp / f"{ref_path.stem}_skeleton.png"
                if draw_skeleton(ref_path, model_path, skel):
                    uploaded_skels[chosen] = client.upload_image(skel)
                else:
                    log(f"  !! could not build a skeleton for {ref_path.name}")

        plate = tmp / f"{path.stem}_plate.png"
        size = composite_on_plate(path, plate)
        init_name = client.upload_image(plate)

        rendered: list[Path] = []
        for c in range(max(1, candidates)):
            nodes = build_workflow(cfg, init_name, uploaded_refs[chosen],
                                   seed=seed + i * 100 + c, prefix=f"posetransfer/{path.stem}",
                                   hair=hair, shoes=pick_shoes,
                                   skeleton_name=uploaded_skels.get(chosen),
                                   render_pass=render_pass)
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

        # Namespaced by asset_label so two characters sharing an outfit slug
        # cannot overwrite each other's results.
        if refine:
            best, note = refine_head(cfg, client, best, plate, path, tmp, model_path,
                                     seed=seed + i * 100, log=log)
            detail += f"  {note}"

        final_dir = out_dir / asset_label(path)
        final_dir.mkdir(parents=True, exist_ok=True)
        final = final_dir / f"{path.stem.replace('_standing', '')}_{pose['suffix']}_{chosen}.webp"
        cut_out(best, final, size)
        ok += 1
        log(f"  [{ok}/{len(sources)}] {chosen:20} {final.name}{detail}  {time.monotonic() - started:.0f}s")

    return ok
