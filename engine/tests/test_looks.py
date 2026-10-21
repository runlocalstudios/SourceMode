"""The 28-look plan drafted and approved from the Characters tab (2026-10-12).

Ash had a job, a style and a locked LoRA and the asset pack was still greyed
out, because the plan file it needs had no way to come into being from the
monitor. The draft must give 28 editable lines in the pack's categories, the
work looks must be HER job outfit, and approving must produce exactly the file
`blocked_shoots` looks for - and refuse while a line is blank.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

import pytest

from sourcemode.assets import looks as L
from sourcemode.assets import wardrobe as W
from sourcemode.assets.catalog import PACK_28


@pytest.fixture
def ash(monkeypatch):
    rec = {"style": "edgy", "palette": "black and denim blue as the base, one hot accent - cobalt, burnt orange, red",
           "avoid": "", "outfits": {"everyday": "cropped tops over denim", "workout": "bright sports bra"},
           "jobs": [{"job": "Waitress at Obsidian", "outfit": "a short black shirt-dress uniform", "places": []},
                    {"job": "", "outfit": "", "places": []}],
           "hair": [], "note": "", "draft": False}
    monkeypatch.setattr(W, "editable", lambda c: rec if c == "ash" else {
        **rec, "jobs": [{"job": "", "outfit": "", "places": []}] * 2, "palette": ""})
    monkeypatch.setattr(W, "hair_options", lambda c: ("her hair worn loose", "her hair in a bun"))
    monkeypatch.setattr(L, "shipped", lambda c: {"casual": 7, "work": 5} if c == "ash" else {})
    monkeypatch.setattr(L, "reference", lambda c: None)
    from sourcemode.assets import appearance as A
    monkeypatch.setattr(A, "persona_job", lambda c: "")
    return rec


def test_palette_colours_are_read_from_prose_longest_first():
    assert L.palette_colours("black and denim blue as the base, with one hot accent - cobalt, burnt orange, red") == (
        "black", "denim blue", "cobalt", "burnt orange", "red")
    assert L.palette_colours("") == L.DEFAULT_COLOURS
    assert L.palette_colours("whatever she likes") == L.DEFAULT_COLOURS


def test_a_colour_family_expands_where_it_is_written():
    """Jeremy, 2026-10-17, after Winnie's 28 looks all rendered white from
    "White with primary colors": "i want the parser to understand common
    phrases like primary colors, secondary colors, earthy tones, vivid colors,
    etc. i don't want to have to type things out color by color"."""
    assert L.palette_colours("White with primary colors") == ("white", "red", "blue", "yellow")
    assert L.palette_colours("earthy tones") == ("rust", "olive", "camel", "terracotta", "chocolate brown", "mustard", "cream")
    assert L.palette_colours("pastels and a little black") == ("pale pink", "baby blue", "mint", "lavender", "lemon yellow", "peach", "black")
    # the lines already on disk that used to fall back to the defaults
    assert L.palette_colours("Dark colors with vivid highlight accent colors")[:6] == (
        "black", "charcoal", "navy", "burgundy", "forest green", "plum")
    assert "hot pink" in L.palette_colours("Dark colors with vivid highlight accent colors")
    assert L.palette_colours("subdued tones")[0] == "dusty pink"
    assert L.palette_colours("vivid colors and dark grays and blacks")[-2:] == ("gray", "black")
    # "warm neutrals" is its own family, not warm + neutrals twice
    assert L.palette_colours("warm neutrals") == ("cream", "camel", "taupe", "chocolate brown", "rust", "oatmeal")
    # a family phrase is not double-counted with the colour words inside it
    assert L.palette_colours("black and white") == ("black", "white", "grey", "charcoal")
    # words that were missing: plurals and the ones his lines already use
    assert L.palette_colours("oatmeal, pale blue, camel and black") == ("oatmeal", "pale blue", "camel", "black")
    assert L.palette_colours("cream, bone, black and indigo denim") == ("cream", "bone", "black", "indigo", "denim")
    assert L.palette_families("White with primary colors, some pastels") == ["primary colors", "pastels"]
    assert L.fill("a {c} sundress", c="oatmeal") == "an oatmeal sundress"


def _record(monkeypatch, **over):
    rec = {"style": "playful but revealing, with a very upscale vibe",
           "palette": "pastels and vivid colors, as well as white or gray t-shirts with vivid graphics",
           "avoid": "", "outfits": {"dressy": "skirt and blouse combo, or trendy flowy slacks with a stunning top",
                                    "night_out": "skirt and cutoff halter top with choker, or a glamorous minidress"},
           "jobs": [{"job": "Owner of Gal Gaming", "places": [],
                     "outfit": "unassuming colorful outfits that are a bit revealing and playful"},
                    {"job": "", "outfit": "", "places": []}],
           "hair": [], "note": "", "draft": False, **over}
    monkeypatch.setattr(W, "editable", lambda c: rec)
    monkeypatch.setattr(W, "hair_options", lambda c: ("her hair worn loose", "her hair in a bun"))
    monkeypatch.setattr(L, "shipped", lambda c: {})
    monkeypatch.setattr(L, "reference", lambda c: None)
    from sourcemode.assets import appearance as A
    monkeypatch.setattr(A, "persona_job", lambda c: "")
    return rec


def _all_outfits(d: dict) -> list[str]:
    return [lk["outfit"] for looks in d.values() for lk in looks]


def test_what_she_never_wears_is_never_drafted(monkeypatch):
    """Jeremy, 2026-10-18: "i told the app that hannah never wears denim, yet
    it still put her in jeans a lot and also this: a gray slip dress under a
    cropped denim jacket". Her record is Hannah's; with no avoid line the
    draft reaches for denim, with it the draft never does - in any category,
    the work brief included - over several rolls."""
    _record(monkeypatch)
    assert any(re.search(r"denim|jeans", o) for s in range(3) for o in _all_outfits(L.draft_looks("hannah", s)))
    _record(monkeypatch, avoid="denim")
    for s in range(4):
        for o in _all_outfits(L.draft_looks("hannah", s)):
            assert not re.search(r"denim|jeans|chambray", o, re.I), o
    # the full 28 are still there - the casual pool has 19 denim-free templates for 7 looks
    assert {k: len(v) for k, v in L.draft_looks("hannah").items()} == PACK_28


def test_any_item_he_writes_is_banned_not_only_known_words(monkeypatch):
    """Jeremy, 2026-10-20: "The restriction on never wears cargo pants is not
    working." Kasia's line, verbatim: only "Denim" was a known word, so her
    draft carried cargo pants and the tee worn as a dress."""
    line = "Denim, cargo pants, cargo shorts, oversized tee worn as a dress"
    ban = L.banned(line)
    assert L.avoids("a navy baby tee and low-rise cargo pants, cut close to the body", ban)
    assert L.avoids("an oversized blush pink graphic tee worn as a dress with a thin belt", ban)
    assert L.avoids("khaki cargo shorts and a tank", ban)
    assert not L.avoids("a fitted navy t-shirt and a pleated skirt", ban)
    assert not L.avoids("a fitted pink tee and a mini skirt", ban)     # a tee is not the dress
    _record(monkeypatch, avoid=line)
    for s in range(4):
        for o in _all_outfits(L.draft_looks("hannah", s)):
            assert not L.avoids(o, ban), o


def test_style_synonym_and_length_words_steer_the_draft(monkeypatch):
    """Jeremy, 2026-10-20, on kasia's draft: "It also really didn't pick up
    her ... professional looks, casual wear direction, did it?" Her lines,
    verbatim: casual came back overalls and a sweatshirt, workout had no
    jumpsuit, dressy was midi dresses."""
    _record(monkeypatch, style="Elegant and sexy",
            avoid="Denim, cargo pants, cargo shorts, oversized tee worn as a dress",
            outfits={"everyday": "Chic professional looks", "workout": "Jumpsuits",
                     "dressy": "Midriff tops and short skirts, short dresses", "date": "Revealing outfits"})
    for s in range(4):
        d = L.draft_looks("kasia", s)
        casual = " | ".join(lk["outfit"] for lk in d["casual"])
        assert not re.search(r"hoodie|sweatshirt|overalls|graphic|joggers|flannel|cargo", casual), casual
        assert len(re.findall(r"tailored|silk|blouse|pencil|tweed|polo|vest|cinched", casual)) >= 2, casual
        for lk in d["workout"]:
            assert re.search(r"jumpsuit|unitard|onesie|one-piece|romper", lk["outfit"]), lk
        for lk in d["fancy_dining_gallery"]:
            assert not re.search(r"midi|maxi|knee-length|column", lk["outfit"]), lk
    # the tee worn as a dress is rare: only when a line asks for it
    for c in ("ash", "zoe", "kim", "bea"):
        assert not any("worn as a dress" in o for o in _all_outfits(L.draft_looks(c))), c
    assert any("worn as a dress" in t for s in range(10)
               for t in L.guided_templates("casual", "a tee dress", 7, random.Random(s)))
    # "cargo shorts" bans cargo shorts, not every pair of shorts
    assert not L.avoids("a red one-piece unitard with short shorts", L.banned("cargo shorts"))
    assert L.avoids("denim shorts", L.banned("shorts"))


def test_the_avoid_line_reaches_cues_colours_and_the_job_looks(monkeypatch):
    # sandra's line: the revealing cues it names are never appended
    ban = L.banned("crop tops, micro skirts, plunging necklines, bare midriff - none of it is her")
    assert L.avoids("the neckline cut low", ban) and L.avoids("the top cropped to show her midriff", ban)
    assert L.avoids("a black micro mini skirt", ban) and not L.avoids("a black pencil skirt", ban)
    rng = random.Random(1)
    for _ in range(20):
        out = L.steer("a fitted white shirt and a pencil skirt", "revealing", rng, ban)
        assert "neckline cut low" not in out and "midriff" not in out
    # colours and families come off the palette; the whole palette stays when nothing would be left
    assert L._allowed(["pale pink", "black", "mint"], L.banned("pastels and anything girlish")) == ["black"]
    assert L._allowed(["black"], L.banned("black")) == ["black"]
    # prose the generator cannot act on bans nothing
    assert L.banned("nothing prim or preppy - she is the opposite of wholesome") is None
    assert L.banned("") is None
    # the work brief draws from the daytime pools - minus the banned ones
    _record(monkeypatch, avoid="denim and hoodies")
    for o in L.work_outfits("hannah", 5):
        assert not re.search(r"denim|jeans|hoodie", o, re.I), o
    # a written-out uniform is his line and stays, denim or not
    _record(monkeypatch, avoid="denim", jobs=[{"job": "Bartender", "places": [],
                                              "outfit": "a denim shirt tied at the waist and black trousers"},
                                             {"job": "", "outfit": "", "places": []}])
    assert L.work_outfits("hannah", 5)[0].startswith("a denim shirt tied at the waist")


def test_draft_is_28_looks_in_the_pack_categories_coloured_from_her_palette(ash):
    d = L.draft_looks("ash")
    assert {k: len(v) for k, v in d.items()} == PACK_28
    assert sum(len(v) for v in d.values()) == 28
    colours = set(L.palette_colours(ash["palette"]))
    for cat, looks in d.items():
        if cat == "work":
            continue
        for lk in looks:
            assert any(c in lk["outfit"] for c in colours), lk
            assert lk["hair"] in ("her hair worn loose", "her hair in a bun")
    # a waitress wears her uniform every day, but not the same way: five
    # different lines, all of them still her uniform, the first one plain
    work = [lk["outfit"] for lk in d["work"]]
    assert len(set(work)) == 5
    assert work[0] == "a short black shirt-dress uniform"
    assert all(w.startswith("a short black shirt-dress uniform") for w in work)
    # deterministic per character, different between characters
    assert L.draft_looks("ash") == d
    assert L.draft_looks("zoe")["casual"] != d["casual"]


def _garments(looks: list[dict]) -> list[str]:
    """The template behind each line, colour removed, so two characters' lines
    compare as garments and not as colours."""
    out = []
    for lk in looks:
        g = lk["outfit"]
        for c in L._COLOURS:
            g = re.sub(rf"\b{re.escape(c)}\b", "{c}", g)
        out.append(g)
    return out


def test_characters_do_not_wear_the_same_garments_on_the_same_days(ash):
    # Jeremy, 2026-10-12: "the bodysuit tucked into jeans ... everyone so far
    # that I've reviewed is wearing the same thing with just different colors"
    names = ["ash", "zoe", "kim", "bea", "lou", "mia", "ivy", "una"]
    for cat, n in PACK_28.items():
        if cat == "work":
            continue
        assert len(L.TEMPLATES[cat]) >= 3 * n, cat
        days = [_garments(L.draft_looks(c)[cat]) for c in names]
        for day in range(n):
            worn = [d[day] for d in days]
            # eight characters, one day: never the same garment on most of them
            assert max(worn.count(w) for w in worn) <= 3, (cat, day, worn)
        # and no character repeats a garment inside a category
        for d in days:
            assert len(set(d)) == n


def test_a_new_seed_is_a_different_roll(ash):
    a, b = L.draft_looks("ash"), L.draft_looks("ash", seed=1)
    assert a != b
    assert L.draft_looks("ash", seed=1) == b
    assert len(a["casual"]) == len(b["casual"]) == PACK_28["casual"]


def test_no_job_outfit_leaves_the_work_looks_blank(ash):
    assert all(lk["outfit"] == "" for lk in L.draft_looks("zoe")["work"])
    assert L.work_outfits("zoe") == ()


def _with_job(monkeypatch, job: str, outfit: str, palette: str = "black and red", game_job: str = ""):
    rec = {"style": "", "palette": palette, "avoid": "", "outfits": {},
           "jobs": [{"job": job, "outfit": outfit, "places": []}, {"job": "", "outfit": "", "places": []}],
           "hair": [], "note": "", "draft": False}
    monkeypatch.setattr(W, "editable", lambda c: rec)
    from sourcemode.assets import appearance as A
    monkeypatch.setattr(A, "persona_job", lambda c: game_job)


def test_the_label_before_the_colon_is_not_part_of_the_outfit():
    assert L.job_base("Obsidian waitress: a short black shirt-dress uniform") == "a short black shirt-dress uniform"
    assert L.job_base("The Chill Trap, evenings: black long-sleeve bodycon mini") == "black long-sleeve bodycon mini"
    assert L.job_base("a black blazer and trousers") == "a black blazer and trousers"
    # a colon deep in the line is prose, not a label
    long = "a tailored blazer with a silk shirt and trousers, or over a black mini: never jeans"
    assert L.job_base(long) == long


@pytest.mark.parametrize("words, kind", [
    ("Waitress at Obsidian night club", "uniform"),
    ("Obsidian head bartender: a fitted black waistcoat", "uniform"),
    ("Lumen Salon assistant: a chambray shirt with a canvas apron", "uniform"),
    ("The Chill Trap, evenings: black long-sleeve bodycon mini", "dancer"),
    ("works at Threads clothing boutique", "boutique"),
    ("executive assistant: a tailored blazer", "office"),
    ("drinks sales rep on evening calls: a black blazer", "office"),
    ("contemporary art gallery: a tailored blazer", "gallery"),
    ("university teaching assistant: a cardigan", "academic"),
    ("church volunteer: a modest long-sleeve dress", "modest"),
    ("club/stage wear: sequin and satin bralettes", "stage"),
    ("a nurse at Chill General", "medical"),
    ("teaches yoga at Ironline", "fitness"),
])
def test_the_kind_of_job_is_read_from_its_words(words, kind):
    assert L.job_kind(words) == kind


def test_a_dancer_gets_five_different_outfits_in_her_palette_her_own_line_first(monkeypatch):
    _with_job(monkeypatch, "", "The Chill Trap, evenings: black long-sleeve bodycon mini, covered but close-fitting",
              palette="black, hot pink and silver")
    w = L.work_outfits("kimmy")
    assert len(w) == 5 and len(set(w)) == 5
    assert w[0] == "black long-sleeve bodycon mini, covered but close-fitting"
    assert not any("bodycon mini" in x for x in w[1:])
    assert all(any(c in x for c in ("black", "hot pink", "silver")) for x in w[1:])
    assert L.work_outfits("kimmy") == w


def test_the_game_job_line_decides_the_kind_when_her_record_has_only_the_outfit(monkeypatch):
    _with_job(monkeypatch, "", "a fitted knit top and tailored trousers", game_job="She runs the floor at Threads")
    w = L.work_outfits("bianca")
    assert w[0] == "a fitted knit top and tailored trousers"
    assert "turtleneck" in " ".join(w) and "blazer" in " ".join(w)      # boutique templates, not uniform suffixes
    assert not any(x.startswith("a fitted knit top and tailored trousers,") for x in w)


def test_her_record_places_the_job_before_the_game_line_does(monkeypatch):
    # cassie: the record's work line is the drinks rep; the game adds that she
    # teaches yoga. Work looks are the rep's, not gym kit.
    _with_job(monkeypatch, "", "drinks sales rep on evening calls: a black blazer and tailored trousers over a satin cami",
              game_job="She sells drink to every bar in the city and teaches yoga at the Studio")
    w = L.work_outfits("cassie")
    assert "sports bra" not in " ".join(w) and "blazer" in w[1] + w[4]


def test_a_uniform_skips_the_variant_she_already_wears(monkeypatch):
    _with_job(monkeypatch, "", "Lumen Salon assistant: a chambray shirt with a canvas apron over jeans")
    w = L.work_outfits("keiko")
    assert len(set(w)) == 5
    assert sum("apron" in x for x in w) == 5 and not any("black apron" in x for x in w)


def test_a_brief_is_never_a_look_and_its_words_shape_every_look(monkeypatch):
    # priya, 2026-10-13: work look 1 drafted as "Chic professional outfits that
    # are a little too revealing" verbatim. "I want the descriptions on the top
    # to guide the design of the outfits"
    brief = "Chic professional outfits that are a little too revealing"
    assert L.is_brief(brief) and not L.is_brief("a tailored blazer with a pencil skirt")
    _with_job(monkeypatch, "Data analyst", brief, palette="black, charcoal, taupe and camel")
    w = L.work_outfits("priya")
    assert len(w) == 5 and len(set(w)) == 5
    assert not any(brief.lower() in x.lower() for x in w)
    assert all(L.GARMENT_RE.search(x) for x in w)                      # office templates
    assert sum(any(x.endswith(c) for c in _cues("revealing")) for x in w) >= 4, w   # the brief's register
    for x in w:                                                        # a hem cue needs a hem
        if re.search(r"hem|slit", x):
            assert re.search(r"skirt|dress", x), x
    assert L.work_outfits("priya") == w


def _cues(reg: str) -> set[str]:
    return {cue for name, _, pool in L.REGISTERS if name == reg for cue, _, _ in pool}


def test_a_cue_only_lands_on_a_garment_that_can_carry_it():
    rng = L.random.Random(0)
    for _ in range(40):
        assert "unbuttoned" not in L.steer("a black crop top and a flowing white maxi skirt", "revealing", rng)
        assert "cropped" not in L.steer("a red sheath dress with a thin belt", "revealing", rng)
        assert "hem" not in L.steer("a navy silk shirt with tailored trousers", "modest", rng)
    assert L.steer("a fitted black knit top", "", rng) == "a fitted black knit top"
    assert L.fill("a {c} blouse", c="olive") == "an olive blouse"
    assert L.fill("a {c} one-piece", c="black") == "a black one-piece"


@pytest.mark.parametrize("line, brief", [
    ("Flirty shorts and tight shirts", True),                                    # plural garments
    ("a modest long-sleeve dress or a jumper with straight-leg jeans", True),    # a choice
    ("Chic business casual", True),                                              # no garment
    ("a short black shirt-dress uniform with white piping, black tights", False),
    ("The Chill Trap, evenings: black long-sleeve bodycon mini, covered but close-fitting", False),
    ("a chambray shirt with a canvas apron over jeans", False),                  # jeans are always plural
    ("a cream wrap blouse with rust or brown high-waisted trousers", False),     # a choice of colour is one outfit
])
def test_a_brief_is_a_style_not_one_outfit(line, brief):
    assert L.is_brief(line) is brief


def test_a_brief_naming_garments_but_no_job_draws_looks_wearing_those_garments(monkeypatch):
    # 2026-10-14 screenshot: "Flirty shorts and tight shirts" drafted as a
    # uniform - "Flirty shorts and tight shirts, a black apron tied at the
    # waist, the neckline cut low". "applying the work style in a dumb way"
    # gigi's job title says server, which is a uniform job - the brief still
    # draws from the pools, never the apron variants
    _with_job(monkeypatch, "Server at the Sandbar", "Flirty shorts and tight shirts", palette="red and white")
    w = L.work_outfits("gigi")
    assert len(w) == 5 and len(set(w)) == 5
    assert not any(x.lower().startswith("flirty") for x in w)
    assert not any("apron" in x or "sleeves pushed up" in x for x in w)
    assert all(re.search(r"shorts|shirt", x) for x in w), w
    assert sum(any(x.endswith(c) for c in _cues("revealing")) for x in w) >= 4, w


def test_a_preppy_brief_with_a_sexy_flair_gets_preppy_looks_cut_revealing(monkeypatch):
    # priyanka: the job title says teaching assistant; the brief says preppy.
    # The brief wins - its words are the design direction
    _with_job(monkeypatch, "Teaching assistant", "Preppy outfits with a sexy flair", palette="navy and cream",
              game_job="She is a teaching assistant at Chill Coast University")
    w = L.work_outfits("priyanka")
    joined = " ".join(w)
    assert len(set(w)) == 5
    assert "pleated" in joined and ("collared" in joined or "argyle" in joined)   # preppy, not academic
    assert "pinafore" not in joined and "tie-neck" not in joined
    assert sum(any(x.endswith(c) for c in _cues("revealing")) for x in w) >= 4


def test_business_casual_at_the_library_is_an_office_brief_not_a_modest_uniform(monkeypatch):
    _with_job(monkeypatch, "", "Chic business casual",
              game_job="She works the desk at Avery Central Library")
    w = L.work_outfits("tess")
    assert len(set(w)) == 5 and "blazer" in " ".join(w)
    assert not any(x.startswith("Chic business casual") for x in w)
    assert not any(x.endswith(c) for x in w for c in _cues("modest"))   # nothing in the brief says modest


def test_her_own_garment_line_is_kept_verbatim_and_only_the_templates_are_steered(monkeypatch):
    line = "church volunteer: a modest long-sleeve navy dress with a cardigan over it"
    _with_job(monkeypatch, "", line, palette="navy, cream")
    w = L.work_outfits("sandra")
    assert w[0] == L.job_base(line)
    assert sum(any(x.endswith(c) for c in _cues("modest")) for x in w[1:]) >= 3


def test_a_written_out_uniform_ignores_the_mood_of_the_style_line(monkeypatch):
    # ash: "a short black shirt-dress uniform" is the spec; a "teasing" style
    # line must not make it sheer
    rec = {"style": "edgy and teasing", "palette": "black", "avoid": "", "outfits": {},
           "jobs": [{"job": "Waitress at Obsidian", "outfit": "a short black shirt-dress uniform", "places": []},
                    {"job": "", "outfit": "", "places": []}],
           "hair": [], "note": "", "draft": False}
    monkeypatch.setattr(W, "editable", lambda c: rec)
    from sourcemode.assets import appearance as A
    monkeypatch.setattr(A, "persona_job", lambda c: "")
    w = L.work_outfits("ash")
    assert not any(any(x.endswith(c) for c in _cues("revealing")) for x in w)


def test_the_category_lines_guide_the_other_categories(ash):
    # colours named in the line replace the palette; a garment it names comes
    # first; a register word in the style line reaches every category
    ash["outfits"] = {"everyday": "bodysuits and tennis skirts", "workout": "plain white or charcoal set"}
    ash["style"] = "office-polished with a slutty edge"
    d = L.draft_looks("ash")
    workout = [lk["outfit"] for lk in d["workout"]]
    assert all(re.search(r"\b(white|charcoal)\b", x) for x in workout), workout
    casual = [lk["outfit"] for lk in d["casual"]]
    assert sum("bodysuit" in x or "skirt" in x for x in casual) >= 5, casual
    cues = _cues("revealing")
    assert sum(any(x.endswith(c) for c in cues) for x in casual + workout) >= len(casual + workout) - 2
    # the same record without the brief words drafts plain lines
    ash["style"] = "edgy"
    plain = [lk["outfit"] for lk in L.draft_looks("ash")["casual"]]
    assert not any(any(x.endswith(c) for c in cues) for x in plain)


def test_only_the_first_job_dresses_the_work_looks(monkeypatch):
    # Jeremy, 2026-10-14: "Work outfits must only come from job 1" - the yoga
    # line was seeping into a drinks rep's pack. Job 2 gets its own section later.
    rec = {"style": "", "palette": "black", "avoid": "", "outfits": {},
           "jobs": [{"job": "drinks sales rep", "outfit": "a black blazer over a satin cami", "places": []},
                    {"job": "yoga instructor", "outfit": "a supportive crop and leggings", "places": []}],
           "hair": [], "note": "", "draft": False}
    monkeypatch.setattr(W, "editable", lambda c: rec)
    from sourcemode.assets import appearance as A
    monkeypatch.setattr(A, "persona_job", lambda c: "")
    w = L.work_outfits("cassie")
    assert len(w) == 5 and w[0] == "a black blazer over a satin cami"
    assert "crop and leggings" not in " ".join(w) and "sports bra" not in " ".join(w)
    # a blank first job leaves the work looks blank even with a second job filled in
    rec["jobs"][0]["outfit"] = ""
    assert L.work_outfits("cassie") == ()


def _cfg(tmp_path: Path) -> dict:
    return {"paths": {"outputs": str(tmp_path / "out"), "library": str(tmp_path / "lib")}}


def test_draft_numbers_from_one_to_replace_her_shipped_looks_and_approve_writes_the_pack_plan(tmp_path, ash, monkeypatch):
    cfg = _cfg(tmp_path)
    from sourcemode.assets import lora as LORA
    monkeypatch.setattr(LORA, "resolve_lora", lambda cfg, c: {
        "path": "sourcemode\\ash_v2\\ash_v2-000017.safetensors", "epoch": 17, "name": "x", "why": ""})
    src = tmp_path / "lib" / "ash" / "2026-09-25_sweep_v2" / "ep17"
    src.mkdir(parents=True)
    (src / "scene_00.png").write_bytes(b"png")

    assert L.state(cfg, "ash")["state"] == "none"
    st = L.draft(cfg, "ash")
    assert st["state"] == "draft" and st["blank"] == 0
    ids = [lk["id"] for c in st["categories"] for lk in c["looks"]]
    # 7 casual shipped already: the pack replaces them, so it is casual_01..07
    # again, not 08..14 (Jeremy, 2026-10-21: "the new assets are supposed to
    # replace the existing")
    assert "casual_01" in ids and "casual_08" not in ids
    assert "work_01" in ids and "workout_01" in ids
    assert L.draft_path(Path(cfg["paths"]["outputs"]), "ash").is_file()
    assert not L.approved_path(Path(cfg["paths"]["outputs"]), "ash").is_file()
    # the guide line shows what her record says for that category
    casual = next(c for c in st["categories"] if c["key"] == "casual")
    assert casual["guide"] == "cropped tops over denim"
    assert next(c for c in st["categories"] if c["key"] == "work")["guide"] == "a short black shirt-dress uniform"

    # his edit lands in the draft
    st = L.save(cfg, "ash", {"all": [{"id": "casual_03", "outfit": "a cobalt moto jacket over a black cami",
                                      "hair": "her hair worn loose"}]})
    got = next(lk for c in st["categories"] for lk in c["looks"] if lk["id"] == "casual_03")
    assert got["outfit"] == "a cobalt moto jacket over a black cami"

    # a blank refuses approval, by name
    L.save(cfg, "ash", {"all": [{"id": "work_02", "outfit": "", "hair": "her hair worn loose"}]})
    with pytest.raises(ValueError, match="work_02"):
        L.approve(cfg, "ash")
    L.save(cfg, "ash", {"all": [{"id": "work_02", "outfit": "the uniform", "hair": "her hair worn loose"}]})

    st = L.approve(cfg, "ash")
    assert st["state"] == "approved" and st["approved_at"]
    plan_file = Path(cfg["paths"]["outputs"]) / "game-assets" / "ash" / "plan_28.json"
    assert plan_file.is_file()
    assert not L.draft_path(Path(cfg["paths"]["outputs"]), "ash").is_file()
    doc = json.loads(plan_file.read_text(encoding="utf-8"))
    assert doc["lora"].endswith("ash_v2-000017.safetensors")
    assert doc["source_asset"].endswith("scene_00.png")
    assert sum(b["lookCount"] for b in doc["categories"].values()) == 28

    # and that is the exact file the shoots tab's guard looks for
    from sourcemode.assets.lora import blocked_shoots
    assert "pack28" not in blocked_shoots(cfg, "ash")

    # Start over on an approved plan: a NEW roll, open beside the approved
    # plan, which keeps rendering until the draft is approved in its place
    st2 = L.draft(cfg, "ash")
    assert st2["state"] == "draft" and st2["seed"] == 1 and st2["approved_at"]
    assert L.approved_path(Path(cfg["paths"]["outputs"]), "ash").is_file()
    fresh = [lk["outfit"] for c in st2["categories"] for lk in c["looks"] if c["key"] == "casual"]
    assert fresh != [lk["outfit"] for c in st["categories"] for lk in c["looks"] if c["key"] == "casual"]
    # edits go into the draft, not the approved plan
    L.save(cfg, "ash", {"all": [{"id": "casual_03", "outfit": "a second-roll edit", "hair": "her hair worn loose"}]})
    kept = json.loads(plan_file.read_text(encoding="utf-8"))
    assert all(e["outfit"] != "a second-roll edit" for e in kept["categories"]["casual"]["looks"])
    st3 = L.approve(cfg, "ash")
    assert st3["state"] == "approved" and st3["seed"] == 1
    assert "a second-roll edit" in [e["outfit"] for e in json.loads(plan_file.read_text(encoding="utf-8"))["categories"]["casual"]["looks"]]


def test_a_continued_run_finds_its_render_under_its_own_epoch_number(tmp_path):
    # priyanka, 2026-10-12: lock priyanka_v2b-000006 = epoch 26; the approve
    # button said "no render of her at epoch 26" while *_sweep_v2b/ep06 had ten
    cfg = _cfg(tmp_path)
    lib = tmp_path / "lib" / "priyanka"
    for d in ("2026-09-20_sweep_v2/ep20", "2026-09-21_sweep_v2b/ep06"):
        (lib / d).mkdir(parents=True)
        (lib / d / "scene_00.png").write_bytes(b"png")
    lora = {"name": "priyanka_v2b-000006.safetensors", "epoch": 26, "path": "x"}
    assert L.source_asset(cfg, "priyanka", 26, lora) == lib / "2026-09-21_sweep_v2b" / "ep06" / "scene_00.png"
    # the plain sweep still wins when the real epoch is there
    assert L.source_asset(cfg, "priyanka", 20, lora) == lib / "2026-09-20_sweep_v2" / "ep20" / "scene_00.png"
    # vivienne: the unnumbered final file of the continued run is its last epoch
    lib = tmp_path / "lib" / "vivienne"
    for d in ("2026-10-10_sweep_v2-asset/ep24", "2026-10-11_sweep_v2b-asset/ep00", "2026-10-11_sweep_v2b-asset/ep04"):
        (lib / d).mkdir(parents=True)
        (lib / d / "scene_00.png").write_bytes(b"png")
    lora = {"name": "vivienne_v2b.safetensors", "epoch": 28, "path": "x"}
    assert L.source_asset(cfg, "vivienne", 28, lora) == lib / "2026-10-11_sweep_v2b-asset" / "ep04" / "scene_00.png"
    # and a v2 lock never borrows from the v2b folders
    assert L.source_asset(cfg, "vivienne", 30, {"name": "vivienne_v2-000030.safetensors", "epoch": 30}) is None
    # the one-name lock (2026-10-15): the run tag is in `file`, not `name`
    lora = {"name": "vivienne.safetensors", "file": "vivienne_v2b.safetensors", "epoch": 28,
            "path": "sourcemode\\vivienne.safetensors"}
    assert L.source_asset(cfg, "vivienne", 28, lora) == lib / "2026-10-11_sweep_v2b-asset" / "ep04" / "scene_00.png"


def test_approve_does_not_need_a_render_the_pack_never_reads(tmp_path, ash, monkeypatch):
    # nisha, 2026-10-15: "she doesn't have ep 21" - the prune had removed her
    # sweep folder, and the pack is T2I and never conditions on that render
    cfg = _cfg(tmp_path)
    from sourcemode.assets import lora as LORA
    monkeypatch.setattr(LORA, "resolve_lora", lambda cfg, c: {
        "path": "sourcemode\\ash.safetensors", "epoch": 17, "name": "ash.safetensors",
        "file": "ash_v2-000017.safetensors", "why": ""})
    L.draft(cfg, "ash")
    st = L.approve(cfg, "ash")
    assert st["state"] == "approved"
    doc = json.loads(L.approved_path(Path(cfg["paths"]["outputs"]), "ash").read_text(encoding="utf-8"))
    assert doc["lora"] == "sourcemode\\ash.safetensors" and doc["source_asset"] is None
    from sourcemode.assets.lora import blocked_shoots
    assert "pack28" not in blocked_shoots(cfg, "ash")


def test_approve_still_refuses_without_a_lock(tmp_path, ash, monkeypatch):
    cfg = _cfg(tmp_path)
    from sourcemode.assets import lora as LORA
    monkeypatch.setattr(LORA, "resolve_lora", lambda cfg, c: None)
    L.draft(cfg, "ash")
    with pytest.raises(ValueError, match="no locked LoRA"):
        L.approve(cfg, "ash")
    assert L.state(cfg, "ash")["state"] == "draft"


def test_scrubs_always_name_the_trousers():
    """Kasia's framing A/B, 2026-10-20: scrubs with no trousers named came back
    chest-up every time; naming them pulled the frame back to mid-thigh."""
    assert L.with_bottoms("Nurse scrubs") == "Nurse scrubs and matching scrub trousers"
    assert L.with_bottoms("scrubs with a pink printed top and plain trousers").endswith("plain trousers")
    assert L.with_bottoms("a red slip dress") == "a red slip dress"
    rng = random.Random(3)
    job = {"job": "Nurse at the hospital", "outfit": "Nurse scrubs", "places": []}
    looks = L._job_looks(job, 5, ["navy", "cream", "black"], rng, "")
    assert all(re.search(r"trousers|pants", lk) for lk in looks), looks


def test_short_dresses_name_the_hem_and_her_legs():
    assert L.with_legs("a navy silk shirt dress cinched with a belt") == \
        "a navy silk shirt dress cinched with a belt, her bare upper thighs showing below the hem"
    assert L.with_legs("a white floral sundress").endswith("below the hem")
    assert L.with_legs("a pink off-the-shoulder midi dress") == "a pink off-the-shoulder midi dress"
    assert L.with_legs("a white tennis dress with built-in shorts").endswith("shorts")
    assert L.with_legs("a cropped hoodie and bike shorts").endswith("shorts")
