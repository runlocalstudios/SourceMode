"""The 28-look wardrobe plan: drafted from her record, edited and approved on the
Characters tab, and the thing that unlocks the asset pack on the Shoots tab.

Jeremy, 2026-10-12, on Ash: "She has a job and is fully filled out, but I still
can't create it for her." The pack needs `game-assets/<char>/plan_28.json` - 28
concrete outfit+hair pairs - and until now the only way to make one was a
session writing the looks by hand and running `assets plan` from a terminal.
Her wardrobe record is style guidance, not 28 outfits, so a draft is made
from it here: each category takes garment templates coloured from her palette,
the work looks are built from her job line (see `work_outfits`), and the hair
rotates through her own options. The draft is a starting point for him to
edit, not a result.

    outputs/game-assets/<char>/plan_28.draft.json   his to edit
    outputs/game-assets/<char>/plan_28.json         approved; the pack renders this

Look numbers start at 1: the pack replaces what the game ships for her.
(Drafts used to number on from her shipped looks, 29-56 after 28, which the
game cannot show - it draws looks 1..lookCount per category. Jeremy,
2026-10-21: "the new assets are supposed to replace the existing".)
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

from .catalog import PACK_28, existing_looks, make_plan, plan_slots

GAME_ROOT = Path("C:/dev/chillafterdark")
REFS = Path("C:/Epic Games/Files/cnc info/codex/references")

#: pack category -> the wardrobe record's outfit type that guides it
CATEGORY_TYPE = {"casual": "everyday", "workout": "workout", "fancy_dining_gallery": "dressy",
                 "fancy_town": "night_out", "casual_date": "date", "work": "job"}
CATEGORY_LABEL = {"casual": "Casual", "workout": "Workout", "fancy_dining_gallery": "Fancy - dining, gallery",
                  "fancy_town": "Fancy - town, club", "casual_date": "Casual date", "work": "Work"}

# {c} is a colour from her palette. Each character SAMPLES her looks from these
# pools, so two characters do not wear the same garments on the same days.
# Jeremy, 2026-10-12, when the pools were eight deep and everyone drew all of
# them: "every single character will look exactly the same on the same days ...
# the same thing with just different colors." Keep every pool at least three
# times the count the pack asks for.
TEMPLATES: dict[str, tuple[str, ...]] = {
    "casual": (
        "a fitted {c} t-shirt tucked into high-waisted light-wash jeans",
        "a {c} ribbed tank top and denim shorts",
        "a cropped {c} knit sweater over a short pleated skirt",
        "an oversized {c} button-up shirt worn open over a white cami and jeans",
        "a {c} sundress with thin straps",
        "a {c} cropped hoodie and bike shorts",
        "a {c} and white striped long-sleeve tee and a denim mini skirt",
        "a {c} bodysuit tucked into straight-leg jeans",
        "a {c} linen shirt knotted at the waist over cut-off denim shorts",
        "an oversized {c} graphic tee worn as a dress with a thin belt",
        "a {c} henley and distressed boyfriend jeans",
        "{c} overalls over a white cropped tee",
        "a {c} baby tee and low-rise cargo pants",
        "a {c} off-the-shoulder knit top and a denim skirt",
        "a {c} tube top under an open denim jacket with jeans",
        "a {c} tennis skirt and a white cropped polo",
        "a {c} plaid flannel tied at the waist over a white tank top and shorts",
        "a {c} crewneck sweatshirt and a pleated mini skirt",
        "a {c} satin cami tucked into high-waisted jeans",
        "a {c} corduroy mini skirt and a fitted white turtleneck",
        "a {c} knit cardigan buttoned up with nothing under it, and faded jeans",
        "a {c} racer-back jumpsuit",
        "a {c} crop top and a flowing white maxi skirt",
        # Jeremy, 2026-10-15: "form-fitting pastel pink long-sleeve square-neckline
        # romper, stretchy knit fabric, short mid-thigh shorts, one-piece outfit"
        # - more like it, across the pools. Jeremy, 2026-10-24: "you are drafting
        # too many rompers" - three of the six went, and a category draws at
        # most one one-piece unless her line asks for them (guided_templates)
        "a form-fitting {c} long-sleeve square-neckline romper in stretchy knit fabric, with short mid-thigh shorts",
        "a {c} ribbed knit romper with spaghetti straps and short shorts, one piece",
        "a {c} zip-front knit romper with short shorts, the zip pulled down a little",
        "a fitted {c} long-sleeve knit unitard cut to mid-thigh, worn as the whole outfit",
        # Jeremy, 2026-10-20, kasia's "Chic professional looks": the pool above is
        # streetwear and had nothing chic to find - polished daytime looks
        "a {c} silk blouse tucked into a high-waisted pencil skirt",
        "a {c} fine-knit polo tucked into tailored wide-leg trousers",
        "a {c} sleeveless mock-neck knit top and tailored high-waisted shorts",
        "a cropped {c} tweed jacket over a matching mini skirt",
        "a {c} fitted knit midi dress cinched with a thin belt",
        "a {c} wrap blouse and tailored cigarette trousers",
        "a {c} satin button-up shirt tucked into a tailored mini skirt",
        "a {c} fitted vest worn as a top with tailored trousers",
    ),
    "workout": (
        "a {c} sports bra and matching high-waisted leggings",
        "a {c} racerback tank over a black sports bra and bike shorts",
        "a {c} seamless crop top and leggings set",
        "a cropped {c} zip hoodie over a sports bra and running shorts",
        "a {c} longline sports bra and flared yoga pants",
        "a {c} one-piece athletic unitard",
        "a {c} tennis dress with built-in shorts",
        "a {c} mesh-panel sports bra and matching cycling shorts",
        "a {c} tank top and running shorts with a split hem",
        "a {c} crop top and high-waisted joggers",
        "a {c} sports bra under an open black mesh tank, with leggings",
        "a {c} ribbed workout onesie unzipped to the sternum",
        "a {c} halter sports bra and flared leggings",
        "a {c} baggy sweatshirt pulled off one shoulder over a sports bra and bike shorts",
        "a {c} scoop-neck bodysuit and wide-leg track pants",
        "a {c} strappy-back sports bra and a wrap skirt over leggings",
        "a {c} track jacket zipped halfway over a sports bra and leggings",
        "a {c} stretchy knit one-piece with a square neckline and short mid-thigh shorts",
        "a {c} long-sleeve athletic romper with built-in bike shorts",
        "a {c} ribbed knit shorts-unitard with thin straps, cut close to the body",
    ),
    "fancy_dining_gallery": (
        "a {c} satin midi dress with a cowl neckline",
        "a tailored {c} blazer dress",
        "a {c} silk slip dress with a draped neckline",
        "a fitted {c} knee-length sheath dress",
        "a {c} off-the-shoulder cocktail dress",
        "a {c} wrap midi dress with a slit",
        "a {c} one-shoulder jersey dress",
        "a {c} tailored jumpsuit with a plunging neckline",
        "a {c} lace midi dress over a nude lining",
        "a {c} velvet slip dress",
        "a {c} halter-neck midi dress with an open back",
        "a {c} pleated satin skirt and a fitted black bodysuit",
        "a {c} tuxedo-style blazer with nothing under it and wide-leg trousers",
        "a {c} square-neck fitted dress with puff sleeves",
        "a {c} silk shirt dress cinched with a belt",
        "a {c} strapless column dress",
        "a {c} ruched mesh midi dress",
        "a {c} high-neck sleeveless midi dress",
        "a {c} draped satin wrap top and a long bias-cut skirt",
        "a {c} fitted long-sleeve midi dress with a keyhole neckline",
        # no rompers here - Jeremy, 2026-10-24: "rompers are casual outfits,
        # possibly date outfits, almost never fancy town outfits unless it's a
        # statement piece"; the tailored jumpsuit above is the one one-piece
        # kasia's dressy line, 2026-10-20: "Midriff tops and short skirts, short
        # dresses" - the pool had no crop top and few short hems
        "a {c} satin cropped bustier top and a tailored mini skirt",
        "a cropped {c} tailored jacket buttoned over a bare midriff, with a matching mini skirt",
        "a {c} cropped corset top and a satin mini skirt",
        "a {c} satin mini dress with a square neckline",
        "a {c} structured strapless mini dress",
    ),
    "fancy_town": (
        "a {c} sequined mini dress",
        "a {c} bodycon dress with a deep neckline",
        "a {c} corset top and a leather mini skirt",
        "a sheer {c} mesh top over a bralette and tailored black trousers",
        "a {c} cut-out halter mini dress",
        "a {c} latex-look mini dress",
        "a {c} chainmail halter top and black leather shorts",
        "a {c} bandage dress with a thigh-high slit",
        "a {c} bralette under a sheer black maxi dress",
        "a {c} satin mini slip dress with a cowl neck",
        "a {c} vinyl mini skirt and a black lace bodysuit",
        "a {c} backless halter jumpsuit",
        "a {c} rhinestone-strap mini dress",
        "a {c} ruched one-shoulder mini dress",
        "a {c} crop top and a high-slit satin maxi skirt",
        "a {c} bustier top and leather trousers",
        "a {c} micro mini dress with a lace-up front",
        "a {c} satin bustier and wide-leg black trousers",
        "a {c} fringe mini dress",
        "a {c} sheer mesh long-sleeve dress over a black bra and thong",
        # the one romper a night out allows: a statement piece (Jeremy, 2026-10-24)
        "a {c} sequined long-sleeve romper with a plunging neckline",
    ),
    "casual_date": (
        "a {c} wrap dress",
        "a {c} off-the-shoulder top and a denim skirt",
        "a fitted {c} knit top and a high-waisted midi skirt",
        "a {c} slip dress under a cropped denim jacket",
        "a {c} floral sundress with a sweetheart neckline",
        "a {c} smocked milkmaid top and a flowy midi skirt",
        "a {c} knit halter dress",
        "a {c} ruffled mini dress with flutter sleeves",
        "a {c} satin cami and a leather mini skirt",
        "a {c} tie-front crop top and wide-leg linen trousers",
        "a {c} square-neck mini dress with a cardigan over her shoulders",
        "a {c} fitted ribbed dress with a scoop neck",
        "a {c} blouse with balloon sleeves tucked into a denim mini skirt",
        "a {c} crochet top and a flowing skirt",
        "a {c} corset-waist midi dress",
        "a {c} bodysuit under high-waisted wide-leg trousers",
        "a {c} tiered sundress with a square neckline",
        "a {c} off-the-shoulder midi dress",
        "a {c} fitted turtleneck mini dress",
        "a {c} satin slip skirt and a cropped knit top",
        "a form-fitting {c} long-sleeve square-neckline romper in stretchy knit fabric, short mid-thigh shorts",
        "a {c} stretchy knit halter romper with mid-thigh shorts, one piece",
    ),
}

# JEWELRY AND A BAG. Jeremy, 2026-10-24: "i also felt like we had added jewelry
# and handbags at some point in fancy/town looks and they are never present
# currently ... i won't want crazy jewelry and a handbag on every piece - roll
# jewelry at 50% on each look to sort of match the kind of look, and roll a
# handbag at 25% odds so maybe 1 of 4 fancy looks gets a handbag (on average)
# and half the looks get earrings and a necklace." The jewelry was in the
# retired August contract prompt and never reached the plan lines. Work looks
# are her uniform and workout has none; the other four roll per look, the
# jewelry in the category's register, the bag only on the two fancy categories.
JEWELRY: dict[str, tuple[str, ...]] = {
    "casual": (
        "small gold hoop earrings and a thin chain necklace",
        "small silver stud earrings and a delicate pendant necklace",
        "small gold hoop earrings and a dainty layered necklace",
    ),
    "casual_date": (
        "small gold hoop earrings and a dainty pendant necklace",
        "pearl stud earrings and a thin gold necklace",
        "small drop earrings and a delicate chain necklace",
    ),
    "fancy_dining_gallery": (
        "drop earrings and a delicate pendant necklace",
        "pearl earrings and a fine gold chain necklace",
        "small diamond stud earrings and a slim gold necklace",
    ),
    "fancy_town": (
        "long drop earrings and a thin layered necklace",
        "oversized gold hoop earrings and a delicate necklace",
        "sparkling drop earrings and a slim choker necklace",
    ),
}
HANDBAGS: tuple[str, ...] = (
    "a small {c2} clutch in her hand",
    "a small {c2} leather clutch in her hand",
    "a mini {c2} shoulder bag",
)
BAG_CATEGORIES = ("fancy_dining_gallery", "fancy_town")
JEWELRY_ODDS, HANDBAG_ODDS = 0.5, 0.25
_WEARS_JEWELRY_RE = re.compile(r"earrings?|necklace|choker|jewel|pendant", re.I)
_CARRIES_BAG_RE = re.compile(r"clutch|handbag|shoulder bag|purse|\bbag\b", re.I)
#: the accessory clause a look ends with, for anything that reads garments only
ACCESSORY_RE = re.compile(r", with (?:[^,]*\b(?:earrings|necklace|clutch|shoulder bag)\b[^,]*)$", re.I)


def accessorise(look: str, cat: str, rng: random.Random, colours: list[str],
                ban: re.Pattern | None = None, plain: bool = False) -> str:
    """Her jewelry on about half the looks, a bag on about a quarter of the
    fancy ones, in a clause the look ends with. The rolls are drawn for every
    category so a seed's garments do not move when a category gains or loses
    the clause; nothing is added where her line already names it or her
    "Never wears" line rules it out."""
    jewel = rng.random() < JEWELRY_ODDS
    bag = rng.random() < HANDBAG_ODDS
    if not look or cat not in JEWELRY:
        return look
    bits = []
    if jewel and not _WEARS_JEWELRY_RE.search(look):
        fit = [j for j in JEWELRY[cat] if not avoids(j, ban)]
        if fit:
            bits.append(rng.choice(fit))
    if bag and cat in BAG_CATEGORIES and not _CARRIES_BAG_RE.search(look):
        fit = [b for b in HANDBAGS if not avoids(b, ban)]
        if fit:
            pool = ["black"] if plain else _allowed(
                [c for c in colours if not re.search(rf"\b{re.escape(c)}\b", look, re.I)] or ["black"], ban)
            bits.append(rng.choice(fit).format(c2=rng.choice(pool)))
    return f"{look}, with {' and '.join(bits)}" if bits else look

# Colour words a palette line may carry, longest first so "denim blue" wins
# over "blue". A trailing s is allowed ("dark grays and blacks"). Anything else
# in the line is prose and is ignored - unless it is a colour FAMILY, below.
_COLOURS = ("burnt orange", "denim blue", "navy blue", "baby blue", "sky blue", "royal blue",
            "cobalt blue", "slate blue", "electric blue", "pale blue", "soft blue", "powder blue",
            "hot pink", "blush pink", "dusty pink", "pale pink", "pastel pink", "soft pink",
            "forest green", "sage green", "olive green", "emerald green", "deep red", "wine red",
            "cherry red", "ruby red", "chocolate brown", "light grey", "light gray", "lemon yellow",
            "off-white",
            "black", "white", "cream", "ivory", "beige", "tan", "camel", "brown", "chocolate",
            "oatmeal", "bone", "ecru", "stone", "taupe", "khaki", "nude", "sand",
            # no "copper", no "platinum": his palette lines mention hair colour
            "grey", "gray", "charcoal", "slate", "silver", "gold", "bronze", "champagne",
            "navy", "cobalt", "indigo", "blue", "teal", "turquoise", "aqua", "sapphire",
            "green", "olive", "sage", "emerald", "mint", "lime", "yellow", "mustard",
            "orange", "coral", "peach", "terracotta", "rust", "red", "burgundy", "maroon", "wine",
            "pink", "rose", "fuchsia", "magenta", "mauve", "purple", "lavender", "lilac", "plum",
            "violet", "amethyst", "denim")
_COLOUR_RE = re.compile(r"\b(" + "|".join(re.escape(c) for c in _COLOURS) + r")s?\b", re.I)
DEFAULT_COLOURS = ("black", "white", "navy", "red", "cream", "olive", "blush pink")

# Colour FAMILIES. Jeremy, 2026-10-17, after Winnie's 28 looks all came out white
# from "White with primary colors": "i want the parser to understand common
# phrases like primary colors, secondary colors, earthy tones, vivid colors, etc.
# i don't want to have to type things out color by color it's more of a style or
# warmth of the character and their style than picking 6 individual colors."
# Each family is the colours a stylist would reach for, in an order that keeps
# neighbouring looks apart. The key is a regex over the adjective; it may be
# followed by up to two words and then a noun - colours, tones, shades, hues,
# accents, highlights, palette - or stand alone where the word itself is the
# family (pastels, neutrals, metallics, monochrome).
_FAMILY_NOUN = r"(?:\s+\w+){0,2}\s+(?:colou?rs?|tones?|shades?|hues?|accents?|highlights?|palette)"
_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (r"primary" + _FAMILY_NOUN, ("red", "blue", "yellow")),
    (r"secondary" + _FAMILY_NOUN, ("green", "orange", "purple")),
    (r"tertiary" + _FAMILY_NOUN, ("teal", "coral", "violet", "lime", "amber", "magenta")),
    (r"(?:earth|earthy|natural)" + _FAMILY_NOUN, ("rust", "olive", "camel", "terracotta", "chocolate brown", "mustard", "cream")),
    (r"warm\s+neutrals?", ("cream", "camel", "taupe", "chocolate brown", "rust", "oatmeal")),
    (r"cool\s+neutrals?", ("white", "grey", "charcoal", "slate blue", "black", "stone")),
    (r"neutrals?(?:" + _FAMILY_NOUN + r")?", ("black", "white", "cream", "grey", "camel", "taupe")),
    (r"pastels?(?:" + _FAMILY_NOUN + r")?|soft" + _FAMILY_NOUN, ("pale pink", "baby blue", "mint", "lavender", "lemon yellow", "peach")),
    (r"(?:vivid|bright|bold|vibrant|saturated|loud|pop(?:py)?)" + _FAMILY_NOUN, ("hot pink", "cobalt blue", "emerald green", "red", "orange", "yellow")),
    (r"jewel" + _FAMILY_NOUN, ("emerald green", "sapphire", "ruby red", "amethyst", "teal", "gold")),
    (r"(?:dark|deep|moody|rich|dramatic)" + _FAMILY_NOUN + r"|darks\b", ("black", "charcoal", "navy", "burgundy", "forest green", "plum")),
    (r"(?:muted|subdued|dusty|faded|washed[- ]out|soft\s+muted|quiet)" + _FAMILY_NOUN, ("dusty pink", "sage green", "slate blue", "mauve", "oatmeal", "taupe")),
    (r"warm" + _FAMILY_NOUN, ("rust", "burnt orange", "mustard", "terracotta", "wine red", "camel")),
    (r"cool" + _FAMILY_NOUN, ("navy", "teal", "slate blue", "lavender", "grey", "mint")),
    (r"monochrome|monochromatic|black[- ]and[- ]white|grey ?scale|gray ?scale", ("black", "white", "grey", "charcoal")),
    (r"metallics?(?:" + _FAMILY_NOUN + r")?", ("gold", "silver", "bronze", "champagne")),
    (r"(?:autumn|fall)" + _FAMILY_NOUN, ("rust", "mustard", "olive", "burgundy", "chocolate brown", "camel")),
    (r"spring" + _FAMILY_NOUN, ("pale pink", "mint", "lemon yellow", "lilac", "sky blue", "white")),
    (r"summer" + _FAMILY_NOUN, ("white", "coral", "turquoise", "lemon yellow", "hot pink", "sky blue")),
    (r"winter" + _FAMILY_NOUN, ("black", "white", "navy", "burgundy", "emerald green", "silver")),
    (r"nautical(?:" + _FAMILY_NOUN + r")?", ("navy", "white", "red")),
    (r"all[- ]black|head[- ]to[- ]toe black", ("black",)),
)
_FAMILY_RE = re.compile(r"\b(?:" + "|".join(f"(?P<f{i}>{p})" for i, (p, _) in enumerate(_FAMILIES)) + r")\b", re.I)


def palette_families(palette: str) -> list[str]:
    """The family phrases the line carries, as written - for the tab to echo back."""
    return [m.group(0) for m in _FAMILY_RE.finditer(palette or "")]


def palette_colours(palette: str) -> tuple[str, ...]:
    """The colours her palette line names, in order of appearance, no repeats.

    A colour word counts once; a family phrase ("primary colors", "earth
    tones", "pastels") expands to its colours at the place it appears, so
    "white with primary colors" reads white, red, blue, yellow - not white,
    white, white. A line that names neither gets the defaults."""
    return _colours_in(palette) or DEFAULT_COLOURS


# NEVER WEARS. Jeremy, 2026-10-18: "i told the app that hannah never wears
# denim, yet it still put her in jeans a lot". The tab's "Never wears" line was
# saved and shown and never read - four of her 28 approved looks were denim.
# These are the words the generator acts on: a phrase as he would write it in
# her line, and the forms it takes on a template, a steer cue or a colour. A
# look, a cue or a colour that carries one is never offered to her. Colours and
# colour families in the line ("pastels", "bright colour") come off her palette
# the same way. Prose ("nothing prim or preppy") is for him; the code only acts
# on words it can match.
_AVOID_WORDS: tuple[tuple[str, str], ...] = (
    (r"denim|jeans|chambray", r"denim|jeans|chambray"),
    (r"leather|suede", r"leather|suede"),
    (r"lace|lacy", r"\blace\b|lacy"),
    (r"satin|silk|silky", r"satin|silk"),
    (r"sequins?|sparkl\w*|glitter\w*", r"sequin|glitter|sparkl"),
    (r"vinyl|latex|pvc", r"vinyl|latex|pvc"),
    (r"sheer|mesh|see[- ]through", r"sheer|mesh|see-through"),
    (r"velvet", r"velvet"),
    (r"fur", r"\bfur\b|faux-fur"),
    (r"crop(?:ped)?(?: tops?)?|midriff", r"crop|midriff"),
    (r"mini ?skirts?|micro ?skirts?|micro ?minis?", r"mini skirt|micro"),
    (r"shorts", r"\bshorts\b"),
    (r"leggings", r"leggings"),
    (r"hoodies?|sweatshirts?", r"hoodie|sweatshirt"),
    (r"heels|stilettos?", r"heels|stiletto|pumps"),
    (r"sneakers|trainers", r"sneakers|trainers"),
    (r"plunging(?: necklines?)?|low[- ]cut|cleavage", r"plunging|neckline cut low|low-cut|deep v"),
    (r"high (?:collars?|necks?)|turtlenecks?", r"turtleneck|high-neck|high collar"),
    (r"bodysuits?", r"bodysuit"),
    (r"rompers?|jumpsuits?|unitards?|onesies?|overalls", r"romper|jumpsuit|unitard|onesie|overalls"),
    (r"blazers?|suits?", r"\bsuit\b|blazer|pantsuit"),
    (r"prints?|patterns?|graphics?|logos?", r"print|floral|stripe|gingham|plaid|polka|graphic|leopard|animal"),
    (r"strapless", r"strapless|tube|bandeau"),
    (r"halters?", r"halter"),
    (r"bikinis?|swimwear", r"bikini|swimsuit|one-piece"),
    (r"jewel\w*|earrings?|necklaces?|chokers?", r"earrings|necklace|choker|pendant"),
    (r"handbags?|purses?|clutch(?:es)?|bags?", r"clutch|handbag|shoulder bag|purse"),
)


def _word_bans(phrase: str, item: str) -> bool:
    """Whether a known word in one item of her line bans its whole family. Not
    when it is only the head of a qualified garment: kasia's "cargo shorts"
    banned every pair of shorts - and with them every unitard cut to the
    thigh, which is what her "Jumpsuits" workout line asked for (2026-10-20).
    "cargo shorts" bans cargo shorts; "shorts" alone bans shorts."""
    m = re.search(rf"\b(?:{phrase})\b", item, re.I)
    if not m:
        return False
    words = [w for w in re.findall(r"[a-z]+", item.lower()) if w not in _PHRASE_STOP]
    qualified = GARMENT_RE.search(item) and len(words) >= 2 and m.group(0).lower() == words[-1]
    return not qualified


def banned(avoid: str) -> re.Pattern | None:
    """A matcher for what her "Never wears" line rules out, None when the line
    carries nothing the generator knows how to act on."""
    pats = [rx for phrase, rx in _AVOID_WORDS
            if any(_word_bans(phrase, item) for item in re.split(r"[,;]", avoid or ""))]
    # whole words: "red" must not ban "tailored"
    pats += [rf"\b{re.escape(c)}s?\b" for c in _colours_in(avoid)]
    pats += _avoid_phrases(avoid)
    return re.compile(r"(?:" + "|".join(pats) + r")", re.I) if pats else None


_PHRASE_STOP = {"a", "an", "the", "as", "of", "with", "in", "on", "to", "her", "she", "or", "and",
                "no", "nothing", "never", "any", "anything"}


def _avoid_phrases(avoid: str) -> list[str]:
    """Each short item of her line as a whole-word, any-order match.

    Jeremy, 2026-10-20: "The restriction on never wears cargo pants is not
    working." Kasia's line reads "Denim, cargo pants, cargo shorts, oversized
    tee worn as a dress" and only "Denim" was on the word list above - her
    draft carried "a navy baby tee and low-rise cargo pants" and "an oversized
    blush pink graphic tee worn as a dress". So every comma item he writes is
    matched as itself: all of its words, in any order, on one look - when the item names a garment. What
    follows a dash ("nothing prim or preppy - she is...") is prose, skipped."""
    out = []
    # everything after a dash is prose about her, never a list of garments
    for item in re.split(r"[,;]", re.split(r" [-–] ", avoid or "")[0]):
        if not GARMENT_RE.search(item):       # "nothing prim or preppy" names no garment
            continue
        words = [_singular(w) for w in re.findall(r"[a-z]+", item.lower()) if w not in _PHRASE_STOP]
        if not words or len(words) > 5 or (len(words) == 1 and len(words[0]) < 4):
            continue
        out.append("".join(rf"(?=.*\b{re.escape(w)}(?:e?s)?\b)" for w in words) + ".")
    return out


def avoids(text: str, ban: re.Pattern | None) -> bool:
    return bool(ban and ban.search(text or ""))


def _colours_in(palette: str) -> tuple[str, ...]:
    """`palette_colours` without the fallback: () when the line names none."""
    found: list[tuple[int, tuple[str, ...]]] = []
    for m in _FAMILY_RE.finditer(palette or ""):
        i = next(k for k in range(len(_FAMILIES)) if m.group(f"f{k}"))
        found.append((m.start(), _FAMILIES[i][1]))
    covered = [(m.start(), m.end()) for m in _FAMILY_RE.finditer(palette or "")]
    for m in _COLOUR_RE.finditer(palette or ""):
        # "black and white" the family already said black and white
        if any(a <= m.start() < b for a, b in covered):
            continue
        found.append((m.start(), (m.group(1).lower(),)))
    seen: list[str] = []
    for _, cols in sorted(found, key=lambda t: t[0]):
        for c in cols:
            if c not in seen:
                seen.append(c)
    return tuple(seen)


# --- work looks ------------------------------------------------------------------
# Jeremy, 2026-10-12: "They're not going to wear the same fucking thing every
# day." One job line in her record becomes five work looks, and the KIND of job
# decides how. A uniform stays a uniform and varies in the small things - sleeves,
# an apron, a cardigan. A job she dresses herself for - the Chill Trap, a
# boutique, an office, a gallery - gets five different outfits in that job's
# register, coloured from her palette. Look 1 is always her own line.
#
# `{base}` is her job line with its "Obsidian waitress:" label stripped; `{c}`
# is a palette colour. First matching kind wins, so the specific ones go first.
WORK_KINDS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("medical", r"nurse|hospital|scrubs|medical|clinic|doctor|dentist|vet\b", (
        "{base}",
        "{c} scrubs with a white long-sleeve tee underneath",
        "{c} scrubs with a fleece zip jacket over the top",
        "scrubs with a {c} printed top and plain trousers",
        "{c} scrubs with a stethoscope around her neck",
        "a white lab coat open over {c} scrubs",
    )),
    ("dancer", r"dancer|stripper|chill trap|strip club|pole|burlesque|stage name|exotic", (
        "{base}",
        # Jeremy, 2026-10-22, from a reference photo: a one-piece sheer fishnet
        # sling - halter strap, mesh triangle cups, thin straps down to a thong.
        # Second so a dancer's five looks always draw it (looks are positional).
        "a sheer {c} fishnet sling bikini with a halter neck strap and mesh triangle cups "
        "running down to a thong cut and clear heels",
        "a {c} satin bralette with matching micro shorts and a sheer wrap skirt",
        "a {c} lace bodysuit cut high on the hip with sheer black thigh-highs",
        "a {c} sequin two-piece - a tiny bra top and a thong-cut bottom",
        "a {c} mesh mini dress worn over a black bra and thong set",
        "a {c} halter bikini top with a black micro skirt and clear heels",
    )),
    ("stage", r"\bband\b|stage|singer|musician|perform|\bdj\b|venue|show night", (
        "{base}",
        "a {c} satin bralette with high-waisted black trousers",
        "a {c} sequin crop top and a black micro skirt",
        "a {c} corset top with leather trousers",
        "a {c} mesh long-sleeve over a bralette and a mini skirt",
        "a {c} slip dress with a studded belt and ankle boots",
    )),
    ("boutique", r"boutique|clothing|fashion|threads|le chic|shop floor|stylist|retail", (
        "{base}",
        "a {c} satin blouse half-tucked into wide-leg trousers",
        "a fitted {c} turtleneck with a leather midi skirt",
        "a {c} blazer worn over a bralette with straight-leg jeans",
        "a {c} knit midi dress with a slim belt",
        "a {c} silk cami with high-waisted tailored shorts",
    )),
    ("gallery", r"gallery|curator|museum|art dealer", (
        "{base}",
        "a {c} column dress with a square neckline",
        "an oversized {c} blazer over a black turtleneck and slim trousers",
        "a {c} silk shirt with a black mini skirt and sheer tights",
        "a {c} asymmetric midi dress",
        "a {c} sleeveless turtleneck with wide-leg trousers",
    )),
    ("fitness", r"yoga|trainer|\bgym\b|fitness|pilates|coach", (
        "{base}",
        "a {c} sports bra and matching high-waisted leggings",
        "a {c} racerback tank over a black sports bra and bike shorts",
        "a cropped {c} zip hoodie over a sports bra and leggings",
        "a {c} longline sports bra and flared yoga pants",
        "a {c} seamless crop top and matching bike shorts",
    )),
    ("academic", r"teach|professor|lecturer|university|tutor|school", (
        "{base}",
        "a {c} cardigan over a blouse with a pleated midi skirt",
        "a {c} tie-neck blouse with tailored trousers",
        "a {c} knit dress with a slim belt",
        "a {c} button-up shirt tucked into an A-line skirt",
        "a {c} turtleneck under a pinafore dress",
    )),
    ("modest", r"church|volunteer|librar|charity|pastor|parish", (
        "{base}",
        "a {c} long-sleeve midi dress",
        "a {c} jumper with straight-leg jeans",
        "a {c} blouse with a knee-length skirt",
        "a {c} cardigan over a shirt dress",
        "a {c} blouse with wide-leg trousers",
    )),
    ("preppy", r"preppy|collegiate|\bivy\b|prep school|sorority", (
        "{base}",
        "a {c} pleated mini skirt with a white collared shirt and a sweater vest",
        "a {c} cable-knit sweater over a collared shirt with a plaid mini skirt",
        "a fitted {c} polo dress",
        "a white button-up tied at the waist with a {c} pleated skirt",
        "a {c} tennis skirt and a cropped argyle sweater",
        "a {c} cardigan buttoned over a white tee with cropped chinos",
    )),
    ("office", r"office|assistant|executive|professional|business|corporate|manager|real[- ]estate|agent|"
               r"\bsales\b|\brep\b|consultant|recruit|account|lawyer|paralegal|property|analyst|\bdesk\b", (
        "{base}",
        "a tailored {c} blazer over a silk cami with a pencil skirt",
        "a {c} sheath dress with a thin belt",
        "a {c} silk shirt tucked into high-waisted tailored trousers",
        "a fitted {c} knit top with wide-leg trousers and a long blazer",
        "a {c} sleeveless blouse tucked into a high-waisted midi skirt",
        "a {c} wrap top with tailored cigarette trousers",
    )),
)

# A job line that names no garment is a brief, not an outfit - priya's "Chic
# professional outfits that are a little too revealing" drafted as work look 1
# verbatim. Jeremy, 2026-10-13: "I want the descriptions on the top to guide
# the design of the outfits, so if I say slutty professional up top that should
# guide the outfit prompts." A brief places the job by its words and every look
# is a template; its register words (below) shape each one.
GARMENT_RE = re.compile(
    r"blazer|skirt|dress|trouser|pants?\b|jeans?|shirt|blouse|\btops?\b|\btee\b|t-shirt|scrubs|uniform|cami|"
    r"bodysuit|apron|waistcoat|jacket|legging|shorts?\b|sweater|cardigan|jumper|\bknit\b|polo|hoodie|"
    r"bralette|\bbra\b|corset|\bsuit\b|romper|jumpsuit|overalls?|skort|\bvest\b|\bcoat\b|tunic|kimono|"
    r"bikini|swimsuit|tights|stockings|turtleneck|tank\b|sports bra|\bset\b|\bmini\b|\bmidi\b|\bmaxi\b|"
    r"bodycon|gown|lingerie|heels|boots|sneakers", re.I)

# What a brief asks for, in the words he writes. A cue is chosen per look from
# the ones that garment can carry: (cue, needs, never) - a hem cue wants a skirt
# or dress, "unbuttoned" wants buttons, nothing is cropped twice.
_HEM = r"skirt|dress"
REGISTERS: tuple[tuple[str, str, tuple[tuple[str, str, str], ...]], ...] = (
    ("revealing", r"reveal|slutty|sexy|skimpy|provocative|racy|daring|flirty|teas|risqu|scandal|\bsheer\b|"
                  r"show(?:s|ing)? (?:off )?(?:skin|cleavage|leg)|cleavage|low[- ]cut|barely", (
        ("the neckline cut low", "", r"turtleneck|high-neck|halter|strapless|tube|bandeau|hoodie|sweatshirt|"
                                     r"jacket|track|off-the-shoulder|one-shoulder|sports bra|plunging|cowl|unzipped|bustier|corset|bikini"),
        ("unbuttoned to the sternum", r"shirt|blouse|button|cardigan|blazer|polo|henley", r"unbuttoned|tied at|knotted"),
        ("cut close to the body", "", r"fitted|fitting|bodycon|sheath|bandage|close-fitting|close to the body|seamless|latex"),
        ("the fabric sheer enough to show the bra beneath",
         r"dress|blouse|shirt|\btee\b|knit|cami|bodysuit|\btop\b", r"sheer|mesh|lace|jacket|hoodie|sweatshirt|track|sports bra|bralette|leather|vinyl|latex|sequin"),
        ("the top cropped to show her midriff",
         r"\btop\b|\btee\b|shirt|sweater|blouse|knit|hoodie|sweatshirt|tank|polo|henley|cardigan",
         r"crop|dress|jumpsuit|unitard|onesie|one-piece|romper|bodysuit|overalls|tucked|corset|bustier|bralette|bikini|tube|"
         r"worn open|knotted|tied at"),
        ("the hem cut well above mid-thigh", _HEM, r"mini|micro|short|tennis"),
        ("with a slit up the thigh", _HEM, r"slit|mini|micro|short|tennis"),
    )),
    ("modest", r"modest|conservative|demure|buttoned[- ]up|\bprim\b|\bproper\b", (
        ("a high neckline", "", r"off-the-shoulder|one-shoulder|strapless|halter|cowl|plunging|slip|cami|sports bra|"
                                r"turtleneck|high-neck|tube|bandeau|scoop|square-neck|sweetheart"),
        ("sleeves to the wrist", "", r"sleeveless|tank|cami|strapless|halter|\btee\b|sports bra|short-sleeve|slip|tube|long-sleeve"),
        ("loose through the body", "", r"fitted|bodycon|sheath|wrap|corset|bandage|close-fitting|seamless|slim|column"),
        ("buttoned to the collar", r"shirt|blouse|cardigan|button", r"unbuttoned|tied at|knotted"),
        ("the hem at the knee", _HEM, r"mini|micro|midi|maxi|knee|long"),
        ("the hem below the knee", _HEM, r"mini|micro|knee|long|maxi"),
    )),
)


# A line is still a brief when it names garments in the plural or as options:
# "Flirty shorts and tight shirts" drafted as a uniform with an apron over it.
# Inherently plural garments (shorts, jeans, trousers, scrubs) do not count.
_PLURAL_RE = re.compile(
    r"\b(?:shirts|blouses|tops|tees|t-shirts|dresses|skirts|blazers|jackets|sweaters|cardigans|bodysuits|"
    r"camis|bralettes|corsets|rompers|jumpsuits|polos|hoodies|tunics|uniforms|minis|gowns|suits|sets|"
    r"bikinis|swimsuits|turtlenecks|tanks|knits|vests|coats|aprons|waistcoats|jumpers|kimonos|outfits?|"
    r"wear|looks)\b", re.I)
_OR_RE = re.compile(r"\bor\s+(\w[\w-]*)", re.I)


def is_brief(outfit: str) -> bool:
    """True when the line describes a style rather than one outfit: it names
    no garment, or names them in the plural, or offers a choice of garments
    ("a dress or a jumper"; "rust or brown trousers" is one outfit)."""
    base = job_base(outfit)
    if not base:
        return False
    choice = any(not _COLOUR_RE.fullmatch(m.group(1)) for m in _OR_RE.finditer(base))
    return not GARMENT_RE.search(base) or bool(_PLURAL_RE.search(base)) or choice


def register(*texts: str) -> str:
    """"revealing" / "modest" / "" from the first text that says either."""
    for t in texts:
        for name, pat, _ in REGISTERS:
            if re.search(pat, (t or "").lower()):
                return name
    return ""


def steer(outfit: str, reg: str, rng: random.Random, ban: re.Pattern | None = None) -> str:
    """One register cue appended to the outfit, chosen from the ones it can
    carry and her "Never wears" line allows; the outfit unchanged when none fits."""
    if not reg or not outfit:
        return outfit
    pool = next(s for n, _, s in REGISTERS if n == reg)
    fit = [cue for cue, needs, never in pool
           if (not needs or re.search(needs, outfit, re.I)) and not (never and re.search(never, outfit, re.I))
           and not avoids(cue, ban)]
    return f"{outfit}, {rng.choice(fit)}" if fit else outfit


_VOWEL_COLOUR_RE = re.compile(
    r"\ba ((?:olive|orange|emerald|ivory|off-white|oatmeal|ecru|indigo|aqua|amethyst|amber)\b)")


def fill(template: str, **kw: str) -> str:
    """`template.format(**kw)` with "a olive" made "an olive"."""
    return _VOWEL_COLOUR_RE.sub(r"an \1", template.format(**kw))


# A SECOND COLOUR. Jeremy, 2026-10-23, on Maya's pack: "The color selections
# are too repetitive - Maya's outfits only have like 3-4 colors. There needs to
# be more combination of colors and accents on clothing unless stated to be
# very plain or simple." Every template carried one {c}, so a four-colour
# palette gave 28 looks in four colours with the second garment left bare
# ("a rust polo tucked into tailored trousers"). Now the second garment gets a
# colour of its own, and a one-piece look gets an accent on about half the
# days. The second colour is another of hers, or a neutral that goes with
# anything; the first stays from her palette, so every look still reads as
# hers. A style, palette or category line that says plain, simple, minimal or
# monochrome turns this off.
PAIR_NEUTRALS = ("white", "black", "cream", "grey", "navy", "camel")
PLAIN_RE = re.compile(r"\b(?:plain|simple|minimal(?:ist|ism)?|monochrome|monochromatic|understated|"
                      r"one[- ]colou?r|single[- ]colou?r|solid colou?rs?|tonal|tone[- ]on[- ]tone)\b", re.I)
_GARMENT = (r"(?:trousers|pants|skirt|shorts|leggings|joggers|sweatpants|blazer|jacket|cardigan|coat|"
            r"cami|camisole|tank top|tank|tee|t-shirt|turtleneck|polo|blouse|shirt|sweater|hoodie|"
            r"sweatshirt|vest|bodysuit|bralette|sports bra|bra|jumpsuit|romper|dress|corset|bustier|"
            r"top|unitard|overalls|tights|culottes|chinos|skort|crewneck|pullover|button-up|button-down|"
            r"henley|flannel)")
# a second garment after a connector: up to three plain words, then the noun
_STOP = r"(?!(?:and|or|it|her|his|with|over|under|into|a|an|the|nothing)\s)"   # \s, not \b: "A-line"
_SECOND_RE = re.compile(r"\b(and|over|under|with|into|beneath|plus)\s+(a |an |the )?"
                        r"((?:" + _STOP + r"[\w-]+\s+){0,3}?)" + _GARMENT + r"\b", re.I)
# a phrase that already has its colour, is a fabric that is one, or belongs to
# the first garment (matching, built-in, the shorts of a romper)
_OWN_COLOUR_RE = re.compile(_COLOUR_RE.pattern + r"|\b(?:denim|jeans|chambray|leather|suede|matching|"
                            r"built-in|sheer|mesh|striped|plaid|printed|graphic|metallic|sequin\w*|lace|"
                            r"nude|same|plain)\b", re.I)
_ONE_PIECE_RE = re.compile(r"\b(?:romper|unitard|one-piece|onesie|jumpsuit)\b", re.I)
_AN_RE = re.compile(r"^(?:olive|orange|emerald|ivory|off-white|oatmeal|ecru|indigo|aqua|amethyst|amber)\b")
# accents for a look with nowhere to put a second garment colour; (cue, never)
ACCENTS: tuple[tuple[str, str], ...] = (
    ("a thin {c2} belt", r"\bbelt\b|sash|bikini|bra\b|thong"),
    ("a {c2} sash tied at the waist", r"\bbelt\b|sash|bikini|bra\b|thong|jumpsuit|romper|trousers|pants|shorts"),
    ("{c2} piping along the seams", r"sheer|mesh|lace|sequin|bikini|thong|slip dress"),
    ("{c2} trim at the neckline", r"strapless|tube top|bikini|thong|neckline|bustier|corset"),
    ("a contrasting {c2} collar", r"strapless|halter|off-the-shoulder|one-shoulder|tube top|bikini|bra\b|thong|"
                                 r"neckline|cowl|slip|cami|bustier|corset|turtleneck|bodysuit|sports"),
    ("{c2} buttons down the front", r"dress|bodysuit|bikini|bra\b|thong|zip|sequin|bustier|corset|sports"),
    ("{c2} stitching", r"sheer|mesh|lace|sequin|latex|vinyl|bikini|thong|satin|silk"),
)


def is_plain(*texts: str) -> bool:
    return any(PLAIN_RE.search(t or "") for t in texts)


def second_colour(line: str, c2: str) -> str | None:
    """`line` with `c2` on its second garment; None when there is no bare one."""
    for m in _SECOND_RE.finditer(line):
        phrase = line[m.start(3):m.end()]
        if _OWN_COLOUR_RE.search(phrase):
            continue
        if phrase.rstrip().endswith("shorts") and _ONE_PIECE_RE.search(line[:m.start()]):
            continue                      # a romper's own shorts are the romper
        art = m.group(2)
        if art and art.strip() in ("a", "an"):
            art = "an " if _AN_RE.match(c2) else "a "
        return line[:m.start(2) if m.group(2) else m.start(3)] + (art or "") + c2 + " " + line[m.start(3):]
    return None


def pair_colours(line: str, colours: list[str], rng: random.Random,
                 ban: re.Pattern | None = None, plain: bool = False) -> str:
    """A second colour on the second garment, or an accent on about every
    other look that has none; the line as it was when she dresses plain."""
    if plain or not line:
        return line
    first = next((c for c in colours if re.search(rf"\b{re.escape(c)}\b", line, re.I)), None)
    pool = _allowed([c for c in colours if c != first] * 2
                    + [n for n in PAIR_NEUTRALS if n not in colours and n != first], ban)
    pool = [c for c in pool if not re.search(rf"\b{re.escape(c)}\b", line, re.I)]
    if not pool:
        return line
    c2 = rng.choice(pool)
    two = second_colour(line, c2)
    if two:
        return two
    if rng.random() < 0.5:
        fit = [cue for cue, never in ACCENTS if not re.search(never, line, re.I) and not avoids(cue, ban)]
        if fit:
            # "a dress with a slit, with piping" reads twice; join on "and"
            sep = " and " if re.search(r"\bwith\b", line) else ", with "
            return line + sep + rng.choice(fit).format(c2=c2)
    return line


def _placed(text: str) -> str:
    """The kind the text itself names, "" when it names none."""
    k = job_kind(text)
    return k if k != "uniform" or UNIFORM_RE.search((text or "").lower()) else ""

# Everything else is a uniform - bar, cafe, counter, salon, grocery, or a job
# line nobody can place. It stays as written and changes in the small things;
# a variant whose key word is already in her line is skipped (keiko's record
# already has the apron).
UNIFORM_VARIANTS: tuple[tuple[str, str], ...] = (
    ("sleeve", "{base}, sleeves pushed up to the elbow"),
    ("apron", "{base}, a black apron tied at the waist"),
    ("cardigan", "{base}, a cropped black cardigan worn over it"),
    ("jacket", "{base}, a fitted black jacket worn open over it"),
    ("badge", "{base}, a thin black belt and a name badge"),
    ("necklace", "{base}, the top button undone and a thin pendant necklace"),
)

# Jobs that are a uniform whatever else their words say ("Lumen Salon assistant"
# is not an office job). Checked before WORK_KINDS.
UNIFORM_RE = re.compile(r"uniform|apron|salon|\bspa\b|waitress|server|bartender|barista|cafe|coffee|"
                        r"grocery|\btill\b|counter|burger|fast food|bakery|market stall|diner|tavern")

_LABEL_RE = re.compile(r"^[^:]{1,45}:\s+(?=\S)")


def job_base(outfit: str) -> str:
    """Her job line as prompt text: "Obsidian waitress: a short black
    shirt-dress" -> "a short black shirt-dress". A colon deeper in the line is
    left alone."""
    return _LABEL_RE.sub("", (outfit or "").strip()).strip()


def job_kind(text: str) -> str:
    """Which WORK_KINDS entry a job's words point at; "uniform" when none."""
    t = (text or "").lower()
    if UNIFORM_RE.search(t):
        return "uniform"
    for kind, pat, _ in WORK_KINDS:
        if re.search(pat, t):
            return kind
    return "uniform"


_BOTTOMS_RE = re.compile(r"trousers|pants|joggers|leggings|skirt|shorts", re.I)


def with_bottoms(outfit: str) -> str:
    """Scrubs with the trousers named. Measured 2026-10-20: across eight packs a
    look naming nothing below the waist came back chest-up 9 of 18 times, every
    scrubs look among them; on kasia's matched seeds, adding "and matching scrub
    trousers" pulled 3 of 5 back to mid-thigh, and Jeremy judged it the best arm.
    Rewording the framing line moved none."""
    if re.search(r"\bscrubs\b", outfit, re.I) and not _BOTTOMS_RE.search(outfit):
        return f"{outfit} and matching scrub trousers"
    return outfit


_LONG_RE = re.compile(r"midi|maxi|knee|floor|ankle|gown|long dress", re.I)


def with_legs(outfit: str) -> str:
    """A short dress with the hem and her legs named. Measured 2026-10-21: of
    the 19 kasia/hannah looks still chest-up after three re-draws, almost every
    one was a dress naming nothing below the waist. Jeremy: "name the hem and
    her legs" - as "bare upper thighs": "bare legs" asks for a full-length
    shot. A long dress is left alone - its hem sits below the crop."""
    if (re.search(r"dress\b", outfit, re.I) and not _BOTTOMS_RE.search(outfit)
            and not _LONG_RE.search(outfit)):
        return f"{outfit}, her bare upper thighs showing below the hem"
    return outfit


def _job_looks(job: dict, n: int, colours: list[str], rng: random.Random, game_job: str,
               style: str = "", ban: re.Pattern | None = None) -> list[str]:
    base = job_base(job["outfit"])
    brief = is_brief(job["outfit"])
    # her record's words place the job; the game's one-line job is consulted
    # only when they do not (a legacy line like "a fitted knit top and
    # trousers" names clothes, not a job)
    words = " ".join((job.get("job", ""), job["outfit"]))
    # a brief's own words outrank the job title ("Teaching assistant: Preppy
    # outfits with a sexy flair" is preppy, not academic)
    kind = (_placed(job["outfit"]) if brief else "") or _placed(words)
    if not kind and game_job:
        kind = _placed(game_job)
    if brief:
        # the brief is never a look: its kind's templates, or - placed nowhere,
        # or a server whose "uniform" is a brief - every pool, the looks
        # wearing what it names first ("Flirty shorts and tight shirts" draws
        # the shorts-and-shirt looks)
        placed = kind not in ("", "uniform")
        pool = [t for t in next(t for k, _, t in WORK_KINDS if k == kind) if t != "{base}"] if placed else "*"
        tpl = guided_templates(pool, base, n, rng, ban, asked=job.get("job", ""))
    elif kind in ("", "uniform"):
        tpl = ["{base}"] + [v for key, v in UNIFORM_VARIANTS if key not in base.lower() and not avoids(v, ban)]
    else:
        # her own line stays hers even when it names what she "never wears"
        tpl = [t for t in next(t for k, _, t in WORK_KINDS if k == kind) if t == "{base}" or not avoids(t, ban)]
    # her job line sets the register; her style line only when the job line
    # is a brief - a written-out uniform is the spec, not a mood
    reg = register(words) or (register(style) if brief else "")
    cols = colours[:]
    rng.shuffle(cols)
    plain = is_plain(words, style)
    out = []
    for i, t in enumerate(tpl[:n]):
        look = with_bottoms(fill(t, base=base, c=cols[i % len(cols)]))
        # her own line stays hers; a template gets its second colour
        out.append(look if t == "{base}" else steer(pair_colours(look, cols, rng, ban, plain), reg, rng, ban))
    while len(out) < n:                       # more looks asked than variants
        out.append(out[len(out) % len(tpl)])
    return out


def work_outfits(character: str, n: int = PACK_28["work"]) -> tuple[str, ...]:
    """Her `n` work outfits from her FIRST job line; `()` when it is blank.

    Jeremy, 2026-10-14: "Work outfits must only come from job 1" - the second
    job's line was seeping into the pack. Job 2 gets its own section later.
    Deterministic per character, like the rest of the draft."""
    from .appearance import persona_job  # noqa: PLC0415
    from .wardrobe import editable  # noqa: PLC0415

    rec = editable(character)
    job = (rec["jobs"] or [{}])[0]
    if not job.get("outfit"):
        return ()
    ban = banned(rec.get("avoid", ""))
    colours = _allowed(palette_colours(rec.get("palette", "")), ban)
    rng = random.Random(f"{character}:work")
    return tuple(_job_looks(job, n, colours, rng, persona_job(character), rec.get("style", ""), ban)[:n])


def _allowed(colours, ban: re.Pattern | None) -> list[str]:
    """Her palette less what she never wears; the whole palette when that
    would leave nothing."""
    kept = [c for c in colours if not avoids(c, ban)]
    return kept or list(colours)


_ALWAYS_PLURAL = {"shorts", "jeans", "trousers", "pants", "leggings", "tights", "scrubs", "overalls", "stockings"}


def _singular(w: str) -> str:
    w = w.lower()
    return w if w in _ALWAYS_PLURAL else re.sub(r"(ss)es$|s$", lambda m: m.group(1) or "", w)


# STYLE WORDS in a direction line. Jeremy, 2026-10-20, on kasia's draft: "It
# also really didn't pick up her ... professional looks, casual wear direction,
# did it?" - "Chic professional looks" names no garment, so the casual pick was
# random streetwear. A style word now steers the pick: (words he writes, looks
# that fit, looks that never fit). Fitting looks come first; looks that never
# fit leave the pool while enough are left to fill the category.
STYLES: tuple[tuple[str, str, str], ...] = (
    (r"chic|polished|elegant|classy|sophisticated|professional|office|tailored|smart|refined|put[- ]together|"
     r"luxury|luxe|designer|high[- ]end|upscale|glam(?:orous)?",
     r"tailored|blazer|sheath|trousers|silk|satin|blouse|turtleneck|pencil|wrap|bodysuit|column|cinched|tweed|"
     r"mock-neck|polo|vest|structured|fine-knit",
     r"jeans|denim|hoodie|sweatshirt|overalls|joggers|cargo|graphic|flannel|distressed|cut-off|baby tee|"
     r"crochet|track|bike shorts|henley|tennis|drawstring|striped|crewneck|onesie|"
     r"sheer|mesh|latex|vinyl|chainmail|fishnet|thong|bralette|lace-up|fringe"),
    (r"sporty|athletic|active", r"sports bra|leggings|track|athletic|tennis|bike shorts|running|joggers|zip", r""),
    (r"edgy|grunge|rock|punk", r"leather|vinyl|latex|chain|mesh|corset|fishnet|distressed|black",
     r"floral|ruffle|puff|tiered|crochet"),
    (r"romantic|feminine|girly|sweet|soft", r"floral|ruffle|lace|puff|sweetheart|tiered|smocked|milkmaid|flutter|wrap",
     r"leather|vinyl|latex|chain|cargo"),
    (r"streetwear|laid[- ]back|relaxed|comfy", r"hoodie|sweatshirt|jeans|denim|joggers|cargo|graphic|tee|overalls", r""),
)

# Garments that answer for each other: "Jumpsuits" for workout found nothing in
# a pool that says unitard.
SYNONYMS: dict[str, str] = {
    "jumpsuit": r"jumpsuit|unitard|catsuit|onesie|one-piece|romper",
    "romper": r"romper|playsuit|shorts-unitard|one-piece",
    "unitard": r"unitard|catsuit|jumpsuit|one-piece",
    "pants": r"pants|trousers|slacks",
    "trouser": r"trousers|pants|slacks",
}

# Length and cut words: (words he writes, looks that fit, looks that never fit).
CUTS: tuple[tuple[str, str, str], ...] = (
    (r"short (?:skirts?|dress(?:es)?|hems?)|minis?\b|micro", r"\bmini\b|micro|short",
     r"midi|maxi|knee-length|column|floor|bias-cut|long (?:skirt|dress)|flowing|ankle"),
    (r"midriff|crop(?:ped)? tops?", r"crop|midriff|bralette|bustier|bandeau|tube top|sports bra", r""),
    (r"long (?:skirts?|dress(?:es)?)|maxi|midi|floor[- ]length", r"midi|maxi|long|floor", r"\bmini\b|micro"),
)


# Looks drafted only when her line asks for them: (the look, the words that ask).
# Jeremy, 2026-10-20: "The outfit generator is way too overindexed on tshirts
# worn as a dress that should be a very rare look" - it was in 10 of 13 plans.
RARE: tuple[tuple[str, str], ...] = (
    (r"tee worn as a dress", r"t-?shirt dress|tee dress|worn as a dress|oversized (?:tee|t-?shirt)"),
    # Jeremy, 2026-10-24, on vivienne's "chic luxury" draft: "you have her
    # wearing a see through maxi dress with a bralette - what in the fuck?"
    # Sheer and fetish-fabric club pieces only when her words go there.
    (r"sheer|mesh|see-through|thong",
     r"sheer|mesh|see[- ]through|reveal|slutty|sexy|racy|daring|provocative|skimpy|risqu|scandal|lingerie|"
     r"dancer|stripper|exotic|club"),
    (r"latex|vinyl|chainmail|fishnet",
     r"latex|vinyl|chainmail|fishnet|edgy|fetish|club|goth|punk|rock|dancer|stripper|exotic"),
)


def _direction(guide: str) -> list[tuple[str, str]]:
    """(fits, never) for every style and cut word the line carries."""
    g = (guide or "").lower()
    return [(fit, never) for words, fit, never in STYLES + CUTS if re.search(rf"\b(?:{words})", g)]


def guided_templates(pool: str | list[str], guide: str, n: int, rng: random.Random,
                     ban: re.Pattern | None = None, asked: str = "") -> list[str]:
    """`n` templates from the pool (a category name, "*" for every category, or
    a list), the ones naming a garment her guide line names first - most of
    them first ("sleeveless blouses, bodysuits" puts the bodysuit looks in) -
    the rest sampled. A template her "Never wears" line rules out is not in
    the pool at all. `asked` is more of her words (the job title) consulted
    only for the RARE looks. At most one one-piece a category unless her line
    names them - Jeremy, 2026-10-24: "you are drafting too many rompers"."""
    if pool == "*":                           # the daytime pools; a job brief is not clubwear
        pool = [t for c in ("casual", "casual_date") for t in TEMPLATES[c]]
    elif isinstance(pool, str):
        pool = list(TEMPLATES[pool])
    pool = [t for t in pool if not avoids(t, ban)]
    words = f"{guide or ''} {asked or ''}"
    pool = [t for t in pool if not any(re.search(look, t) and not re.search(asks, words, re.I)
                                       for look, asks in RARE)]
    nouns = {_singular(m.group(0)) for m in GARMENT_RE.finditer(guide or "")}
    nouns -= {"set", "top"}                   # too common to mean anything
    rules = _direction(guide)
    for _, never in rules:
        if never:
            kept = [t for t in pool if not re.search(never, t, re.I)]
            pool = kept if len(kept) >= n else pool

    def noun_hit(w: str, t: str) -> bool:
        return bool(re.search(SYNONYMS.get(w) or rf"\b{re.escape(w)}(?:e?s)?\b", t, re.I))

    def hits(t: str) -> int:
        return sum(noun_hit(w, t) for w in nouns)

    named = [t for t in pool if hits(t)]
    rng.shuffle(named)
    named.sort(key=hits, reverse=True)       # stable: shuffled within a score
    picked = named[:n]
    # a style or cut word guarantees a SHARE, sampled: every "edgy" character
    # given the same two edgy looks is the sameness of 2026-10-12 again
    fits = [t for t in pool if t not in picked and any(re.search(f, t, re.I) for f, _ in rules)]
    if fits:
        picked += rng.sample(fits, min(len(fits) // 3, n - len(picked)))
    rest = [t for t in pool if t not in picked]
    picked += rng.sample(rest, min(len(rest), n - len(picked)))
    if not re.search(r"romper|jumpsuit|unitard|onesie|one-piece|playsuit|catsuit", words, re.I):
        pieces = [t for t in picked if _ONE_PIECE_RE.search(t)]
        spare = [t for t in pool if t not in picked and not _ONE_PIECE_RE.search(t)]
        rng.shuffle(spare)
        spare.sort(key=hits)                  # a swapped-in look still wears what she named
        for extra in pieces[1:]:
            if not spare:
                break
            picked[picked.index(extra)] = spare.pop()
    rng.shuffle(picked)
    return picked


def draft_looks(character: str, seed: int = 0) -> dict[str, list[dict]]:
    """`{category: [{outfit, hair}, ...]}` for the standard 28, from her record.

    Deterministic per (character, seed): two drafts of the same character
    agree, two characters do not get the same lines, and "Start over" on the
    tab passes the next seed for a different roll.
    """
    from .wardrobe import editable, hair_options  # noqa: PLC0415

    rec = editable(character)
    ban = banned(rec.get("avoid", ""))
    colours = _allowed(palette_colours(rec.get("palette", "")), ban)
    hair = list(hair_options(character))
    rng = random.Random(f"{character}:{seed}" if seed else character)
    out: dict[str, list[dict]] = {}
    for ci, (cat, n) in enumerate(PACK_28.items()):
        looks = []
        off = rng.randrange(len(hair))          # her own hair rotation, not everyone's
        if cat == "work":
            # five different days at her job; blank lines when she has no job
            # outfit written down, for him to fill
            work = work_outfits(character, n)
            for i in range(n):
                looks.append({"outfit": work[i] if work else "",
                              "hair": hair[(i + ci + off) % len(hair)]})
        else:
            # a sample, not the whole pool: what she wears on day three is
            # not what the next character wears on day three. Her line for the
            # category guides it - its garments come first, its colours replace
            # the palette, its register (revealing, modest) shapes every look -
            # and her style line stands in where the category line is blank.
            guide = (rec.get("outfits") or {}).get(CATEGORY_TYPE[cat], "") or ""
            tpl = guided_templates(cat, guide or rec.get("style", ""), n, rng, ban)
            # "denim" alone in a guide line is the fabric, not a colour
            named = ([c for c in palette_colours(guide) if c != "denim"]
                     if (_COLOUR_RE.search(guide) or _FAMILY_RE.search(guide)) else [])
            named = _allowed(named, ban) if named else []
            cols = named if len(named) > 1 else named + [c for c in colours if c not in named]
            rng.shuffle(cols)
            reg = register(guide, rec.get("style", ""))
            plain = is_plain(guide, rec.get("style", ""), rec.get("palette", ""))
            for i in range(n):
                look = pair_colours(fill(tpl[i], c=cols[i % len(cols)]), cols, rng, ban, plain)
                look = accessorise(steer(look, reg, rng, ban), cat, rng, cols, ban, plain)
                looks.append({"outfit": look, "hair": hair[(i + ci + off) % len(hair)]})
        out[cat] = looks
    return out


# --- files -----------------------------------------------------------------------

def plan_dir(outputs: Path, character: str) -> Path:
    return Path(outputs) / "game-assets" / character


def approved_path(outputs: Path, character: str) -> Path:
    return plan_dir(outputs, character) / "plan_28.json"


def draft_path(outputs: Path, character: str) -> Path:
    return plan_dir(outputs, character) / "plan_28.draft.json"


def _read(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    except ValueError:
        return None


def _write(p: Path, doc: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)


def _first_render(folder: Path) -> Path | None:
    for name in ("scene_00.png", "scene_01.png"):
        if (folder / name).is_file():
            return folder / name
    hits = sorted(folder.glob("*.png")) if folder.is_dir() else []
    return hits[0] if hits else None


def source_asset(cfg: dict, character: str, epoch: int | None, lora: dict | None = None) -> Path | None:
    """A 2:3 render of her at her locked epoch for the pack to condition on:
    `scene_00.png` of her sweep in the library, else the old outputs/dense_* spot.

    Which `ep*` folder is hers is `library.lock_render_dir`, the same rule the
    prune uses to keep that folder when it clears the rest of her sweep."""
    from ..library import library_dir, lock_render_dir  # noqa: PLC0415
    from ..config import outputs_dir  # noqa: PLC0415

    if epoch is None:
        return None
    lock = dict(lora or {}, epoch=epoch)
    roots = sorted((library_dir(cfg) / character).glob("*_sweep_*"), reverse=True)
    roots += sorted(outputs_dir(cfg).glob(f"dense_{character}*"), reverse=True)
    # the real epoch number anywhere first, then a continued run's own numbering
    for r in roots:
        hit = _first_render(r / f"ep{int(epoch)}")
        if hit:
            return hit
    for r in roots:
        d = lock_render_dir(r, character, lock)
        hit = _first_render(d) if d else None
        if hit:
            return hit
    return None


def reference(character: str) -> Path | None:
    for pat in (f"{character}_face.*", f"{character}_portrait*.*"):
        hits = sorted(REFS.glob(pat)) if REFS.is_dir() else []
        if hits:
            return hits[0]
    return None


def shipped(character: str) -> dict[str, int]:
    return existing_looks(GAME_ROOT / "src" / "assets" / "characters" / character / "outfits")


def draft(cfg: dict, character: str) -> dict:
    """Write a fresh draft from her record and return the state. Each draft
    after the first is a different roll (the seed counts up from the draft it
    replaces). Never touches an approved plan: a new draft sits beside it until
    approved, when it takes over."""
    from ..config import outputs_dir  # noqa: PLC0415
    from .lora import resolve_lora  # noqa: PLC0415

    c = character.lower()
    out = outputs_dir(cfg)
    prev = _read(draft_path(out, c)) or _read(approved_path(out, c)) or {}
    seed = int(prev.get("seed", -1)) + 1
    lora = resolve_lora(cfg, c)
    src = source_asset(cfg, c, (lora or {}).get("epoch"), lora)
    ref = reference(c)
    plan = make_plan(c, lora=(lora or {}).get("path"),
                     source_asset=str(src) if src else None,
                     reference=str(ref) if ref else None,
                     looks=draft_looks(c, seed))
    plan["seed"] = seed
    _write(draft_path(out, c), plan)
    return state(cfg, c)


def save(cfg: dict, character: str, categories: dict) -> dict:
    """Write his edits into whichever file is current - the open draft, or the
    approved plan if he is revising one. `categories` is {cat: [{id, outfit, hair}]}."""
    from ..config import outputs_dir  # noqa: PLC0415

    c = character.lower()
    out = outputs_dir(cfg)
    p = draft_path(out, c) if draft_path(out, c).is_file() else approved_path(out, c)
    doc = _read(p)
    if not doc:
        raise ValueError("nothing to save into - draft her looks first")
    edits = {e.get("id"): e for block in (categories or {}).values() for e in block}
    for block in doc["categories"].values():
        for entry in block["looks"]:
            e = edits.get(entry["id"])
            if e is not None:
                entry["outfit"] = str(e.get("outfit") or "").strip()
                entry["hair"] = str(e.get("hair") or "").strip()
    _write(p, doc)
    return state(cfg, c)


def approve(cfg: dict, character: str) -> dict:
    """Promote the draft to the plan the pack renders. Refuses blanks and a
    plan with no LoRA behind it.

    The source render is recorded when one exists and is not required: the
    pack renders through T2I (`pack.render_pack`) and never reads it. Only the
    Edit graph (`assets render --plan`) conditions on it, and that path raises
    its own error when the plan has none. Nisha, 2026-10-15: the prune had
    removed every judged sweep folder, so 38 of 39 locked characters had no
    `ep<lock>/scene_00.png` left and every pack approval was refused for a
    file the pack does not use."""
    from ..config import outputs_dir  # noqa: PLC0415
    from .lora import resolve_lora  # noqa: PLC0415

    c = character.lower()
    out = outputs_dir(cfg)
    doc = _read(draft_path(out, c))
    if not doc:
        raise ValueError("no draft to approve")
    blank = [s["id"] for s in plan_slots(doc) if not s["outfit"] or not s["hair"]]
    if blank:
        raise ValueError(f"{len(blank)} look{'s' if len(blank) != 1 else ''} still blank: "
                         + ", ".join(blank[:6]) + ("..." if len(blank) > 6 else ""))
    # the LoRA and the source render are looked up again now, not trusted from
    # the draft: she may have been locked to a different epoch since
    lora = resolve_lora(cfg, c)
    if not lora:
        raise ValueError("no locked LoRA for her - the pack renders from her lock")
    src = source_asset(cfg, c, lora.get("epoch"), lora)
    doc["lora"], doc["source_asset"] = lora["path"], (str(src) if src else None)
    if not doc.get("reference") and reference(c):
        doc["reference"] = str(reference(c))
    from datetime import datetime, timezone  # noqa: PLC0415
    doc["approved"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write(approved_path(out, c), doc)
    draft_path(out, c).unlink(missing_ok=True)
    return state(cfg, c)


def state(cfg: dict, character: str) -> dict:
    """What the Characters tab shows: none / draft / approved, and the looks."""
    from ..config import outputs_dir  # noqa: PLC0415
    from .wardrobe import editable  # noqa: PLC0415

    c = character.lower()
    out = outputs_dir(cfg)
    ap, dr = _read(approved_path(out, c)), _read(draft_path(out, c))
    # an open draft is what he is working on, even when a plan is approved
    doc = dr or ap
    st = "draft" if dr else ("approved" if ap else "none")
    rec = editable(c)
    cats = []
    if doc:
        for cat, block in doc["categories"].items():
            t = CATEGORY_TYPE.get(cat, "")
            guide = (" / ".join(j["outfit"] for j in rec["jobs"] if j["outfit"]) if t == "job"
                     else rec["outfits"].get(t, ""))
            cats.append({"key": cat, "label": CATEGORY_LABEL.get(cat, cat), "guide": guide,
                         "looks": [{"id": e["id"], "look": e["look"], "outfit": e["outfit"],
                                    "hair": e["hair"]} for e in block["looks"]]})
    blank = sum(1 for s in plan_slots(doc) if not s["outfit"] or not s["hair"]) if doc else 0
    from . import pack as P  # noqa: PLC0415

    staged = P.read_staged(out, c)
    if staged:
        # the page needs the sheet by name, never a path; and whether it is
        # already in the game or waiting on him
        staged = {"at": staged.get("at"), "n": staged.get("n"), "missing": staged.get("missing") or [],
                  "flagged": staged.get("flagged") or [], "would_overwrite": staged.get("would_overwrite", 0),
                  "set": staged.get("set"), "shipped": staged.get("shipped"),
                  "sheets": [k for k, v in (staged.get("sheets") or {}).items() if Path(v).is_file()],
                  # each new look beside the game's, for the tiles he ticks
                  "looks": [] if staged.get("shipped") else P.pairs(out, c, GAME_ROOT)}
    return {"character": c, "state": st, "approved_at": (ap or {}).get("approved"),
            "seed": (doc or {}).get("seed", 0),
            "categories": cats, "blank": blank, "shipped": shipped(c),
            "staged": staged, "shipped_at": ((ap or {}).get("shipped") or {}).get("at"),
            "source_asset": (doc or {}).get("source_asset"), "lora": (doc or {}).get("lora")}


def sheet_path(cfg: dict, character: str, which: str) -> Path | None:
    from ..config import outputs_dir  # noqa: PLC0415
    from . import pack as P  # noqa: PLC0415

    st = P.read_staged(outputs_dir(cfg), character.lower())
    p = ((st or {}).get("sheets") or {}).get(which)
    return Path(p) if p and Path(p).is_file() else None


def ship(cfg: dict, character: str, keep: list[str] | None = None) -> dict:
    """The formal approval. Jeremy, 2026-10-14: "I would like a formal approval
    step of that final shift ... before just deciding to overwrite whatever is
    in the game currently." The only write into the game repo. `keep` is the
    files he ticked; None is all of them."""
    from ..config import outputs_dir  # noqa: PLC0415
    from . import pack as P  # noqa: PLC0415

    return P.ship(outputs_dir(cfg), character.lower(), GAME_ROOT, keep)


def look_tile(cfg: dict, character: str, name: str, side: str) -> Path | None:
    """A small image of one staged look (`new`) or the game's file (`game`)
    for the tiles on the Characters tab; None when there is no such file."""
    from ..config import outputs_dir  # noqa: PLC0415
    from . import pack as P  # noqa: PLC0415

    c = character.lower()
    if side not in ("new", "game") or Path(name).name != name:
        return None
    out = outputs_dir(cfg)
    p = ((out / "game-assets" / c / "outfits") if side == "new"
         else (GAME_ROOT / "src" / "assets" / "characters" / c / "outfits")) / name
    return P.thumb(p, out, c, side) if p.is_file() else None


def discard_staging(cfg: dict, character: str) -> bool:
    from ..config import outputs_dir  # noqa: PLC0415
    from . import pack as P  # noqa: PLC0415

    return P.discard(outputs_dir(cfg), character.lower())


def ship_portrait(cfg: dict, character: str, src: Path) -> dict:
    """One reference photo becomes the game's profile portrait for her. The
    other write into the game repo, beside `ship`."""
    from ..config import outputs_dir  # noqa: PLC0415
    from . import pack as P  # noqa: PLC0415

    return P.ship_portrait(outputs_dir(cfg), character.lower(), GAME_ROOT, src)


def portrait_tile(cfg: dict, character: str) -> Path | None:
    """A small image of the game's current profile for the card; None when the
    game has none. Cached under outputs, never beside the game's file."""
    from ..config import outputs_dir  # noqa: PLC0415
    from . import pack as P  # noqa: PLC0415

    c = character.lower()
    p = P.portrait_path(GAME_ROOT, c)
    return P.thumb(p, outputs_dir(cfg), c, "portrait") if p.is_file() else None
