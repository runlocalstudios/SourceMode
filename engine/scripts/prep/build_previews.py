"""Build the approval preview for one or more characters.

    python build_previews.py raven mira sunny

bucket_px MUST be 1536 to match how every approved dataset was measured - the
default of 1024 reports a face 30% smaller and fails the resolution gate on a set
that actually passes.
"""
import sys
from pathlib import Path

from sourcemode.config import load_config
from sourcemode.train.preview import build_preview, preview_root

root = preview_root(load_config())
for char in sys.argv[1:]:
    ds = Path(f"outputs/lora-datasets/{char}_v2")
    if not (ds / "image_src").is_dir():
        print(f"{char}: no image_src"); continue
    d = build_preview(root, ds, dataset_id=f"{char}_v2", trigger=char,
                      render_size=(1024, 1536), bucket_px=1536)
    g = d["gate"]
    print(f"{char}_v2: {d['n']} images, gate {g['score']}, failing {g['failed']}")
    print(f"   caption checks failing: {d['captions']['failed']}")
    for f in g["findings"]:
        if not f["passed"]:
            print(f"   FAIL {f['check']}: {f['detail'][:96]}")
print("PREVIEWSDONE")
