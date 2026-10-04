"""Preview for a dataset whose folder name is not <trigger>_v2.

    python preview_named.py amanda_seeded_v2 amanda
"""
import sys
from pathlib import Path

from sourcemode.config import load_config
from sourcemode.train.preview import build_preview, preview_root

ds_id, trigger = sys.argv[1], sys.argv[2]
d = build_preview(preview_root(load_config()), Path(f"outputs/lora-datasets/{ds_id}"),
                  dataset_id=ds_id, trigger=trigger, render_size=(1024, 1536), bucket_px=1536)
g = d["gate"]
print(f"{ds_id}: {d['n']} images, gate {g['score']}, failing {g['failed']}; caption checks failing {d['captions']['failed']}")
for f in g["findings"]:
    if not f["passed"]:
        print(f"   FAIL {f['check']}: {f['detail'][:96]}")
