"""Rewrite the hair clause of every seeded Amanda caption to what the IMAGE shows.

Jeremy, 2026-10-01: "modify the captions to align with the hairstyle because we
only have four hairstyles in the seeds ... a lot say parted to one side that
really just show up as the regular loose hairstyle ... some say ponytail where
her hair is not in a ponytail."

Measured against the seed used: the ponytail seed produced a ponytail in 1 of 13
outputs, the bun seed a bun in 5 of 6, the half-up seed a visible half-up in 5
of 21, the loose seed loose in 27 of 27. The seed does NOT dictate the hair, so
the caption cannot come from the plan - it has to come from the picture. These
calls are by eye from three contact sheets.
"""
import re
from pathlib import Path

IMG = Path("outputs/lora-datasets/amanda_seeded_v2/image_src")
BUN = {12, 38, 39, 45, 54}
PONY = {57}
HALF = {5, 10, 13, 48, 50}
TEXT = {"bun": "her hair in a messy bun", "pony": "her hair in a ponytail",
        "half": "her hair half pinned back", "loose": "her hair worn loose"}
n = 0
for i in range(67):
    p = IMG / f"src_{i:03d}.txt"
    cap = p.read_text(encoding="utf-8")
    st = "bun" if i in BUN else "pony" if i in PONY else "half" if i in HALF else "loose"
    new = re.sub(r"her hair[^,]*", TEXT[st], cap, count=1)
    if new != cap:
        p.write_text(new, encoding="utf-8"); n += 1
print(f"rewrote {n} of 67 hair clauses")
