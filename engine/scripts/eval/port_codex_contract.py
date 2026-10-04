"""One-off: port the Codex game-asset-gen prompt contract into sourcemode/assets/render.py.

Jeremy, 2026-10-02: "I just want the level of consistency and prompt adherence" -
mid-thigh-up crop, separate body turn and head turn, the closed expression table.
Ported from ~/.codex/skills/game-asset-gen/scripts/scaffold.py (FRAMINGS,
describe_yaw, pose_fields, EXPRESSIONS, prompt order), not re-derived.
"""
import ast
from pathlib import Path

p = Path("sourcemode/assets/render.py")
s = p.read_text(encoding="utf-8")
a = s.index("# Jeremy, 2026-10-01: game assets are THREE-QUARTER portraits")
b = s.index("def shot_prompt(")
c = s.index("\n\n\n", b)

NEW = '''# Jeremy, 2026-10-02: "I just want the level of consistency and prompt adherence"
# of the Codex game-asset-gen skill - its mid-thigh-up crop, separate body turn and
# head turn, and its closed expression table. Ported from
# ~/.codex/skills/game-asset-gen/scripts/scaffold.py (FRAMINGS, describe_yaw,
# pose_fields, EXPRESSIONS, the prompt order) rather than re-derived. Pose family
# rotates front / image-left / image-right by look number so every category carries
# all three; degrees come from a per-look seeded randomizer, exactly as the scaffold
# does. Full length is never asked for - it starved the face (122px kept 12%).
import random

FRAMING_MID_THIGH = ("standing mid-thigh-up portrait; bottom edge cuts through the middle of the thighs; "
                     "knees, lower legs, and feet outside the frame; never full-body")
FRAMING = FRAMING_MID_THIGH   # kept for callers that read the old name
EXPRESSIONS = (
    "relaxed neutral: lips gently together, mouth corners level, cheeks soft, eyebrows resting, relaxed direct gaze; no smile",
    "warm closed-lip smile: both mouth corners lifted, cheeks slightly raised, lips gently together, brows relaxed, soft direct eye contact",
    "natural smile showing teeth: lips comfortably parted with upper teeth visible, cheeks raised, brows relaxed, eyes softly narrowed toward viewer",
    "subtle flirty smile: one mouth corner gently lifted, lips softly together, cheeks slightly raised, brows relaxed, inviting direct eye contact",
    "soft neutral: lips resting together without pressure, mouth corners level, cheeks relaxed, brows smooth, soft attentive eyes toward viewer; no smile",
    "gentle closed-lip smile: mouth corners subtly lifted, lips together without tension, cheeks lightly raised, brows resting, warm direct gaze",
    "bright natural smile showing teeth: both mouth corners lifted, lips parted in an easy smile with teeth visible, cheeks lifted, brows relaxed, eyes engaged with viewer",
    "warm flirty smile: lips slightly parted in a subtle smile, mouth corners gently lifted, cheeks softly raised, brows resting, softly lowered eyelids with direct inviting eye contact",
)
CATEGORY_ORDER = ("casual", "workout", "fancy_dining_gallery", "fancy_town", "casual_date", "work")
SITTING = "She sits on a plain wooden stool facing the camera, hands resting on her thighs, a soft natural smile."
LOOK = ("Photorealistic, natural skin texture, sharp focus, soft even studio lighting, "
        "a plain solid medium grey background with nothing else in frame. "
        "Natural realistic human proportions, correct anatomy.")


def describe_yaw(degrees: int) -> str:
    if degrees == 0:
        return "FRONT: breastbone and pelvis face the lens; both shoulders equally near the camera, torso breadth balanced on both sides"
    side = "image-left" if degrees < 0 else "image-right"
    near = "image-right" if degrees < 0 else "image-left"
    return (f"THREE-QUARTER toward {side} (about {abs(degrees)} degrees): "
            f"breastbone and pelvis point toward {side}; the shoulder on {near} is nearer the camera; "
            f"the shoulder on {side} recedes; chest and waist visibly foreshortened, "
            "far upper arm partly obscured by the torso. Rotate the whole torso, not just one shoulder")


def pose_fields(character: str, slot: dict) -> dict:
    """Screen-relative body geometry and an independent head pose, seeded per look."""
    look = int(slot.get("look", 1))
    family = ("front", "left", "right")[(look - 1) % 3]
    rng = random.Random(f"{character}-{slot.get('id', look)}")
    sign = {"front": 0, "left": -1, "right": 1}[family]
    body = sign * rng.randint(35, 45)
    head = sign * rng.randint(20, 30)
    pitch = ("level", "slightly lowered", "slightly raised")[(look - 1) % 3]
    if sign:
        side = "image-left" if sign < 0 else "image-right"
        head_turn = (f"Nose points toward {side} (about {abs(head)} degrees); unequal visible cheek widths, "
                     "both eyes visible; eyes look toward the lens without squaring the face to it")
    else:
        head_turn = "Nose faces the lens, both cheeks similarly visible; direct eye contact"
    cat_i = CATEGORY_ORDER.index(slot["category"]) if slot.get("category") in CATEGORY_ORDER else 0
    return {"body": describe_yaw(body), "head": f"{head_turn}; chin {pitch}; no lateral head tilt",
            "expression": EXPRESSIONS[(look - 1 + cat_i * 3) % len(EXPRESSIONS)]}


def shot_prompt(character: str, slot: dict, trigger: str | None = None) -> str:
    """The trigger is the bare character name unless the plan overrides it; the rest
    follows the Codex prompt order: crop, body, head, expression, hair, outfit, finish."""
    if slot["pose"] == "sitting":
        return f"{trigger or character}. {SITTING} She is wearing {slot['outfit']}, {slot['hair']}. {LOOK}"
    pf = pose_fields(character, slot)
    return (f"{trigger or character}. New photorealistic standing portrait. "
            f"Crop: {FRAMING_MID_THIGH}. Vertical 2:3, consistent headroom and scale; hair and lateral silhouette inside canvas. "
            f"Body: {pf['body']}. Directions mean image-left/image-right as seen by the viewer. "
            f"Head: {pf['head']}. Body direction and head direction are separate requirements. "
            f"Expression: {pf['expression']}. "
            f"Hair: {slot['hair']}. "
            f"Outfit: {slot['outfit']}. Hands naturally within crop, relaxed standing weight shift. "
            f"{LOOK} No profiles, rear views, seated poses, or off-camera gaze.")'''

s = s[:a] + NEW + s[c:]
ast.parse(s)
p.write_text(s, encoding="utf-8")
print("render.py ported")
