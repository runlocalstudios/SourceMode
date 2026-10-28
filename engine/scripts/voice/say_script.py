"""Every line of a script in her voice, one model load: line_00.wav, line_01.wav ...

    uv run --isolated --with chatterbox-tts --with "setuptools<81" --with soundfile \
        python scripts/voice/say_script.py <reference.wav> <out_dir> <lines.json> [exaggeration] [cfg_weight]

lines.json is a list of strings. CPU only; its own env because Chatterbox pins
transformers 5.2. A line already on disk is skipped. cfg_weight is held at one
value for the whole script so the pace does not change from line to line.
"""

import json
import sys
import time
from pathlib import Path

import soundfile as sf

if len(sys.argv) < 4:
    raise SystemExit(__doc__)
REF, OUT, LINES = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
EXAG = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
CFG = float(sys.argv[5]) if len(sys.argv) > 5 else 0.4
if not REF.is_file():
    raise SystemExit(f"no reference clip at {REF}")
lines = json.loads(LINES.read_text(encoding="utf-8"))
OUT.mkdir(parents=True, exist_ok=True)
todo = [(i, t) for i, t in enumerate(lines) if not (OUT / f"line_{i:02d}.wav").is_file()]
if todo:
    from chatterbox.tts import ChatterboxTTS  # noqa: E402

    t0 = time.time()
    m = ChatterboxTTS.from_pretrained(device="cpu")
    print(f"chatterbox on cpu in {time.time() - t0:.0f}s", flush=True)
    for i, text in todo:
        wav = m.generate(text, audio_prompt_path=str(REF), exaggeration=EXAG, cfg_weight=CFG)
        sf.write(OUT / f"line_{i:02d}.wav", wav.squeeze(0).numpy(), m.sr)
        print(f"  line {i}: {wav.shape[-1] / m.sr:.1f}s  {text[:60]}", flush=True)
print(f"SCRIPTDONE {len(lines)} lines in {OUT}", flush=True)
