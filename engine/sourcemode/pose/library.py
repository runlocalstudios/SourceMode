"""Pose definitions. Adding a pose is an entry here — never a new script.

Each pose declares:
  variants     one entry per arm/hand position; chosen at random per image
  ref_prompt   how to render its reference photo ({arms} is substituted)
  ref_negative what must not appear in that reference
  ref_target   the metrics to gate on, and their ideal values
  ref_limits   hard accept bands; anything outside is rejected outright

`ref_target` REPLACES the base set rather than merging with it. Merging was a
real bug: limits calibrated on a kneeling figure are meaningless for a standing
one (a standing torso measures ~1.8-2.3 against shoulder width where a kneeling
one measures ~0.8), and it silently rejected 6 of 6 good rear references.

Four rules for writing ref_prompt, each learned expensively:
 1. Never name a physical object to describe the camera. "Photograph taken from
    a stepladder" put an actual stepladder in every reference, and the pose
    transfer then copied it into every output.
 2. State the camera FIRST. Whatever leads the prompt dominates it; burying the
    angle at the end produced worm's-eye renders shot from floor level.
 3. Say what is VISIBLE from that camera (top of the head, shoulders, the floor
    behind) — it pins the angle harder than any adjective.
 4. Gate on whatever is specific to the pose, or a reference will pass on
    framing while getting the pose itself wrong.
"""

from __future__ import annotations

BASE_TARGET = {"head": 0.40, "foreshorten": 0.92, "gaze": -0.05}
BASE_LIMITS = {"head": (0.32, 0.50), "foreshorten": (0.70, 1.05), "gaze": (-0.30, 0.08)}
BASE_WEIGHTS = {"head": 1.0, "foreshorten": 1.2, "gaze": 1.0}

_KNEEL_ARMS = {
    "hands_thighs": "both hands resting flat on the tops of her thighs, arms relaxed",
    "arms_behind": "both arms held behind her back, hands clasped behind her lower back, "
                   "shoulders drawn back",
    "arms_under_bust": "both forearms folded horizontally across her stomach just beneath her chest",
}
_STAND_ARMS = {
    "arms_relaxed": "her arms hanging relaxed at her sides",
    "hands_hips": "both hands resting on her hips",
}

_KNEEL_CAMERA = (
    "High angle photograph looking steeply down at the subject from well above her head "
    "height, shot from a distance with a long lens so the whole body stays in proportion. "
    "The floor is completely empty apart from her. "
)
_KNEEL_TAIL = (
    "She tips her face up and looks directly into the lens, making eye contact with the "
    "camera above her, her face square to the lens. Because the camera is above her, the "
    "floor fills the background behind her and the tops of her shoulders and thighs are "
    "visible. Her whole body from head to knees is in frame with space around her. Natural "
    "realistic human proportions, correct anatomy, a normal sized head. She wears a plain "
    "fitted grey vest top and plain grey shorts. Plain light grey studio floor, soft even "
    "lighting, photorealistic, sharp focus."
)
_KNEEL_NEGATIVE = (
    "eye level camera, low angle, worm's eye view, from below, looking at the ceiling, "
    "chin thrown back, staring upward past the camera, eyes rolled up, close-up, cropped "
    "head, tight framing, wide angle lens distortion, huge head, oversized head, bobblehead, "
    "chibi, doll proportions, distorted anatomy, ladder, stepladder, step stool, stool, "
    "chair, furniture, props, equipment, objects on the floor, nude, topless, naked, text, watermark"
)
_REAR_NEGATIVE_TAIL = (
    "close-up, cropped, huge head, bobblehead, distorted anatomy, ladder, stool, chair, "
    "furniture, props, nude, topless, naked, text, watermark"
)

POSES: dict[str, dict] = {
    "kneeling": {
        "suffix": "kneeling",
        "variants": _KNEEL_ARMS,
        "ref_prompt": _KNEEL_CAMERA + (
            "A woman kneels upright on both knees on the floor, sitting back on her heels, "
            "knees together, back straight, {arms}. " + _KNEEL_TAIL
        ),
        "ref_negative": _KNEEL_NEGATIVE,
    },
    "kneeling_wide": {
        "suffix": "kneeling_wide",
        "variants": _KNEEL_ARMS,
        # thigh_angle is the APPARENT angle from an overhead camera, which
        # perspective widens: knees together measures 24-28, and asking for a
        # ~60 degree real stance produced 76-99. Tuned against measurement.
        "ref_target": {**BASE_TARGET, "thigh_angle": 78.0},
        "ref_limits": {**BASE_LIMITS, "thigh_angle": (60.0, 100.0)},
        "ref_weights": {**BASE_WEIGHTS, "thigh_angle": 1.5},
        "ref_prompt": _KNEEL_CAMERA + (
            "A woman kneels upright on both knees on the floor, sitting back on her heels. "
            "Her knees are set wide apart on the floor, roughly sixty degrees between her "
            "thighs, a wide open kneeling stance with a clear gap between her knees, her "
            "lower legs angled outward behind her. Her back is straight, {arms}. " + _KNEEL_TAIL
        ),
        "ref_negative": "knees together, knees touching, legs closed, thighs pressed together, " + _KNEEL_NEGATIVE,
    },
    "standing_rear": {
        "suffix": "standing_rear",
        "variants": _STAND_ARMS,
        "ref_target": {"foreshorten": 2.00, "body_facing": -1.0, "head_turn": 0.1},
        "ref_limits": {"foreshorten": (1.40, 2.70), "body_facing": (-1.3, -0.5),
                       "head_turn": (0.0, 0.45)},
        "ref_weights": {"body_facing": 1.5, "head_turn": 1.3},
        "ref_prompt": (
            "Photograph of a woman standing with her back fully turned to the camera, seen "
            "from directly behind. Her face is not visible at all, the back of her head and "
            "her hair are toward the camera. She stands upright, {arms}. Shot from a distance "
            "with a long lens at chest height so the whole body stays in proportion, the floor "
            "empty apart from her, her whole body in frame with space around her. Natural "
            "realistic human proportions, correct anatomy. She wears a plain fitted grey vest "
            "top and plain grey shorts. Plain light grey studio backdrop, soft even lighting, "
            "photorealistic, sharp focus."
        ),
        "ref_negative": (
            "facing the camera, front view, face visible, looking at camera, turning around, "
            "glancing over shoulder, profile, three-quarter view, " + _REAR_NEGATIVE_TAIL
        ),
    },
    "standing_rear_glance": {
        "suffix": "standing_rear_glance",
        "variants": _STAND_ARMS,
        "ref_target": {"foreshorten": 2.00, "body_facing": -1.0, "head_turn": 1.2},
        "ref_limits": {"foreshorten": (1.40, 2.70), "body_facing": (-1.3, -0.5),
                       "head_turn": (0.70, 3.20)},
        "ref_weights": {"body_facing": 1.5, "head_turn": 1.3},
        "ref_prompt": (
            "Photograph of a woman standing with her back turned to the camera, seen from "
            "behind, turning her head to glance back over her shoulder at the camera. Her body "
            "faces away but her face is turned back in three-quarter profile so one side of "
            "her face and one eye are clearly visible, making eye contact with the camera. "
            "She stands upright, {arms}. Shot from a distance with a long lens at chest height "
            "so the whole body stays in proportion, the floor empty apart from her, her whole "
            "body in frame. Natural realistic human proportions, correct anatomy. She wears a "
            "plain fitted grey vest top and plain grey shorts. Plain light grey studio backdrop, "
            "soft even lighting, photorealistic, sharp focus."
        ),
        "ref_negative": (
            "front view, body facing the camera, face fully visible, full frontal, "
            "head facing away, back of the head only, bending over, leaning forward, "
            + _REAR_NEGATIVE_TAIL
        ),
    },
}


def gates(pose: dict) -> tuple[dict, dict, dict]:
    """Target/limits/weights for a pose. Declared sets REPLACE the base set."""
    if pose.get("ref_target"):
        target = dict(pose["ref_target"])
        limits = {k: v for k, v in pose.get("ref_limits", {}).items() if k in target}
        weights = {**{k: 1.0 for k in target}, **pose.get("ref_weights", {})}
        return target, limits, weights
    return dict(BASE_TARGET), dict(BASE_LIMITS), dict(BASE_WEIGHTS)
