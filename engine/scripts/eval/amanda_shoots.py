"""Six risque photo shoots of Amanda on the local recipe (arm C: hair seed + one
reference + text), ~96 shots, for Jeremy to review while the card is otherwise idle
(2026-10-01). Fitted / revealing wardrobe by design - these are the shots that show
her build. Appearance clause from characters/appearance.json in every prompt.
Output: outputs/loragen_local/amanda_shoots/<shoot>_<nn>.png + judge set shoot_amanda.
"""
import json
import random
from pathlib import Path

import numpy as np
from PIL import Image

from sourcemode.assets.judge import make_set
from sourcemode.config import load_config, workflows_dir
from sourcemode.gates.identity import _get_face_app, embed_image
from sourcemode.render.client import ComfyUIClient
from sourcemode.render.workflow import load_template, substitute

CHAR = "amanda"
REFS = Path("C:/Epic Games/Files/cnc info/codex/references")
SEEDS = Path("outputs/seeds/amanda")
COMFY_IN = Path("C:/ComfyUI/input")
OUT = Path("outputs/loragen_local/amanda_shoots")
OUT.mkdir(parents=True, exist_ok=True)
NEG = ("different person, different face, deformed, distorted hands, extra limbs, "
       "plastic skin, doll-like, blurry, low quality, cartoon, watermark, text")
from sourcemode.assets.appearance import clause as _clause
APP = _clause(CHAR)
HAIR = {"loose": "her hair worn loose", "ponytail": "her hair pulled back in a high ponytail",
        "halfup": "her hair half pinned back", "bun": "her hair up in a messy bun"}

SHOOTS = {
    "boudoir": {
        "setting": "in a softly lit bedroom with white sheets and warm lamplight",
        "light": "warm soft lamplight",
        "outfits": ["a black lace bralette and matching panties", "a sheer white lace bodysuit", "a burgundy satin slip",
                    "a black strappy lingerie set", "an oversized white shirt unbuttoned over black lace underwear",
                    "a pale pink silk camisole and shorts"],
        "poses": ["sitting on the edge of the bed, one knee drawn up", "kneeling on the bed, back slightly arched",
                  "lying on her side propped on one elbow", "standing by the bed, one strap slipped off her shoulder",
                  "sitting back on her heels on the bed, hands on her thighs", "leaning forward toward the camera on the bed"]},
    "pool": {
        "setting": "beside a sunlit pool with turquoise water and a white lounger",
        "light": "soft open shade",
        "outfits": ["a tiny white string bikini", "a black cut-out one-piece swimsuit", "a red triangle bikini",
                    "a metallic gold bikini", "a sheer sarong over a white bikini", "a leopard-print bikini"],
        "poses": ["standing at the pool edge, hair pushed back", "sitting on the lounger, legs stretched out",
                  "leaning back on her hands at the pool edge", "stepping out of the water",
                  "lying on the lounger, looking at the camera", "standing three-quarter turned, looking back at the camera"]},
    "mirror": {
        "setting": "in a bright bathroom, taking a mirror selfie with her phone",
        "light": "soft bathroom vanity light",
        "outfits": ["a white crop top and tiny shorts", "a black sports bra and thong", "a towel wrapped around her chest",
                    "a sheer mesh top over a black bra", "a fitted ribbed bodysuit", "a lace bralette and jeans unbuttoned"],
        "poses": ["holding the phone at chest height, hip pushed out", "phone held up high, looking at the screen",
                  "turned to show her profile in the mirror", "leaning toward the mirror",
                  "one hand lifting the hem of her top", "standing square to the mirror"]},
    "gym": {
        "setting": "in a modern gym with mirrors and black equipment",
        "light": "cool even gym lighting",
        "outfits": ["a tiny black sports bra and high-waisted leggings", "a white sports bra and grey biker shorts",
                    "a cropped tank top knotted at the ribs and leggings", "a mint green sports bra and matching shorts",
                    "a sheer mesh crop top over a sports bra", "a one-shoulder athletic bra and leggings"],
        "poses": ["stretching with her arms over her head", "sitting on a bench, leaning forward on her knees",
                  "standing with a towel around her neck", "mid-squat looking at the camera",
                  "wiping sweat from her brow", "leaning against the mirror wall, one knee bent"]},
    "silk": {
        "setting": "in a dim hotel room with city lights out the window",
        "light": "low moody window light",
        "outfits": ["a short black silk robe loosely tied", "an emerald silk robe slipping off one shoulder",
                    "a champagne silk nightgown with a deep neckline", "a black mesh bodysuit under an open robe",
                    "a white silk robe held closed with one hand", "a red satin teddy"],
        "poses": ["standing at the window, looking back over her shoulder", "sitting in an armchair, legs crossed",
                  "leaning in the doorway", "sitting on the windowsill", "walking toward the camera",
                  "lying across the bed on her stomach, chin on her hands"]},
    "beach_sunset": {
        "setting": "on a beach at sunset, golden light, waves behind her",
        "light": "golden-hour backlight",
        "outfits": ["a white crochet bikini", "a white t-shirt knotted over a black bikini", "a black bikini with a sheer cover-up",
                    "an orange bikini", "a tied-up shirt and bikini bottoms", "a pink bikini top and denim cut-offs"],
        "poses": ["walking out of the surf", "kneeling in the sand", "standing with the wind in her hair",
                  "sitting in the shallow water", "arching back with her hands in her hair",
                  "looking over her shoulder, walking away"]},
}
AZ = ["front", "front-left quarter", "front-right quarter", "front", "front-left quarter", "front-right quarter"]
DIST = ["medium shot", "medium shot", "close-up", "medium shot", "medium shot", "close-up"]
STYLES = ["loose", "ponytail", "halfup", "bun"]
EXPR = ["a playful smile", "a soft smile", "a sultry look at the camera", "biting her lip",
        "laughing", "a confident gaze", "a relaxed expression"]


def stage(p: Path) -> str:
    d = COMFY_IN / p.name
    if not d.exists():
        d.write_bytes(p.read_bytes())
    return p.name


seeds = {st: stage(next(SEEDS.glob(f"{CHAR}_seed_{st}.*"))) for st in STYLES}
face = stage(REFS / "amanda_face.jpg")
cfg = load_config()
client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
app = _get_face_app()
refemb = [e for e in (embed_image(REFS / n) for n in ("amanda_face.jpg", "amanda_portrait1.jpg", "amanda_portrait2.jpg"))
          if e is not None]


def measure(path: Path) -> dict:
    im = Image.open(path).convert("RGB")
    fs = app.get(np.asarray(im)[:, :, ::-1])
    if not fs:
        return {}
    f = max(fs, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
    return {"self": round(max(float(e @ f.normed_embedding) for e in refemb), 3),
            "bucket_px": round(float(f.bbox[3] - f.bbox[1]) / im.height * 1536)}


rng = random.Random(7)
rows, k = [], 0
for shoot, S in SHOOTS.items():
    for i in range(16):
        outfit = S["outfits"][i % 6]
        pose = S["poses"][(i // 6 + i) % 6]
        st = STYLES[k % 4]
        az, dist = AZ[i % 6], DIST[i % 6]
        expr = rng.choice(EXPR)
        prompt = (f"<sks> {az} view eye-level shot {dist}, {APP}, {HAIR[st]}, wearing {outfit}, {pose}, {expr}, "
                  f"{S['light']}, {S['setting']}")
        dest = OUT / f"{shoot}_{i:02d}.png"
        if not dest.exists():
            wf = substitute(load_template(workflows_dir(cfg), "qwen_multiangle_ref"), {
                "REF1": seeds[st], "REF2": face, "REF3": face, "POSITIVE": prompt, "NEGATIVE": NEG,
                "SEED": 9000 + k, "FILENAME_PREFIX": f"loragen_local/amanda_shoots/{shoot}_{i:02d}"})
            files = client.outputs(client.wait(client.submit(wf), timeout_s=1800))
            if not files:
                print(f"{shoot} {i}: NO OUTPUT", flush=True)
                k += 1
                continue
            client.fetch(files[0], dest)
        m = measure(dest)
        rows.append({"id": f"{shoot}_{i:02d}", "shoot": shoot, "hair": st, "file": str(dest), "prompt": prompt, **m})
        print(f"{shoot} {i:02d} {st:<8} self {m.get('self')} {m.get('bucket_px')}px", flush=True)
        k += 1
(OUT / "scores.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
items = [{"id": r["id"], "path": r["file"], "arm": r["shoot"], "group": r["hair"]} for r in rows]
make_set(Path("outputs/judge"), "shoot_amanda", "Amanda - six risque shoots on the local recipe", items,
         question="Is this Amanda, and is the shot usable?", reference=str(REFS / "amanda_face.jpg"), priority=1)
print(f"AMANDASHOOTSDONE {len(items)} shots -> judge set shoot_amanda")
