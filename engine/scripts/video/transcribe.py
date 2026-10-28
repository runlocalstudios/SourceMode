"""What is said in a reference clip, with times: <clip>.transcript.json beside it.

    uv run --isolated --with faster-whisper python scripts/video/transcribe.py <clip.mp4> [...]

CPU lane (faster-whisper, MIT; the `small` model). A video template's audio
script starts from its source's words (Jeremy, 2026-10-28: "set the audio
script to be the same as the source, but something that I can edit"). Skips a
clip whose transcript is already on disk.
"""

import json
import sys
import time
from pathlib import Path

from faster_whisper import WhisperModel

clips = [Path(a) for a in sys.argv[1:]]
if not clips:
    raise SystemExit(__doc__)
model = WhisperModel("small", device="cpu", compute_type="int8")
for clip in clips:
    out = clip.with_suffix(".transcript.json")
    if out.is_file():
        print(f"{clip.name}: transcript exists, skipping", flush=True)
        continue
    t0 = time.time()
    segments, info = model.transcribe(str(clip), language="en", vad_filter=True)
    segs = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segments]
    out.write_text(json.dumps({"clip": clip.name, "language": info.language,
                               "duration": round(info.duration, 2), "segments": segs},
                              indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{clip.name}: {len(segs)} segments in {time.time() - t0:.0f}s", flush=True)
print("TRANSCRIBEDONE", flush=True)
