"""One-off: apply Jeremy's 2026-10-02 feedback on Amanda's first asset pack.

Backgrounds not fully transparent -> magenta backdrop + chroma key. Stiff poses ->
natural pose rotation. Too far away -> upper-thigh framing. Must always look at the
camera -> gaze clause in the prompt and a hard gaze check in adherence. Body not
petite enough / bust too small -> the appearance clause goes into every asset prompt.
"""
import ast
from pathlib import Path

p = Path("sourcemode/assets/render.py")
s = p.read_text(encoding="utf-8")

old = 'FRAMING = FRAMING_MID_THIGH   # kept for callers that read the old name'
new = '''# Jeremy, 2026-10-02, on Amanda's first pack: "almost all a little too far away...
# shoot for framing to her upper thighs instead of what's basically at her knees".
FRAMING_UPPER_THIGH = ("standing upper-thigh portrait, close enough that her face is large in frame; bottom edge "
                       "cuts across the tops of her thighs just below the hips; knees, lower legs, and feet "
                       "outside the frame; never full-body, never a wide shot")
FRAMING = FRAMING_UPPER_THIGH   # kept for callers that read the old name'''
assert old in s
s = s.replace(old, new)

old = '        "a plain solid medium grey background with nothing else in frame. "'
new = '        "a flat solid bright magenta #FF00FF background edge to edge with nothing else in frame, no shadows on it. "'
assert old in s
s = s.replace(old, new)

s = s.replace('"both eyes visible; eyes look toward the lens without squaring the face to it")',
              '"both eyes visible; her eyes locked on the lens, direct eye contact with the viewer")')
s = s.replace('head_turn = "Nose faces the lens, both cheeks similarly visible; direct eye contact"',
              'head_turn = "Nose faces the lens, both cheeks similarly visible; her eyes locked on the lens, direct eye contact with the viewer"')

old = '            "asked": {"crop": "mid-thigh-up", "body_side": side, "body_deg": body, "head_side": side,'
new = '''            "pose": POSES[(look - 1 + cat_i) % len(POSES)],
            "asked": {"crop": "upper-thigh-up", "body_side": side, "body_deg": body, "head_side": side,'''
assert old in s
s = s.replace(old, new)

old = 'CATEGORY_ORDER = ("casual", "workout", "fancy_dining_gallery", "fancy_town", "casual_date", "work")'
new = '''CATEGORY_ORDER = ("casual", "workout", "fancy_dining_gallery", "fancy_town", "casual_date", "work")
# Jeremy, 2026-10-02: "stiff poses". Natural, relaxed standing poses rotated per look;
# none of them a hand on the hip, none looking away.
POSES = (
    "relaxed natural stance, weight on one leg, one hand resting lightly on her upper thigh, the other arm loose",
    "one hand lifting her hair away from her neck, elbow out, the other arm relaxed at her side",
    "thumbs hooked loosely in her waistband, shoulders relaxed",
    "arms crossed loosely under her bust, lifting it slightly",
    "one hand touching her collarbone, the other arm relaxed, a slight natural lean",
    "hands clasped loosely in front of her hips, shoulders back",
    "one hand brushing hair behind her ear, the other arm relaxed at her side",
    "leaning her weight back slightly on one leg, one hand on the back of her neck",
)


def appearance_clause(character: str) -> str:
    """The character's body/feature clause from characters/appearance.json, injected into
    every generation prompt and never into a caption (see that file's header)."""
    import json  # noqa: PLC0415
    for base in (Path(__file__).resolve().parents[3], Path("C:/dev/sourcemode")):
        f = base / "characters" / "appearance.json"
        if f.is_file():
            try:
                return (json.loads(f.read_text(encoding="utf-8")).get(character.lower()) or {}).get("prompt", "") or ""
            except (OSError, ValueError):
                return ""
    return ""'''
assert old in s
s = s.replace(old, new)

old = '''    pf = pose_fields(character, slot)
    return (f"{trigger or character}. New photorealistic standing portrait. "
            f"Crop: {FRAMING_MID_THIGH}. Vertical 2:3, consistent headroom and scale; hair and lateral silhouette inside canvas. "
            f"Body: {pf['body']}. Directions mean image-left/image-right as seen by the viewer. "
            f"Head: {pf['head']}. Body direction and head direction are separate requirements. "
            f"Expression: {pf['expression']}. "
            f"Hair: {slot['hair']}. "
            f"Outfit: {slot['outfit']}. Hands naturally within crop, relaxed standing weight shift. "
            f"{LOOK} No profiles, rear views, seated poses, or off-camera gaze.")'''
new = '''    pf = pose_fields(character, slot)
    app = appearance_clause(character)
    return (f"{trigger or character}. New photorealistic standing portrait of {app + ', ' if app else ''}"
            f"her body shape and proportions exactly as described. "
            f"Crop: {FRAMING_UPPER_THIGH}. Vertical 2:3, consistent headroom and scale; hair and lateral silhouette inside canvas. "
            f"Body: {pf['body']}. Directions mean image-left/image-right as seen by the viewer. "
            f"Head: {pf['head']}. Body direction and head direction are separate requirements. "
            f"Gaze: she is ALWAYS looking directly into the camera lens. "
            f"Expression: {pf['expression']}. "
            f"Pose: {pf['pose']}. "
            f"Hair: {slot['hair']}. "
            f"Outfit: {slot['outfit']}, fitted to her tiny frame. "
            f"{LOOK} No profiles, rear views, seated poses, or off-camera gaze.")'''
assert old in s
s = s.replace(old, new)
ast.parse(s)
p.write_text(s, encoding="utf-8")

a = Path("sourcemode/assets/adherence.py")
t = a.read_text(encoding="utf-8")
old = '        ok = have == want or (want in ("waist-up", "mid-thigh-up") and have == "mid-thigh-up")'
new = '        ok = have == want or (want in ("waist-up", "mid-thigh-up", "upper-thigh-up") and have == "mid-thigh-up")'
assert old in t
t = t.replace(old, new)
old = '        got["smile"], got["jaw"] = round(smile, 3), round(jaw, 3)'
new = '''        got["smile"], got["jaw"] = round(smile, 3), round(jaw, 3)
        # gaze, as gaze_mp.py scores it: (inLeft + outRight) - (outLeft + inRight);
        # large magnitude = eyes off the lens. Jeremy: she must ALWAYS look at the camera.
        gaze = ((b.get("eyeLookInLeft", 0) + b.get("eyeLookOutRight", 0))
                - (b.get("eyeLookOutLeft", 0) + b.get("eyeLookInRight", 0)))
        got["gaze"] = round(float(gaze), 3)
        got["eyes_on_lens"] = abs(gaze) < 1.0'''
assert old in t
t = t.replace(old, new)
old = '''    got: dict = {"crop": None, "body_side": None, "body_depth": None, "head_side": None,
                 "head_offset": None, "expression": None, "smile": None, "jaw": None}'''
new = '''    got: dict = {"crop": None, "body_side": None, "body_depth": None, "head_side": None,
                 "head_offset": None, "expression": None, "smile": None, "jaw": None,
                 "gaze": None, "eyes_on_lens": None}'''
assert old in t
t = t.replace(old, new)
old = '    if asked.get("expression") and got.get("expression"):'
new = '''    if got.get("eyes_on_lens") is False:
        failed.append(f"gaze: eyes off the lens ({got.get('gaze')})")
    if asked.get("expression") and got.get("expression"):'''
assert old in t
t = t.replace(old, new)
ast.parse(t)
a.write_text(t, encoding="utf-8")

q = Path("scripts/eval/amanda_assets.ps1")
u = q.read_text(encoding="utf-8")
u = u.replace('"--out", "outputs\\game-assets\\amanda\\cutouts", "--game")',
              '"--out", "outputs\\game-assets\\amanda\\cutouts", "--game", "--chroma", "magenta")')
u = u.replace("amanda_v2.log", "daisy_v2.log").replace("AMANDA_V2TRAINDONE", "DAISY_V2TRAINDONE").replace("amanda never finished", "daisy never finished")
assert '"--chroma", "magenta"' in u and "DAISY_V2TRAINDONE" in u
q.write_text(u, encoding="utf-8")
print("render, adherence, amanda_assets patched")
