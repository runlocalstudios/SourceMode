"""Render the takes a Music-tab spec asks for (queued; never run by hand).

    python scripts/music/make_takes.py <library/_music/<place>/_spec_*.json>
"""

from __future__ import annotations

import sys
from pathlib import Path

from sourcemode.config import load_config
from sourcemode.music.core import render_spec


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    cfg = load_config()
    made = render_spec(cfg, Path(sys.argv[1]), log=lambda m: print(m, flush=True))
    print(f"done: {len(made)} take(s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
