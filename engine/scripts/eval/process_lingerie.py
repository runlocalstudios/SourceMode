"""`process_intimate.py <character> lingerie` - kept so queued jobs that still name this script run."""
import runpy
import sys
from pathlib import Path

sys.argv = [sys.argv[0], *[a for a in sys.argv[1:] if not a.startswith("--")][:1], "lingerie"]
runpy.run_path(str(Path(__file__).with_name("process_intimate.py")), run_name="__main__")
