"""The 28-look plan drafted and approved from the Characters tab (2026-10-12).

Ash had a job, a style and a locked LoRA and the asset pack was still greyed
out, because the plan file it needs had no way to come into being from the
monitor. The draft must give 28 editable lines in the pack's categories, the
work looks must be HER job outfit, and approving must produce exactly the file
`blocked_shoots` looks for - and refuse while a line is blank.
"""

from __future__ import annotations

import json
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


def test_two_jobs_split_the_five_looks_three_and_two(monkeypatch):
    rec = {"style": "", "palette": "black", "avoid": "", "outfits": {},
           "jobs": [{"job": "drinks sales rep", "outfit": "a black blazer over a satin cami", "places": []},
                    {"job": "yoga instructor", "outfit": "a supportive crop and leggings", "places": []}],
           "hair": [], "note": "", "draft": False}
    monkeypatch.setattr(W, "editable", lambda c: rec)
    w = L.work_outfits("cassie")
    assert len(w) == 5
    assert w[0] == "a black blazer over a satin cami" and w[3] == "a supportive crop and leggings"
    assert "sports bra" in w[4]


def _cfg(tmp_path: Path) -> dict:
    return {"paths": {"outputs": str(tmp_path / "out"), "library": str(tmp_path / "lib")}}


def test_draft_extends_her_shipped_looks_and_approve_writes_the_pack_plan(tmp_path, ash, monkeypatch):
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
    assert "casual_08" in ids and "casual_01" not in ids     # 7 shipped -> 8..14
    assert "work_06" in ids and "workout_01" in ids
    assert L.draft_path(Path(cfg["paths"]["outputs"]), "ash").is_file()
    assert not L.approved_path(Path(cfg["paths"]["outputs"]), "ash").is_file()
    # the guide line shows what her record says for that category
    casual = next(c for c in st["categories"] if c["key"] == "casual")
    assert casual["guide"] == "cropped tops over denim"
    assert next(c for c in st["categories"] if c["key"] == "work")["guide"] == "a short black shirt-dress uniform"

    # his edit lands in the draft
    st = L.save(cfg, "ash", {"all": [{"id": "casual_08", "outfit": "a cobalt moto jacket over a black cami",
                                      "hair": "her hair worn loose"}]})
    got = next(lk for c in st["categories"] for lk in c["looks"] if lk["id"] == "casual_08")
    assert got["outfit"] == "a cobalt moto jacket over a black cami"

    # a blank refuses approval, by name
    L.save(cfg, "ash", {"all": [{"id": "work_06", "outfit": "", "hair": "her hair worn loose"}]})
    with pytest.raises(ValueError, match="work_06"):
        L.approve(cfg, "ash")
    L.save(cfg, "ash", {"all": [{"id": "work_06", "outfit": "the uniform", "hair": "her hair worn loose"}]})

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
    L.save(cfg, "ash", {"all": [{"id": "casual_08", "outfit": "a second-roll edit", "hair": "her hair worn loose"}]})
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


def test_approve_refuses_without_a_render_to_condition_on(tmp_path, ash, monkeypatch):
    cfg = _cfg(tmp_path)
    from sourcemode.assets import lora as LORA
    monkeypatch.setattr(LORA, "resolve_lora", lambda cfg, c: {"path": "x", "epoch": 17, "name": "x", "why": ""})
    L.draft(cfg, "ash")
    with pytest.raises(ValueError, match="epoch 17"):
        L.approve(cfg, "ash")
    assert L.state(cfg, "ash")["state"] == "draft"
