"""No prompt may ask for hair UP while its identity clause says the hair is DOWN.

Geena and Cindy, 2026-10-04: "long" + a bun rendered the full length hanging
with a bun perched on top, 10 of 10. Priya, 2026-10-05: "a chin-length bob" +
a messy bun did the same in her influencer pack, because the fix only stripped
LONG words. This walks every character x every hair a prompt can be given and
fails on any surviving collision, whichever builder or record introduced it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from sourcemode.assets import influencer as I
from sourcemode.assets.appearance import APPEARANCE, is_up_style
from sourcemode.assets.render import shot_prompt
from sourcemode.assets.wardrobe import DEFAULT_HAIR, SHORT_HAIR, hair_options, is_own_hair, is_short_haired

DOWN = re.compile(r"\b(long|chin-length|shoulder-length|jaw-length|bob|pixie|worn loose|"
                  r"falling|hanging|past her shoulders|down her back)\b", re.I)

sys.path.insert(0, str(Path("scripts/eval").resolve()))
from asset_scenes import LOOKS  # noqa: E402

CHARS = [k for k in json.loads(APPEARANCE.read_text(encoding="utf-8")) if not k.startswith("_")]


def _parts(p: str) -> tuple[str, str]:
    ident = re.search(r" of (.*?), her body shape", p)
    hair = re.search(r"Hair: (.*?)\. ", p)
    return (ident.group(1) if ident else ""), (hair.group(1) if hair else "")


@pytest.mark.parametrize("char", CHARS)
def test_no_prompt_puts_hair_up_and_down_at_once(char):
    hairs = set(DEFAULT_HAIR) | set(hair_options(char)) | {l["hair"] for l in LOOKS}
    slots = [{"id": "x", "look": i, "category": "casual", "pose": "standing",
              "outfit": "a white tee", "hair": h} for i, h in enumerate(sorted(hairs))]
    slots += I.slots(char, 1)
    for s in slots:
        ident, hair = _parts(shot_prompt(char, s, char, backdrop=s.get("setting")))
        # a line he wrote into her brief himself is his call, collision or not
        if is_up_style(hair) and not is_own_hair(char, hair):
            assert not DOWN.search(ident), f"{char}: {hair!r} with {ident!r}"


def test_priya_is_short_haired_and_never_asked_to_put_it_up():
    """Canned up-styles are swapped for a short-haired character; her OWN
    wardrobe lines are never touched. Jeremy, 2026-10-15: "If I put low
    ponytail for a character, I want a low ponytail." """
    assert is_short_haired("priya")
    own = hair_options("priya")
    assert own != SHORT_HAIR, "priya has her own hair list in wardrobe.json"
    for h in own:
        p = shot_prompt("priya", {"id": "x", "look": 1, "category": "casual", "pose": "standing",
                                  "outfit": "a white tee", "hair": h}, "priya")
        assert f", {h}, wearing" in p, f"his line {h!r} is not in the prompt: {p}"
    for l in LOOKS:
        if is_own_hair("priya", l["hair"]):
            continue
        _, hair = _parts(shot_prompt("priya", dict(l, pose="standing"), "priya"))
        assert not is_up_style(hair), hair


def test_a_canned_up_style_is_still_swapped_for_short_hair():
    p = shot_prompt("priya", {"id": "x", "look": 1, "category": "casual", "pose": "standing",
                              "outfit": "a white tee", "hair": "her hair up in a messy bun"}, "priya")
    assert "messy bun" not in p
    from sourcemode.assets.wardrobe import hair_options
    assert any(f", {s}, wearing" in p for s in hair_options("priya")), p


def test_long_haired_characters_keep_the_shared_rotation():
    assert not is_short_haired("zara")
    assert hair_options("zara") == DEFAULT_HAIR


def test_a_short_haired_character_with_her_own_list_never_gets_a_canned_clause(monkeypatch):
    from sourcemode.assets import wardrobe as W
    monkeypatch.setattr(W, "is_short_haired", lambda c: c in ("linda", "priya"))
    monkeypatch.setattr(W, "brief", lambda c: {"hair": ["her short hair neatly styled",
                                                        "her short hair tousled and messy"]} if c == "linda" else {})
    own = {"her short hair neatly styled", "her short hair tousled and messy"}
    for clause in ("her hair worn loose", "her hair tucked behind her ears", "her hair in a high ponytail"):
        assert W.short_hair("linda", clause, 3) in own
    assert W.short_hair("linda", "her short hair tousled and messy", 1) == "her short hair tousled and messy"
    # no list of her own: only an up-style is swapped, as before
    assert W.short_hair("priya", "her hair worn loose", 2) == "her hair worn loose"
    assert W.short_hair("priya", "her hair in a messy bun", 2) in W.SHORT_HAIR
    assert W.short_hair("zara", "her hair in a messy bun", 2) == "her hair in a messy bun"
