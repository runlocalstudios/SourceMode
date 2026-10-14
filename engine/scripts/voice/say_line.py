"""One line in her voice: Chatterbox clones zero-shot from her reference clip.

    uv run --isolated --with chatterbox-tts --with "setuptools<81" --with soundfile \
        python scripts/voice/say_line.py <reference.wav> <out.wav> "<the line>" [exaggeration] [cfg_weight]

CPU only; its own env because Chatterbox pins transformers 5.2. Skips when the
out file exists, so a re-run of the job that queued it costs nothing here.
cfg_weight 0.4 is the unhurried read the selfie videos settled on (Chatterbox's
docs: ~0.3 slows delivery).
"""

import sys
import time
from pathlib import Path

import soundfile as sf

if len(sys.argv) < 4:
    raise SystemExit(__doc__)
REF, OUT, LINE = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
EXAG = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
CFG = float(sys.argv[5]) if len(sys.argv) > 5 else 0.4
if not REF.is_file():
    raise SystemExit(f"no reference clip at {REF}")
if OUT.is_file():
    print(f"LINEDONE exists {OUT}", flush=True)
    sys.exit(0)

from chatterbox.tts import ChatterboxTTS  # noqa: E402

t0 = time.time()
m = ChatterboxTTS.from_pretrained(device="cpu")
print(f"chatterbox on cpu in {time.time() - t0:.0f}s", flush=True)
wav = m.generate(LINE, audio_prompt_path=str(REF), exaggeration=EXAG, cfg_weight=CFG)
OUT.parent.mkdir(parents=True, exist_ok=True)
sf.write(OUT, wav.squeeze(0).numpy(), m.sr)
print(f"LINEDONE {OUT} {wav.shape[-1] / m.sr:.1f}s", flush=True)
