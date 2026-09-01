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

_SQUAT_ARMS_KNEES = {
    "hands_knees": "both hands resting flat on the tops of her knees, arms straight, "
                   "elbows out over her knees",
}
_SQUAT_ARMS_FLOOR = {
    "hands_floor": "both hands placed flat on the floor between and just in front of her "
                   "feet, arms straight, leaning her weight slightly forward onto them",
}

# A deep squat is the hardest pose to hold: it drifts to a half-squat (hips
# never drop), to kneeling (shins go to the floor), or to sitting. All three
# are named in the negative because all three showed up.
#
# "hips below the level of her knees" was not enough — it produced a correct but
# shallow-looking gym squat. Depth has to be described against the body itself
# (bottom to heels, thighs folded onto calves), which the model can actually
# see, rather than against an imaginary horizontal line through the knees.
# Nothing is said about heels: forcing them flat fights the depth, and letting
# the weight roll onto the balls of the feet both drops the hips further and
# reads better for these poses.
_SQUAT_BODY = (
    "She is sunk all the way down into an extremely deep full squat, her hips dropped right "
    "down to her ankles and her bottom hovering just above her heels, the backs of her thighs "
    "folded down against her calves, her knees bent as far as they go and opened apart. Her "
    "shins are NOT touching the floor and her knees are NOT resting on the floor, "
)
_SQUAT_NEGATIVE = (
    "shallow squat, half squat, quarter squat, hips above the knees, barely bending, "
    "standing, standing upright, kneeling, knees on the floor, shins on the floor, "
    "sitting on a chair, sitting on a stool, sitting on the floor, bottom on the floor, "
    # the overhead camera these poses started with, now explicitly excluded
    "high angle, from above, looking down at her, birds eye view, overhead shot, "
    # without these it renders fitness stock: a muscular athlete mid-workout
    "gym, fitness, workout, exercise, exercising, training, weightlifting, weight training, "
    "crossfit, sports photography, athletic build, muscular, bodybuilder, ripped, "
    "grimacing, straining, "
    "close-up, cropped head, tight framing, wide angle lens distortion, huge head, "
    "oversized head, bobblehead, chibi, doll proportions, distorted anatomy, "
    "ladder, stepladder, step stool, stool, chair, furniture, props, "
    "objects on the floor, nude, topless, naked, text, watermark"
)
# Unlike the kneeling family, these are shot LEVEL and straight on, not from
# above. An overhead camera made them read as gym mobility drills and flattened
# the pose; eye level is also what the poses are for.
_SQUAT_CAMERA_FRONT = (
    "Photograph taken from directly in front of her with the camera at her eye level, level "
    "with her face and not above her, shot from a distance with a long lens so the whole body "
    "stays in proportion. The floor is completely empty apart from her. "
)
# These are glamour poses, not exercise photographs. Without saying so the model
# defaults to fitness stock: a muscular athlete mid-workout under flat gym
# light. The wardrobe stays plain and neutral because the real outfit comes from
# image1 — the styling that has to change is the posture and the lighting.
_SQUAT_GLAMOUR = (
    "She looks straight down the lens at the viewer, her face square to the camera and her "
    "chin level. Her back is gracefully arched, her posture poised, feminine and elegant. "
)
_SQUAT_TAIL_FRONT = _SQUAT_GLAMOUR + (
    "Her whole body from head to feet is in frame with space around her. A slim, elegant "
    "young woman, natural realistic human proportions, correct anatomy, a normal sized head. "
    "She wears a plain fitted grey vest top and plain grey shorts. Plain light grey studio "
    "backdrop, soft flattering glamour lighting, photorealistic, sharp focus."
)
_SQUAT_CAMERA_REAR = (
    "Photograph of a woman seen from directly behind, her back fully turned to the camera and "
    "her face not visible at all, taken from straight behind her with the camera at her eye "
    "level and not above her, shot from a distance with a long lens. The floor is completely "
    "empty apart from her. "
)
_SQUAT_TAIL_REAR = (
    "Her back is gracefully arched and her posture is poised and feminine. Her whole body is "
    "in frame with space around her. A slim, elegant young woman, natural realistic human "
    "proportions, correct anatomy, a normal sized head. She wears a plain fitted grey vest top "
    "and plain grey shorts. Plain light grey studio backdrop, soft flattering glamour lighting, "
    "photorealistic, sharp focus."
)
_SQUAT_NEGATIVE_REAR = (
    "facing the camera, front view, face visible, looking at camera, turning around, "
    "glancing over shoulder, profile, three-quarter view, " + _SQUAT_NEGATIVE
)

# All squat bands below are measured from the EYE-LEVEL camera these poses use.
# They were originally calibrated against an overhead camera and every number
# changed sign or magnitude when the camera moved, which is the whole reason
# metrics.py warns about this: squat_depth read +0.41..+0.55 for a deep squat
# from above and reads -0.06..-0.36 for the same pose from eye level. If a
# camera changes, re-measure; do not adjust these by intuition.
#
# Measured, 4 draft candidates per pose:
#   hands on knees  depth -0.06..-0.13  hand_height 0.77..0.91  torso 1.22..1.30
#   hands on floor  depth -0.28..-0.36  hand_height -0.27..-0.20 torso 0.94..1.02
#
# hand_height (wrists vs ankles, in thigh lengths) is what separates the two
# poses, and it separates them by a full 1.0 with no overlap. torso_bend was the
# obvious candidate and is USELESS here: reaching down to the floor out of a deep
# squat leaves the shoulder-hip line vertical, so it measured 0.2-1.3 degrees in
# BOTH poses. A torso_bend gate would have rejected every correct reference.
_SQUAT_FRONT_TARGET = {"head": 0.41, "foreshorten": 1.25, "gaze": -0.10}
_SQUAT_FRONT_LIMITS = {"head": (0.32, 0.50), "foreshorten": (1.00, 1.55), "gaze": (-0.30, 0.10)}
_SQUAT_FRONT_WEIGHTS = {"head": 1.0, "foreshorten": 1.0, "gaze": 1.0}

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
    # --- deep squats ------------------------------------------------------
    # thigh_angle bands are wider than the kneeling ones: from an overhead
    # camera a deep squat splays the knees much further than a kneel, and the
    # apparent angle moves a lot with how far forward the torso leans.
    "squat_deep_hands_knees": {
        "suffix": "squat_deep_hands_knees",
        "variants": _SQUAT_ARMS_KNEES,
        "ref_target": {**_SQUAT_FRONT_TARGET, "squat_depth": -0.10, "hand_height": 0.84,
                       "thigh_angle": 169.0},
        "ref_limits": {**_SQUAT_FRONT_LIMITS, "squat_depth": (-0.60, 0.05), "hand_height": (0.45, 1.30),
                       "thigh_angle": (140.0, 180.0)},
        "ref_weights": {**_SQUAT_FRONT_WEIGHTS, "squat_depth": 2.0, "hand_height": 1.5,
                        "thigh_angle": 1.0},
        "ref_prompt": _SQUAT_CAMERA_FRONT + (
            "A woman is squatting on the floor facing the camera. " + _SQUAT_BODY
            + "{arms}. Her back is straight and upright. " + _SQUAT_TAIL_FRONT
        ),
        "ref_negative": _SQUAT_NEGATIVE,
    },
    "squat_deep_hands_knees_rear": {
        "suffix": "squat_deep_hands_knees_rear",
        "variants": _SQUAT_ARMS_KNEES,
        "ref_target": {"squat_depth": -0.10, "hand_height": 0.84, "body_facing": -1.0,
                       "head_turn": 0.1},
        "ref_limits": {"squat_depth": (-0.60, 0.05), "hand_height": (0.45, 1.30),
                       "body_facing": (-1.3, -0.5), "head_turn": (0.0, 0.45)},
        "ref_weights": {"squat_depth": 2.0, "hand_height": 1.5, "body_facing": 1.5,
                        "head_turn": 1.3},
        "ref_prompt": _SQUAT_CAMERA_REAR + (
            "She is squatting on the floor with her back to the camera. " + _SQUAT_BODY
            + "{arms}. Her back is straight and upright, the back of her head and her hair "
            "toward the camera. " + _SQUAT_TAIL_REAR
        ),
        "ref_negative": _SQUAT_NEGATIVE_REAR,
    },
    # Hands on the floor pitches the torso forward, so this pair gates on
    # torso_bend as well — without it a reference passes on depth while
    # standing bolt upright with its arms dangling.
    "squat_deep_hands_floor": {
        "suffix": "squat_deep_hands_floor",
        "variants": _SQUAT_ARMS_FLOOR,
        "ref_target": {"head": 0.42, "foreshorten": 0.98, "gaze": -0.14,
                       "squat_depth": -0.32, "hand_height": -0.23, "thigh_angle": 143.0},
        "ref_limits": {"head": (0.32, 0.50), "foreshorten": (0.80, 1.30), "gaze": (-0.35, 0.08),
                       "squat_depth": (-0.70, -0.10), "hand_height": (-0.60, 0.15),
                       "thigh_angle": (115.0, 175.0)},
        "ref_weights": {"head": 1.0, "foreshorten": 1.0, "gaze": 1.0,
                        "squat_depth": 2.0, "hand_height": 2.0, "thigh_angle": 1.0},
        "ref_prompt": _SQUAT_CAMERA_FRONT + (
            "A woman is squatting on the floor facing the camera. " + _SQUAT_BODY
            + "{arms}. Her torso leans forward over her hands. " + _SQUAT_TAIL_FRONT
        ),
        "ref_negative": "hands on knees, hands on thighs, arms at her sides, " + _SQUAT_NEGATIVE,
    },
    "squat_deep_hands_floor_rear": {
        "suffix": "squat_deep_hands_floor_rear",
        "variants": _SQUAT_ARMS_FLOOR,
        "ref_target": {"squat_depth": -0.32, "hand_height": -0.23, "body_facing": -1.0,
                       "head_turn": 0.1},
        "ref_limits": {"squat_depth": (-0.70, -0.10), "hand_height": (-0.60, 0.15),
                       "body_facing": (-1.3, -0.5), "head_turn": (0.0, 0.45)},
        "ref_weights": {"squat_depth": 2.0, "hand_height": 2.0, "body_facing": 1.5,
                        "head_turn": 1.3},
        "ref_prompt": _SQUAT_CAMERA_REAR + (
            "She is squatting on the floor with her back to the camera. " + _SQUAT_BODY
            + "{arms}. Her torso leans forward over her hands, the back of her head and her "
            "hair toward the camera. " + _SQUAT_TAIL_REAR
        ),
        "ref_negative": "hands on knees, hands on thighs, arms at her sides, " + _SQUAT_NEGATIVE_REAR,
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
