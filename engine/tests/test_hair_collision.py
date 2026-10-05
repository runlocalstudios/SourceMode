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
from sourcemode.assets.wardrobe import DEFAULT_HAIR, SHORT_HAIR, hair_options, is_short_haired

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
        if is_up_style(hair):
            assert not DOWN.search(ident), f"{char}: {hair!r} with {ident!r}"


def test_priya_is_short_haired_and_never_asked_to_put_it_up():
    assert is_short_haired("priya")
    assert hair_options("priya") == SHORT_HAIR
    for l in LOOKS:
        _, hair = _parts(shot_prompt("priya", dict(l, pose="standing"), "priya"))
        assert not is_up_style(hair), hair


def test_long_haired_characters_keep_the_shared_rotation():
    assert not is_short_haired("zara")
    assert hair_options("zara") == DEFAULT_HAIR
