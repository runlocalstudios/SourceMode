"""The photo stories photo_story.py renders: room, camera, one look per character, ordered shots.

Jeremy, 2026-11-10 evening: "recreate the Fiona librarian set, the dictation set,
the try-on set, the cheerleader tease set, and then ... the living room tease set
for her with a very schoolgirl outfit ... her straddling the couch arm ... show
off her panties ... hair down ... the massage set (messy bun - POV pics of her
massaging the inside of the viewer's leg near his crotch but clothed) ... the
closing the bar set (pigtails ... extremely sexy and unique outfit for a slutty
gorgeous bartender) ... the tutor set (you pick the particulars - make it very
sexy) ... When you're done with all the Fiona sets, I want one of Eden doing the
living room tease - you pick a very, very sexy outfit".

Storyboards follow the Codex shot plans (docs/codex-story-plans.md, extracted from
his read-only Codex output folder), including the frames OpenAI refused
(rear views, over-the-shoulder looks, sitting on the bed or the bar, kneeling on
the sofa, hands on his shoulders, the ankle-strap crouch), which are the point.

Rules proven on the hotel story (docs/story-recipes.md):
- never name the viewer or his seat; "the camera at seated eye level"
- one outfit sentence and one room sentence, identical in every frame
- floor/standing poses say "a full-length photo, her whole ... figure in frame"
- close portraits get CLOSE and their own soft room
- "flushed" paints blush; "biting her lip" draws a tongue; a dress named once it
  is off re-dresses her; hair-up poses say "exactly two hands"
- nude shots: her LoRA alone (the nude face probe, j1388: GNASS at 0.5 cost
  0.15-0.2 of face score and bought nothing)
"""

from dataclasses import dataclass, field

GNASS = "nsfw\\qimage2512_gnass.safetensors"
GNASS_STRENGTH = 0.0   # j1388: her LoRA alone renders nudity and keeps her face; GNASS only cost identity

POV = "point-of-view photo, the camera at seated eye level"
HANDS = "both of her hands away from the camera"   # appended after every shot text by photo_story.prompt_for
# the selfie arm: a close POV frame with one hand unaccounted for reaches for the camera (try-on 6/26, cheer a01/a04);
# "shot on a tripod" put a TRIPOD in the frame (cheer b03/b04). Name BOTH hands in every waist-up shot.
CLOSE = "a close-up portrait photo, head and shoulders only, her face filling the frame"
PLEASED = "a warm closed-lip smile"
TEASE = "a teasing smile, eyes on the camera"
FULL = "a full-length photo, her whole figure in frame"

NEG_BASE = ("different person, different face, changed hair, extra hands, extra limbs, deformed hands, "
            "blurry, low quality, cartoon, anime, watermark, text, a second woman, the man's face, his face, "
            "tongue out, blush circles, pink cheeks, heavy blush, selfie, her arm reaching toward the camera, "
            "childlike, child, underage")
NEG_NOMAN = "armchair, a man, man's shoulder, suit jacket, another person"   # dropped on shots flagged "him"
NEG_NUDE = ("clothes on her, bra, panties, underwear, covered, censored, deformed genitals, extra fingers, "
            "tears, crying, toothy grin, his hand, upside down")


@dataclass(frozen=True)
class Shot:
    id: str
    text: str                       # {POV} {CLOSE} {FULL} {OUTFIT} {TEASE} {PLEASED} and look extras
    flags: tuple[str, ...] = ()     # nude, close, face_low, face_hidden, him (his body is in frame on purpose)
    negative: str = ""
    alt: str | None = None          # a named alternate look (try-on's three outfits)


@dataclass(frozen=True)
class Look:
    hair: str
    outfit: str
    negative: str = ""
    extras: dict = field(default_factory=dict)          # extra template keys
    alts: dict = field(default_factory=dict)            # name -> (hair, outfit)


@dataclass(frozen=True)
class Story:
    title: str
    room: str
    looks: dict                      # character -> Look ("*" = any)
    shots: tuple
    close_room: str = "Soft out-of-focus room behind her, warm lamplight"
    negative: str = ""

    def look(self, char: str) -> Look | None:
        return self.looks.get(char) or self.looks.get("*")

    def hair_outfit(self, shot: Shot, look: Look) -> tuple[str, str]:
        if shot.alt:
            return look.alts[shot.alt]
        return look.hair, look.outfit

    def render(self, shot: Shot, look: Look) -> str:
        hair, outfit = self.hair_outfit(shot, look)
        keys = {"POV": POV, "CLOSE": CLOSE, "FULL": FULL, "TEASE": TEASE, "PLEASED": PLEASED,
                "OUTFIT": outfit, "HAIR": hair, **look.extras}
        return shot.text.format_map(keys)


STORIES: dict[str, Story] = {}

# =============================================================================================
# 1. LIBRARIAN - closing time
# =============================================================================================
LIB_ROOM = ("Inside a small old library at night after closing, warm green-shaded brass lamps on a long dark "
            "oak reading table, tall dark oak bookshelves, black mullioned windows reflecting the lamps, a "
            "wooden rolling ladder on a rail along the shelves, an open book on the near end of the table")
STORIES["librarian"] = Story(
    title="librarian, closing time",
    room=LIB_ROOM,
    close_room="Soft out-of-focus library shelves and green-shaded lamps behind her at night",
    looks={"*": Look(
        hair="her hair worn loose",
        outfit=("an ivory satin sleeveless boat-neck blouse tucked into a high-waisted red and black plaid "
                "pencil skirt ending just above the knee, sheer black stockings, dark brown block heels and "
                "two slim deep-red barrettes at her temples"),
        negative="glasses, cardigan, long dress, pants, sneakers, bare feet")},
    shots=(
        Shot("a01_shelf", "{POV}: three-quarter length, she stands by a low shelf holding three clothbound books "
                          "against her ribs, checking the top spine with a slight downward glance, in {OUTFIT}"),
        Shot("a02_smile", "{POV}: three-quarter length, she stands by the shelf with the books held against her "
                          "ribs, turning her head and shoulder to the camera with a bright spontaneous smile, in {OUTFIT}"),
        Shot("a03_ladder", "{POV}: {FULL}, she stands on the first rung of the wooden rolling ladder, one hand on "
                           "the rail, sliding a book onto a chest-height shelf, in {OUTFIT}"),
        Shot("a04_ladder_look", "{POV}: {FULL}, standing on the ladder's first rung with her back to the camera, "
                                "pressing a book flush into the shelf, looking back over her shoulder with a "
                                "quick closed-lip smile, in {OUTFIT}", flags=("face_low",)),
        Shot("a05_hush", "{POV}: three-quarter length, standing on the ladder's first rung turned toward the "
                         "camera, her bare index finger raised to her lips in a playful hush, eyebrows "
                         "lifted, in {OUTFIT}"),
        Shot("a06_step_down", "{POV}: {FULL}, she steps down off the ladder onto the floor, one foot still on the "
                              "rung and one hand on the brass rail, glancing at the camera, in {OUTFIT}"),
        Shot("b01_closing", "{POV}: three-quarter length, she stands beside the reading table with her fingertips "
                            "on the tabletop, telling the camera the library is closing, lips parted "
                            "mid-sentence, in {OUTFIT}"),
        Shot("b02_listen", "{POV}: three-quarter length, standing beside the table, head tilted a few degrees, "
                           "listening with a patient closed-lip smile, in {OUTFIT}"),
        Shot("b03_tuck", "{POV}: waist up, standing beside the table, one palm on the oak and the other hand "
                         "tucking a strand of hair behind her ear, head tipped toward it, {PLEASED}, in {OUTFIT}"),
        Shot("b04_laugh", "{POV}: waist up, standing beside the table, one light natural laugh at the camera, "
                          "eyes narrowing, in {OUTFIT}"),
        Shot("c01_perch", "{POV}: three-quarter length, she perches on the near corner of the reading table with "
                          "her legs angled toward the camera and her palms on the table edge, a slow closed-mouth "
                          "smile, in {OUTFIT}"),
        Shot("c02_cross", "{POV}: three-quarter length, perched on the table corner with one leg crossed over the "
                          "other at the knee, palms behind her on the oak, leaning back a little, head tilted, "
                          "one corner of her mouth lifted, in {OUTFIT}"),
        Shot("c03_lean_in", "{POV}: waist up, seated on the table corner beside a red book, leaning forward toward "
                            "the camera to listen with her brows lifted, both hands resting on the table edge beside "
                            "her hips, in {OUTFIT}"),
        Shot("c04_laugh", "{POV}: waist up, seated on the table corner, straightening up and laughing, one hand "
                          "open palm-up at her waist, in {OUTFIT}"),
        Shot("c05_slide_closer", "{POV}: three-quarter length, she has slid along the table edge closer to the "
                                 "camera, hips resettled, glancing down at the open book with a slight smile, in {OUTFIT}"),
        Shot("c06_read", "{POV}: waist up, leaning over the open book on the table with her fingertips beside the "
                         "page, her hair slipping forward over one shoulder, eyes tracking a line, in {OUTFIT}"),
        Shot("c07_close_book", "{POV}: waist up, standing by the table corner lowering the cover of the open book "
                               "nearly closed, a quietly amused closed-lip look up at the camera, in {OUTFIT}"),
        Shot("d01_drop", "{POV}: three-quarter length, a red book tipping off the table edge as she reaches for it "
                         "too late, brows up, mouth opening, in {OUTFIT}"),
        Shot("d02_kneel", "{POV}: {FULL}, down on one knee beside the table leg, bending forward to pick a red book "
                          "up off the floor with one hand, her other hand on her raised knee, her face turned up "
                          "three-quarter toward the camera, in {OUTFIT}"),
        Shot("d03_kneel_look", "{POV}: {FULL}, kneeling on one knee by the table, the book lifted onto her raised "
                               "knee, looking up at the camera with an amused closed-mouth smile, in {OUTFIT}"),
        Shot("d04_bend_back", "{POV}: {FULL}, seen from behind, bent forward at the waist reaching for a book on "
                              "the floor by the table, her plaid skirt tight across her bottom, looking back over "
                              "her shoulder at the camera, in {OUTFIT}", flags=("face_low",)),
        Shot("d05_smooth", "{POV}: three-quarter length, standing with one hand on the recovered book on the oak "
                           "and the other palm smoothing a crease on her skirt over her thigh, glancing down, "
                           "pleased, in {OUTFIT}"),
        Shot("e01_close_smile", "{CLOSE}, she looks straight into the camera over the green lamp with a slow "
                                "asymmetric half-smile, chin dipped a little, in {OUTFIT}", flags=("close",)),
        Shot("e02_close_glasses_off", "{CLOSE}, she bites the arm of a pair of reading glasses at the corner of "
                                      "her mouth, eyes on the camera, one brow raised, in {OUTFIT}",
             flags=("close",), negative="glasses on her face"),
        Shot("e03_last_perch", "{POV}: three-quarter length, one last perch on the table corner with her knees "
                               "together toward the camera and her palms on the edge, a warm parting smile, in {OUTFIT}"),
        Shot("e04_walk_away", "{POV}: {FULL}, walking away down the aisle between the shelves with her back to the "
                              "camera, looking back over her shoulder with a small goodnight smile, in {OUTFIT}",
             flags=("face_low",)),
    ))

# =============================================================================================
# 2. DICTATION
# =============================================================================================
OFFICE_ROOM = ("Inside a private dark-walnut office in daylight, a broad walnut desk with a brass lamp in the "
               "near foreground, a closed walnut door on the far panelled wall, a tall city window on the right "
               "with soft daylight, one cream wool guest chair beyond the far desk corner, taupe carpet")
STORIES["dictation"] = Story(
    title="dictation",
    room=OFFICE_ROOM,
    close_room="Soft out-of-focus walnut office and a bright window behind her in daylight",
    looks={"*": Look(
        hair="her hair worn loose",
        outfit=("an ivory fitted sleeveless cropped top with a square neckline showing her midriff, a charcoal "
                "tailored high-rise mini skirt, black stiletto heels and large thin gold hoop earrings"),
        negative="blazer, jacket, long skirt, pants, sneakers, bare feet, glasses",
        extras={"PAD": "an olive spiral notepad"})},
    shots=(
        Shot("a01_ready", "{POV} from behind the desk: waist up, she sits in the guest chair with {PAD} on her lap "
                          "and a pen lifted, eyes on the camera, lips parted as if asking if he is ready, in {OUTFIT}"),
        Shot("a02_writing", "{POV} from behind the desk: waist up, in the guest chair in a shallow three-quarter "
                            "turn, chin lowered, writing on {PAD}, in {OUTFIT}"),
        Shot("a03_look_up", "{POV} from behind the desk: waist up, she pauses writing and looks up from {PAD} with "
                            "a small genuine smile, pen poised, in {OUTFIT}"),
        Shot("a04_legs", "{POV} from behind the desk: {FULL}, she sits in the guest chair beside the far desk "
                         "corner with her legs crossed, {PAD} on her lap, looking up from her notes, in {OUTFIT}"),
        Shot("a05_pen_drop", "{POV} from behind the desk: {FULL}, in the guest chair with her legs angled to the "
                             "side, the pen just slipped from her hand onto the carpet, glancing down after it, in {OUTFIT}"),
        Shot("a06_bend_pen", "{POV} from behind the desk: three-quarter length, she bends forward out of the guest "
                             "chair to pick the pen up off the carpet, her cropped top falling open at the "
                             "neckline, looking up at the camera, in {OUTFIT}"),
        Shot("a07_laugh", "{POV} from behind the desk: waist up, she resumes dictation with a brief laugh, {PAD} "
                          "held up in one hand, gesturing with the pen in the other, in {OUTFIT}"),
        Shot("b01_stand", "{POV} from behind the desk: {FULL}, she stands up from the guest chair and steps toward "
                          "the desk, one hip turned, checking a line on {PAD} at reading height, in {OUTFIT}"),
        Shot("b02_compare", "{POV} from behind the desk: three-quarter length, standing at the far desk corner "
                            "comparing {PAD} with a typed sheet on the desk, tracing a line with the pen, in {OUTFIT}"),
        Shot("b03_read_aloud", "{POV} from behind the desk: waist up, standing right beside the desk reading a "
                               "lifted sheet aloud, lids lowered, mid-speech, in {OUTFIT}"),
        Shot("b04_glance", "{POV} from behind the desk: waist up, she pauses reading and glances up from the page "
                           "with a gradual closed-mouth smile, chin tilted, in {OUTFIT}"),
        Shot("b05_desk_lean", "{POV} from behind the desk: three-quarter length, she leans over the near side of "
                              "the desk toward the camera with both palms on the walnut, her cleavage framed by "
                              "the square neckline, eyes on the camera, in {OUTFIT}"),
        Shot("b06_beside_chair", "{POV} looking up at her from the desk chair: three-quarter length, she stands right "
                                 "beside the camera in the window aisle, one hand on the near desk corner, a small "
                                 "warm smile down at the camera, in {OUTFIT}", flags=("him",)),
        Shot("b07_armrest", "{POV} looking up at her: three-quarter length, she sits sideways on the padded armrest "
                            "of the black leather desk chair right beside the camera, legs crossed, {PAD} on her "
                            "knee, looking down at the camera with a knowing smile, in {OUTFIT}", flags=("him",)),
        Shot("b08_tuck", "{POV} from behind the desk: waist up, standing beside the desk tucking a section of hair "
                         "behind her ear to show the gold hoop, looking slightly toward the window, in {OUTFIT}"),
        Shot("b09_laugh", "{POV} from behind the desk: waist up, a quick amused laugh with her chin tipped up, one "
                          "palm on the walnut, her midriff showing, in {OUTFIT}"),
        Shot("c01_kneel_note", "{POV} from behind the desk: {FULL}, she lowers onto one knee on the carpet beside "
                               "the desk to pick up a fallen note, one hand on the desk edge, looking up at the "
                               "camera, in {OUTFIT}"),
        Shot("c02_point", "{POV} from behind the desk: waist up, she holds the top page at chest height and points "
                          "at a spot on it with her index finger, looking up with raised brows, in {OUTFIT}"),
        Shot("c03_slide", "{POV} from behind the desk: waist up, she leans in sliding a report across the desk "
                          "toward the camera, one hand guiding the corner, a small closed-mouth smile, in {OUTFIT}"),
        Shot("c04_sit_on_desk", "{POV} from behind the desk: three-quarter length, she sits on the near edge of the "
                                "desk facing the camera with her legs crossed, {PAD} on her knee, in {OUTFIT}"),
        Shot("c05_desk_lean_back", "{POV} from behind the desk: three-quarter length, seated on the desk edge "
                                   "leaning back on her palms, chin lifted, a playful half-smile, in {OUTFIT}"),
        Shot("d01_close_half_smile", "{CLOSE}, forearm on the near desk corner, a slow asymmetric half-smile, in "
                                     "{OUTFIT}", flags=("close",)),
        Shot("d02_close_brow", "{CLOSE}, chin dipped, a playful glance up with one brow lifting, brushing a lock back "
                               "to show the gold hoop, in {OUTFIT}", flags=("close",)),
        Shot("d03_close_laugh", "{CLOSE}, a flirty laugh with her teeth showing, turning back to the camera, in "
                                "{OUTFIT}", flags=("close",)),
        Shot("e01_hair_up_seated", "{POV} from behind the desk: waist up, seated side-on in the guest chair facing "
                                   "the window, gathering all her hair up high behind her crown with both hands, "
                                   "exactly two hands, head turned three-quarter to the camera with a knowing "
                                   "smile, in {OUTFIT}"),
        Shot("e02_hair_up_stand", "{POV} from behind the desk: three-quarter length, standing beside the near end "
                                  "of the desk in a broad stance with her hips to the desk, one hand raised "
                                  "gathering her hair high at the crown and the other palm on the desk behind "
                                  "her hip, exactly two hands, in {OUTFIT}"),
        Shot("e03_back_in_chair", "{POV} from behind the desk: waist up, back in the guest chair with {PAD} above "
                                  "her lap and the pen poised, looking up into the camera holding back a smile, in {OUTFIT}"),
    ))

# =============================================================================================
# 3. TRY-ON
# =============================================================================================
TRYON_ROOM = ("Inside a cream-walled bedroom in the evening, an open honey-oak walk-in closet on the far wall with "
              "a clothes rail and hangers, a pale oak floor with an ivory runner, a white-duvet bed on the left, "
              "an oak-framed full-length mirror beside the closet, a warm linen-shaded bedside lamp")
TRY_A = ("a fitted midnight-blue rhinestone mini dress with narrow straps and a scoop neckline, short mid-thigh "
         "hem, bare feet")
TRY_B = ("a plum velour short-sleeved romper with a soft scooped V-neck and tailored short legs, bare feet")
TRY_C = ("a cream long-sleeved cropped knit sweater showing a band of midriff, a charcoal A-line mini skirt, a "
         "slim black velvet choker, bare feet")
STORIES["tryon"] = Story(
    title="try-on",
    room=TRYON_ROOM,
    close_room="Soft out-of-focus bedroom and open closet behind her, warm lamplight",
    looks={"*": Look(
        hair="her hair worn loose", outfit=TRY_A,
        negative="shoes, heels, sneakers, jeans, long dress",
        alts={"A": ("her hair worn loose", TRY_A),
              "B": ("her hair half-up with two small high tight pigtails above her ears, the rest hanging loose", TRY_B),
              "C": ("her hair half-up in one high half-up ponytail at the back of her crown, the rest hanging loose", TRY_C)})},
    shots=(
        Shot("a01_doorway", "{POV}: {FULL}, she stands facing the camera in the closet doorway with her fingertips "
                            "on the oak jamb, an expectant closed-mouth smile, in {OUTFIT}", alt="A"),
        Shot("a02_step_out", "{POV}: three-quarter length, one step out of the closet, pausing at the threshold "
                             "with her shoulders to the camera and a small warm smile, in {OUTFIT}", alt="A"),
        Shot("a03_side", "{POV}: three-quarter length, standing on the oak floor in a soft pivot showing the side of "
                         "the dress with the stones catching the light, torso side-on, face turned back three-quarter watching the camera's "
                         "reaction, in {OUTFIT}", alt="A", flags=("face_low",)),
        Shot("a04_rear_look", "{POV}: {FULL}, standing on the oak floor in a rear three-quarter stance showing the back "
                              "of the dress, looking "
                              "back over her near shoulder with a confident half-smile, in {OUTFIT}", alt="A",
             flags=("face_low",)),
        Shot("a05_hair_sweep", "{POV}: three-quarter length, near the camera, sweeping a section of hair behind one "
                               "shoulder and raising her eyes with a small cheek lift, in {OUTFIT}", alt="A"),
        Shot("a06_well", "{POV}: three-quarter length, standing with her feet planted and both hands resting at her "
                         "sides, one brow lifted, a playful "
                         "half-smile asking which look he likes, in {OUTFIT}", alt="A"),
        Shot("a07_back_in", "{POV}: {FULL}, stepping back into the closet with her body angled away, turning partway "
                            "back with an easy smile before changing, in {OUTFIT}", alt="A", flags=("face_low",)),
        Shot("b01_doorway", "{POV}: {FULL}, she stands at the closet threshold in the romper, one hand at the side "
                            "seam, a small knowing smile, in {OUTFIT}", alt="B"),
        Shot("b02_step", "{POV}: three-quarter length, one step toward the camera with both arms hanging at her sides "
                         "and her hands by her thighs, eyebrows "
                         "lifted, an amused closed-lip smile, in {OUTFIT}", alt="B"),
        Shot("b03_side", "{POV}: three-quarter length, standing side-on at the near mark with her hands clasped behind "
                         "her back, head partly turned for a sideways "
                         "glance with a small smile, in {OUTFIT}", alt="B", flags=("face_low",)),
        Shot("b04_rear", "{POV}: {FULL}, rear three-quarter stance showing the back of the romper and the pigtails, "
                         "glancing back over her near shoulder with a quiet half-smile, in {OUTFIT}", alt="B",
             flags=("face_low",)),
        Shot("b05_check_velour", "{POV}: three-quarter length, standing facing the camera, both hands at the waist "
                                 "seam of the romper, eyes flicking down to check the velour, in {OUTFIT}", alt="B"),
        Shot("b06_laugh", "{POV}: waist up, standing with her hands clasped behind her back, a brief natural laugh, "
                          "cheeks lifting, eyes crinkling, in {OUTFIT}", alt="B"),
        Shot("b07_back_in", "{POV}: {FULL}, walking back to the closet with one quick grin back over her shoulder, "
                            "in {OUTFIT}", alt="B", flags=("face_low",)),
        Shot("c01_doorway", "{POV}: {FULL}, she stands in the closet doorway with one hand on the jamb, relaxed, a "
                            "faint knowing smile, in {OUTFIT}", alt="C"),
        Shot("c02_cuff", "{POV}: three-quarter length, standing one step out of the closet turned to the camera, "
                         "both hands down in front of her, the fingertips of one hand touching the knit cuff of the other, the choker and her midriff showing, soft eye contact, in {OUTFIT}", alt="C"),
        Shot("c03_side", "{POV}: three-quarter length, standing on the oak floor in a comfortable side stance with her "
                         "hands clasped behind her back, glancing back in a three-quarter "
                         "head turn, in {OUTFIT}", alt="C", flags=("face_low",)),
        Shot("c04_rear", "{POV}: {FULL}, standing on the oak floor turned to show the back of the outfit, the short "
                         "skirt over her bottom, "
                         "looking back over her near shoulder with a confident soft closed-lip smile, in {OUTFIT}",
             alt="C", flags=("face_low",)),
        Shot("c05_to_bed", "{POV}: three-quarter length, she turns to the near foot corner of the bed and looks down "
                           "placing a hand on the mattress edge before sitting, in {OUTFIT}", alt="C"),
        Shot("c06_sit", "{POV}: three-quarter length, she sits upright on the bed's foot corner with her feet on the "
                        "floor and one hand on the duvet, turning to the camera with a knowing smile, in {OUTFIT}", alt="C"),
        Shot("c07_chin", "{POV}: waist up, seated on the bed corner with her elbow on her thigh and her chin on her "
                         "knuckles, listening, relaxed lips, in {OUTFIT}", alt="C"),
        Shot("c08_lean_back", "{POV}: three-quarter length, seated on the bed corner leaning back on one palm set "
                              "into the mattress, knees forward, a soft smile, in {OUTFIT}", alt="C"),
        Shot("c09_legs", "{POV}: {FULL}, seated on the bed corner with her legs crossed, the skirt riding up her "
                         "thigh, one hand on her knee, {TEASE}, in {OUTFIT}", alt="C"),
        Shot("c10_close", "{CLOSE}, she looks straight into the camera with a slow half-smile, the choker at her "
                          "throat, in {OUTFIT}", alt="C", flags=("close",)),
        Shot("c11_rise", "{POV}: {FULL}, rising from the bed and turning toward the closet, looking back at the "
                         "camera with a quick amused grin, in {OUTFIT}", alt="C", flags=("face_low",)),
        Shot("c12_last_look", "{POV}: {FULL}, in the closet doorway with a hand on the jamb, turned a little through "
                              "the shoulders for one last look back, in {OUTFIT}", alt="C"),
    ))

# =============================================================================================
# 4. CHEERLEADER TEASE
# =============================================================================================
BEDROOM = ("Inside a warm bedroom in daylight, an ivory-duvet bed with a blush upholstered headboard on the right, "
           "pale sheer curtains and broad daylight on the left, a cream rug, a brass bedside lamp, a low cream "
           "upholstered bench at the foot of the bed")
CHEER = ("a plum short-sleeved cheerleader uniform top with a broad ivory chevron across the chest and a scoop "
         "neckline, a matching plum pleated cheer mini skirt with ivory hem bands, white ankle socks and white "
         "sneakers")
STORIES["cheer"] = Story(
    title="cheerleader tease",
    room=BEDROOM,
    close_room="Soft out-of-focus bedroom and bright sheer curtains behind her",
    looks={"*": Look(
        hair="her hair pulled back in a high ponytail", outfit=CHEER,
        negative="pom poms, lettering, logo, long skirt, pants, bare feet, heels",
        alts={"down": ("her hair worn loose", CHEER)})},
    shots=(
        Shot("a01_welcome", "{POV}: three-quarter length, standing almost front-on on the rug, one shoulder back, "
                            "one hand at her waist, a bright welcoming smile, in {OUTFIT}"),
        Shot("a02_turn", "{POV}: {FULL}, a quarter turn toward the window with her arms down, an easy smile showing "
                         "her upper teeth, in {OUTFIT}"),
        Shot("a03_back", "{POV}: {FULL}, standing with her back to the camera, the pleated skirt over her bottom, "
                         "glancing back over her right shoulder with a teasing smile, in {OUTFIT}", flags=("face_low",)),
        Shot("a04_profile", "{POV}: three-quarter length, in profile at the window holding the end of her ponytail, "
                            "a soft smile, in {OUTFIT}", flags=("face_low",)),
        Shot("a05_ponytail", "{POV}: waist up, adjusting the elastic of her ponytail with both hands behind her head, "
                             "exactly two hands, one eyebrow raised, a warm closed-lip smile, in {OUTFIT}"),
        Shot("a06_skirt_lift", "{POV}: {FULL}, standing facing the camera, lifting the front hem of her pleated "
                               "cheer skirt with both hands to show the plum spankies underneath, {TEASE}, in {OUTFIT}"),
        Shot("a07_skirt_flip_back", "{POV}: {FULL}, standing with her back to the camera, flipping the back of her "
                                    "pleated skirt up with both hands to show the plum spankies over her bottom, "
                                    "looking back over her shoulder with a grin, in {OUTFIT}", flags=("face_low",)),
        Shot("a08_high_kick", "{POV}: {FULL}, a high cheer kick with one leg straight up, the pleated skirt flying "
                              "open, arms out, a big smile, in {OUTFIT}"),
        Shot("b01_bed_edge", "{POV}: three-quarter length, she sits on the edge of the bed facing the camera with her "
                             "palm on the mattress and a direct gaze, {PLEASED}, in {OUTFIT}"),
        Shot("b02_bed_profile", "{POV}: three-quarter length, seated on the bed edge in side profile with one hand "
                                "planted behind her, in {OUTFIT}", flags=("face_low",)),
        Shot("b03_legs_folded", "{POV}: {FULL}, sitting on the duvet with her legs folded to one side, one hand on "
                                "the bed, a soft smile, in {OUTFIT}"),
        Shot("b04_lean_in", "{POV}: waist up, seated on the bed edge leaning in toward the camera with her chin on "
                            "her hand, a teasing smile, in {OUTFIT}"),
        Shot("b05_lying_hip", "{POV}: {FULL}, lying on her side on the duvet propped on one elbow, facing the "
                              "camera, the pleated skirt riding up her thigh, {TEASE}, in {OUTFIT}"),
        Shot("b06_knees_bed", "{POV}: {FULL}, kneeling upright on the duvet facing the camera with her hands on "
                              "her thighs, {TEASE}, in {OUTFIT}"),
        Shot("b07_knees_bed_back", "{POV}: {FULL}, kneeling on the bed facing the headboard with her back to the "
                                   "camera, the pleated skirt over her bottom, head turned back over her shoulder, "
                                   "in {OUTFIT}", flags=("face_low",)),
        Shot("b08_all_fours", "{POV}: {FULL}, on all fours on the duvet facing the camera, her ponytail falling "
                              "over one shoulder, a sly smile, in {OUTFIT}"),
        Shot("c01_kneel_rug", "{POV}: {FULL}, kneeling on the rug in front of the camera sitting back on her heels, "
                              "knees together, hands meeting in a light clap, a bright smile, in {OUTFIT}"),
        Shot("c02_kneel_side", "{POV}: {FULL}, kneeling on her heels turned to the window, hands on her lap, side "
                               "view, laughing, in {OUTFIT}", flags=("face_low",)),
        Shot("c03_kneel_rear", "{POV}: {FULL}, kneeling on the rug in a rear three-quarter view, one hand on the "
                               "bench seat, looking back at the camera, in {OUTFIT}", flags=("face_low",)),
        Shot("c04_bench_forearms", "{POV}: three-quarter length, kneeling at the bench with her forearms on its "
                                   "cushion, seen from behind, the skirt over her raised bottom, a glance back "
                                   "over her shoulder, in {OUTFIT}", flags=("face_low",)),
        Shot("c05_peace", "{POV}: waist up, kneeling at the bench, a peace sign at shoulder height, a warm smile, in {OUTFIT}"),
        Shot("d01_close_chin", "{CLOSE}, chin down, eyes up, an asymmetric smile, the ponytail over one shoulder, in "
                               "{OUTFIT}", flags=("close",)),
        Shot("d02_close_bashful", "{CLOSE}, a bashful look with her eyes dropped off camera, the ponytail over her "
                                  "right shoulder, in {OUTFIT}", flags=("close",)),
        Shot("e01_tie_off", "{POV}: waist up, kneeling at the bench, slipping the elastic off her ponytail with "
                            "both hands, exactly two hands, her hair held high, in {OUTFIT}"),
        Shot("e02_hair_falls", "{POV}: waist up, she opens her hand and her long hair falls wide around her "
                               "shoulders, {TEASE}, in {OUTFIT}", alt="down"),
        Shot("e03_hair_down_bed", "{POV}: three-quarter length, sitting on the edge of the bed facing the camera with "
                                  "her hair loose down her back, drawing it forward over one shoulder with a "
                                  "warm smile, in {OUTFIT}", alt="down"),
        Shot("e04_hair_lift", "{POV}: waist up, both hands under her loose hair lifting it at the roots, exactly two "
                              "hands, chin raised, in {OUTFIT}", alt="down"),
    ))

# =============================================================================================
# 5. LIVING ROOM TEASE - 2 a.m., a last drink
# =============================================================================================
LIVING = ("Inside a modern apartment living room at 2 a.m., a charcoal velvet sofa with a broad padded arm, a "
          "brass floor lamp with a linen shade giving soft amber light, a neutral rug, a low walnut drinks "
          "cabinet with a decanter and tumblers against the left wall, a round walnut side table by the sofa, "
          "a walnut entrance door across the room, faint city glow in the window")
LIVING_SHOTS = (
    Shot("a01_door", "{POV} from the sofa: waist up, she stands in the open apartment doorway with the hall behind "
                     "her, catching the camera's eye with a surprised laugh, a clutch in one hand and the other on "
                     "the door edge, in {OUTFIT}"),
    Shot("a02_close_door", "{POV} from the sofa: {FULL}, she eases the door closed with her shoulder, glancing "
                           "toward the sofa, in {OUTFIT}"),
    Shot("a03_against_door", "{POV} from the sofa: three-quarter length, one shoulder against the closed door, chin "
                             "lifted, eyes gently closed, a relaxed smile, in {OUTFIT}"),
    Shot("a04_crouch_shoe", "{POV} from the sofa: {FULL}, crouching down by the door with her knees apart to undo the "
                            "strap of one shoe, one palm on the door, glancing up at the camera with an amused "
                            "smile, in {OUTFIT}"),
    Shot("a05_step_out", "{POV} from the sofa: {FULL}, stepping out of her second shoe looking down, lips open in "
                         "concentration, in {OUTFIT}"),
    Shot("b01_pour", "{POV} from the sofa: waist up in three-quarter view, at the drinks cabinet pouring a small "
                     "nightcap from the decanter, eyes on the stream, in {OUTFIT}"),
    Shot("b02_sip", "{POV} from the sofa: waist up, turned from the cabinet sipping, eyes over the rim toward the "
                    "camera, in {OUTFIT}"),
    Shot("b03_walk_over", "{POV} from the sofa: {FULL}, walking the last steps toward the sofa with a relaxed "
                          "half-smile, tumbler in her hand, in {OUTFIT}"),
    Shot("b04_sway", "{POV} from the sofa: three-quarter length, swaying slowly in the lamplight, weight on one foot, "
                     "a slow one-cheek smile, free hand marking the rhythm, in {OUTFIT}"),
    Shot("b05_arm_up", "{POV} from the sofa: three-quarter length, dancing with her eyes closed, one arm raised with "
                       "a soft elbow, her hair swinging, in {OUTFIT}"),
    Shot("b06_rear_turn", "{POV} from the sofa: {FULL}, pivoting into a rear three-quarter turn, the skirt over her "
                          "bottom, looking back with bright eyes about to laugh, in {OUTFIT}", flags=("face_low",)),
    Shot("b07_offer", "{POV} from the sofa: waist up, facing the camera, offering her drink playfully with her "
                      "eyebrows raised, in {OUTFIT}"),
    Shot("c01_sit_tucked", "{POV} from the sofa: three-quarter length, seated on the sofa cushion right beside the "
                           "camera with her legs folded to the side, one hand on the sofa back, a knowing "
                           "closed-lip smile, in {OUTFIT}"),
    Shot("c02_laugh", "{POV} from the sofa: waist up, laughing at a remark with her teeth briefly showing, forearm "
                      "along the sofa back, in {OUTFIT}"),
    Shot("c03_lean_in", "{POV} from the sofa: waist up, leaning in close to listen, one palm braced beside her hip "
                        "on the cushion, her face near the camera, in {OUTFIT}"),
    Shot("c04_kneel_cushion", "{POV} from the sofa: three-quarter length, risen to an upright kneel on the cushion "
                              "right beside the camera, knees on the seat, one hand on the sofa back, looking down "
                              "into the camera, in {OUTFIT}"),
    Shot("c05_kneel_tilt", "{POV} from the sofa: three-quarter length, kneeling upright on the cushion, head tipped "
                           "to one side, an amused closed-lip smile, in {OUTFIT}"),
    Shot("d01_straddle_arm", "{POV} from the sofa: {FULL}, she straddles the broad padded arm of the sofa facing the "
                             "camera, one leg on each side of it, her skirt riding up so her panties show, hands "
                             "on her thighs, {TEASE}, in {OUTFIT}"),
    Shot("d02_straddle_lean", "{POV} from the sofa: three-quarter length, straddling the sofa arm, leaning forward "
                              "toward the camera with her hands on the arm in front of her, her panties showing "
                              "under the skirt, lips parted, in {OUTFIT}"),
    Shot("d03_straddle_back", "{POV} from the sofa: {FULL}, straddling the sofa arm with her back to the camera, the "
                              "skirt up over her bottom showing her panties, looking back over her shoulder, in "
                              "{OUTFIT}", flags=("face_low",)),
    Shot("d04_straddle_hair", "{POV} from the sofa: three-quarter length, straddling the sofa arm facing the camera, "
                              "both hands lifting her hair up behind her head, exactly two hands, chest out, "
                              "her panties showing, in {OUTFIT}"),
    Shot("d05_straddle_side", "{POV} from the sofa: {FULL}, straddling the sofa arm side-on to the camera, one hand "
                              "on the arm, the skirt pushed up over her thigh, her face turned to the camera, "
                              "{TEASE}, in {OUTFIT}", flags=("face_low",)),
    Shot("d06_arm_sit_legs", "{POV} from the sofa: {FULL}, sitting sideways on the sofa arm with her legs crossed, "
                             "the skirt high on her thighs, leaning back on one hand, in {OUTFIT}"),
    Shot("e01_lie_back", "{POV} from the sofa: {FULL}, lying back along the sofa with her head on the far arm and "
                         "her knees up, the skirt fallen back to show her panties, looking at the camera, in {OUTFIT}"),
    Shot("e02_close_whisper", "{CLOSE}, she shares a quiet remark just beside the camera, in {OUTFIT}", flags=("close",)),
    Shot("e03_stretch", "{POV} from the sofa: {FULL}, standing in front of the sofa stretching both arms overhead, "
                        "eyes half closed, the crop top riding up, in {OUTFIT}"),
    Shot("e04_walk_away", "{POV} from the sofa: {FULL}, walking toward the hall with her back to the camera, a small "
                          "goodbye smile over her shoulder, in {OUTFIT}", flags=("face_low",)),
)
STORIES["livingroom"] = Story(
    title="living room tease",
    room=LIVING,
    close_room="Soft out-of-focus living room and amber lamplight behind her",
    negative="classroom, backpack, school desk",
    looks={
        # Jeremy asked for "a very schoolgirl outfit"; the first six frames in knee socks and Mary Janes read
        # 19-20 and the costume itself is the thing that reads under age, so that version was cancelled
        # (j1397) and deleted. This is the adult read of the same look: his repertoire's plaid micro mini and
        # tied-off top, with stockings, stilettos, red lips and a drink in her hand.
        "fiona": Look(hair="her hair worn loose",
                      outfit=("a tight white cropped button-up shirt tied in a knot under her breasts with the "
                              "top buttons open, a very short red plaid pleated micro mini skirt, red lace "
                              "panties, sheer black thigh-high stockings with lace tops, black stiletto heels, "
                              "red lipstick and gold hoop earrings"),
                      negative="long skirt, pants, tie, blazer, knee socks, ankle socks, flat shoes, backpack"),
        "eden": Look(hair="her hair worn loose",
                     outfit=("a sheer black lace bodysuit with a plunging neckline and high-cut legs, a tiny "
                             "black leather mini skirt, sheer black thigh-high stockings with lace tops, black "
                             "stiletto heels and gold hoop earrings"),
                     negative="long skirt, pants, blazer, jeans"),
    },
    shots=LIVING_SHOTS)

# =============================================================================================
# 6. MASSAGE
# =============================================================================================
MASSAGE_ROOM = ("Inside a quiet warm-grey living room in late afternoon, one deep cream linen sofa with a low back, "
                "tall windows on the left, a floor lamp by the sofa arm, a pale textured rug, a low walnut coffee "
                "table, an open doorway to a plain hallway ahead")
HIS_LAP = ("close point-of-view photo looking down from the eyes of a man seated on the sofa, his own thighs in "
           "grey sweatpants spread along the bottom of the frame")
STORIES["massage"] = Story(
    title="home massage",
    room=MASSAGE_ROOM,
    close_room="Soft out-of-focus living room and window light behind her",
    looks={"*": Look(
        hair="her hair up in a messy bun",
        outfit=("a tight white short-sleeved tunic with a deep V-neck and a short hem, tight black leggings "
                "and white trainers, small gold hoop earrings"),
        negative="massage table, long dress, skirt, bare feet",
        extras={"LAP": HIS_LAP})},
    shots=(
        Shot("a01_doorway", "{POV} from the sofa: {FULL}, she stands in the open doorway with a black canvas massage "
                            "bag on her shoulder, a small welcoming smile, in {OUTFIT}"),
        Shot("a02_hello", "{POV} from the sofa: {FULL}, one step in, a small greeting wave, head tilted, lips parted "
                          "saying hello, in {OUTFIT}"),
        Shot("a03_bend_bag", "{POV} from the sofa: {FULL}, beside the lamp, bending at the hips to set the bag on "
                             "the rug, the leggings tight over her bottom, in {OUTFIT}"),
        Shot("a04_bun", "{POV} from the sofa: three-quarter length, both hands behind her head tightening her messy "
                        "bun, exactly two hands, head bowed, the tunic lifting at the hem, in {OUTFIT}"),
        Shot("a05_hips", "{POV} from the sofa: three-quarter length, hands on her hips, a one-cheek smile finishing "
                         "setup, in {OUTFIT}"),
        Shot("b01_shoulders", "{POV} from the sofa looking back over the shoulder: waist up, she stands behind the low "
                              "sofa back with both palms on the shoulders of the man seated in front of her, only "
                              "the back of his head and his shoulders in the bottom of the frame, leaning slightly "
                              "forward, looking down at the camera, in {OUTFIT}", flags=("him",),
             negative="his face, a man facing the camera"),
        Shot("b02_shoulders_laugh", "{POV} from the sofa looking back over the shoulder: waist up, standing behind "
                                    "the sofa with her hands on the man's shoulders, laughing with her head tipped "
                                    "back, in {OUTFIT}", flags=("him",)),
        Shot("b03_lean_close", "{POV} from the sofa looking back over the shoulder: waist up, leaning down close over "
                               "the sofa back, her face near the camera, lips forming a short reassuring sentence, "
                               "the V-neck of the tunic falling open, in {OUTFIT}", flags=("him",)),
        Shot("c01_table_slide", "{POV} from the sofa: {FULL}, a shallow squat with both hands on the coffee table "
                                "edge sliding it aside, hips back, in {OUTFIT}"),
        Shot("c02_oil", "{POV} from the sofa: three-quarter length, standing in the cleared space holding a small "
                        "amber oil bottle at her waist, {PLEASED}, in {OUTFIT}"),
        Shot("c03_one_knee", "{POV} from the sofa: {FULL}, lowering onto one knee on the rug in front of the camera, "
                             "a hand on her raised thigh, the oil bottle in the other hand, in {OUTFIT}"),
        Shot("c04_kneel", "{POV} from the sofa: {FULL}, kneeling on both knees on the rug right in front of the "
                          "camera, sitting upright, setting the bottle on the table corner, in {OUTFIT}"),
        Shot("d01_thigh", "{LAP}: she kneels on the rug between his knees, both palms pressing into the inside of "
                          "his thigh through the sweatpants just below his crotch, looking up into the camera, "
                          "in {OUTFIT}", flags=("him",)),
        Shot("d02_thigh_smile", "{LAP}: kneeling between his knees with both palms kneading the inside of his thigh "
                                "high up near his crotch, raising her gaze with a small reassuring closed-lip "
                                "smile, in {OUTFIT}", flags=("him",)),
        Shot("d03_thigh_focus", "{LAP}: kneeling between his knees, both hands working the inside of his thigh high "
                                "up, looking down at the contact, chin lowered, lips slightly parted, in {OUTFIT}", flags=("him",)),
        Shot("d04_thigh_lean", "{LAP}: kneeling between his knees leaning forward at the hips, palms sliding up the "
                               "inside of his thigh toward his crotch, her V-neck falling open, eyes on the "
                               "camera, in {OUTFIT}", flags=("him",)),
        Shot("d05_thigh_tilt", "{LAP}: kneeling between his knees, hands resting high on the inside of his thigh, "
                               "chin raised and head tilted to her shoulder, a gradual smile, in {OUTFIT}", flags=("him",)),
        Shot("d06_both_thighs", "{LAP}: kneeling between his knees with one hand on the inside of each thigh near "
                                "his crotch, looking up from under her brows, lips parted, in {OUTFIT}", flags=("him",)),
        Shot("e01_rise", "{POV} from the sofa: {FULL}, midway rising from the rug, one foot flat, a hand braced on "
                         "her thigh, a small white towel in the other, in {OUTFIT}"),
        Shot("e02_towel", "{POV} from the sofa: three-quarter length, standing in front of the sofa wiping her hands "
                          "on a small white towel, a satisfied smile, in {OUTFIT}"),
        Shot("e03_bend_bag", "{POV} from the sofa: {FULL}, bending over to lift the packed bag by its straps, seen "
                             "from behind, the leggings tight over her bottom, looking back at the camera, in "
                             "{OUTFIT}", flags=("face_low",)),
        Shot("e04_close", "{CLOSE}, she looks into the camera with a warm one-cheek smile, a loose strand falling "
                          "from her messy bun, in {OUTFIT}", flags=("close",)),
        Shot("e05_walk_away", "{POV} from the sofa: {FULL}, walking away toward the doorway with her back to the "
                              "camera, the bag on her shoulder, in {OUTFIT}", flags=("face_hidden",)),
        Shot("e06_look_back", "{POV} from the sofa: {FULL}, at the doorway with her torso rotated for a partial look "
                              "back, eyes on the camera, in {OUTFIT}", flags=("face_low",)),
        Shot("e07_farewell", "{POV} from the sofa: {FULL}, in the doorway facing the camera, one hand lifted in a "
                             "small farewell, a warm broad smile, in {OUTFIT}"),
    ))

# =============================================================================================
# 7. CLOSING THE BAR - after hours
#    ("{POV} from the bar stool" sat HER on a stool in 9 of the first 12 frames - the hotel armchair lesson again)
# =============================================================================================
BAR = ("Inside an intimate closed cocktail bar at night, a short dark-walnut bar counter with a rounded near end "
       "right in front of the camera running back toward a backlit wall of bottles, warm amber pendant lights, "
       "brass fittings, a dark timber front door with a glass panel and a hanging sign on the left, night "
       "outside, two cut-crystal lowball tumblers with amber drinks on the bar")
STORIES["bar"] = Story(
    title="closing the bar",
    room=BAR,
    close_room="Soft out-of-focus backlit bottles and amber pendant lights behind her",
    looks={"*": Look(
        hair="her hair worn down with high, tight pigtails",
        outfit=("a black leather bustier corset laced up the front with nothing underneath, a tiny black leather "
                "mini skirt with a silver chain belt, black fishnet stockings, black ankle boots, a black velvet "
                "choker with a small silver ring and silver hoop earrings"),
        negative="apron, long skirt, pants, sneakers, bare feet, other customers, crowd")},
    shots=(
        Shot("a01_lock", "{POV}: three-quarter length, at the front door turning the lock with "
                         "her torso three-quarter away, head angled down, in {OUTFIT}", flags=("face_low",)),
        Shot("a02_sign", "{POV}: three-quarter length, flipping the hanging door sign to closed "
                         "with her chin raised, lips parted exhaling, in {OUTFIT}"),
        Shot("a03_walk_back", "{POV}: {FULL}, walking back from the door toward the bar with a "
                              "half-smile at the camera, her pigtails swinging, in {OUTFIT}"),
        Shot("b01_pour", "{POV}: waist up, behind the bar pouring the second of two drinks, chin "
                         "lowered, focused, in {OUTFIT}"),
        Shot("b02_slide", "{POV}: waist up, sliding a glass across the bar to the camera, a small "
                          "smile, eyes meeting the camera, in {OUTFIT}"),
        Shot("b03_palms", "{POV}: waist up, facing the camera behind the bar with both palms on "
                          "the edge shoulder-width apart, leaning a little forward so the corset presses her "
                          "cleavage up, lips parted, in {OUTFIT}"),
        Shot("b04_chin_knuckles", "{POV}: waist up, leaning across the bar on one elbow with her "
                                  "chin on her knuckles, a slow closed-mouth smile, in {OUTFIT}"),
        Shot("b05_laugh", "{POV}: waist up, head lifting back in a brief natural laugh, eyes "
                          "narrowed, in {OUTFIT}"),
        Shot("b06_forearms", "{POV}: waist up, both forearms on the bar, her chest nearer the "
                             "camera, chin lowered, a smile settling, in {OUTFIT}"),
        Shot("b07_turn_away", "{POV}: three-quarter length, straightening and turning toward the "
                              "end of the bar, one hand trailing the bar edge, seen from behind, the leather skirt "
                              "tight over her bottom, in {OUTFIT}", flags=("face_low",)),
        Shot("c01_around", "{POV}: {FULL}, stepping around the rounded end of the bar toward the "
                           "camera, three-quarter to it, a brief speaking expression, in {OUTFIT}"),
        Shot("c02_beside", "{POV}: three-quarter length, standing right beside the camera at the "
                           "near end of the bar, one palm on the bar, head tilted, a small asymmetrical smile, "
                           "in {OUTFIT}"),
        Shot("c03_hop_up", "{POV}: three-quarter length, settling her hips up onto the rounded near "
                           "end of the bar with her palms on the edge, gaze down at her hands, in {OUTFIT}"),
        Shot("c04_bar_sit", "{POV}: three-quarter length, seated on the bar top facing the camera "
                            "with one leg crossed over the other, the fishnets and ankle boots in view, a quiet "
                            "closed-lip smile, in {OUTFIT}"),
        Shot("c05_bar_sit_smile", "{POV}: three-quarter length, seated on the bar top with her "
                                  "legs crossed, head tilted, a broad soft smile with teeth, eyes down to the "
                                  "camera, in {OUTFIT}"),
        Shot("c06_bar_lean", "{POV}: waist up, seated on the bar top leaning forward from the "
                             "hips toward the camera, one hand on her crossed knee, in {OUTFIT}"),
        Shot("c07_bar_legs_open", "{POV}: {FULL}, seated on the bar top facing the camera with "
                                  "her knees apart and her boots on the brass rail, leaning back on her palms, "
                                  "{TEASE}, in {OUTFIT}"),
        Shot("c08_slide_off", "{POV}: three-quarter length, sliding off the bar top with her palms "
                              "pressing the edge behind her hips, boots lowering to the floor, in {OUTFIT}"),
        Shot("d01_between_knees", "{POV}: three-quarter length, standing directly in front of the "
                                  "camera very close, head inclined down to it, a gentle closed-mouth smile, her "
                                  "hands resting on the shoulders of the man on the stool, in {OUTFIT}", flags=("him",)),
        Shot("d02_closer", "{POV}: waist up, standing very close with her hands on the man's "
                           "shoulders, inclining closer, lips parted finishing a quiet sentence, in {OUTFIT}", flags=("him",)),
        Shot("d03_pigtails", "{POV}: waist up, standing close, holding one pigtail in each hand "
                             "and giving them a playful tug, exactly two hands, {TEASE}, in {OUTFIT}"),
        Shot("d04_close_toast", "{CLOSE}, raising a lowball glass toward the camera at chin height, a genuine small "
                                "smile with a little teeth, in {OUTFIT}", flags=("close",)),
        Shot("d05_close_look", "{CLOSE}, she looks straight into the camera with a slow half-smile, the choker ring "
                               "at her throat, in {OUTFIT}", flags=("close",)),
        Shot("e01_bottles", "{POV}: {FULL}, at the backlit bottles with her back to the camera, "
                            "the leather skirt tight over her bottom, torso turned for a look back, in {OUTFIT}",
             flags=("face_low",)),
        Shot("e02_bar_lie", "{POV}: {FULL}, lying on her side along the bar top propped on one "
                            "elbow facing the camera, one knee bent, {TEASE}, in {OUTFIT}"),
        Shot("e03_last_drink", "{POV}: waist up, back behind the bar, picking up her own glass "
                               "from its coaster, lips pursed considering a toast, in {OUTFIT}"),
    ))
