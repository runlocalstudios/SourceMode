"""Hear each reference take the way Chatterbox will use it: the clone reads
the check line from every take_NN.wav that has no take_NN_chatterbox.wav yet.

    uv run --isolated --with chatterbox-tts --with "setuptools<81" --with soundfile \
        python scripts/voice/clone_check.py <set_dir>

<set_dir>/spec.json may carry `check_line`, `exaggeration`, `cfg_weight`.
Runs in its own env (Chatterbox pins transformers 5.2; Parler pins 4.46).
"""

import json
import sys
import time
from pathlib import Path

import soundfile as sf

SET = Path(sys.argv[1])
spec = json.loads((SET / "spec.json").read_text(encoding="utf-8")) if (SET / "spec.json").is_file() else {}
LINE = spec.get("check_line") or ("Hey you. I was starting to think you'd forgotten about me. "
                                  "Come sit with me for a minute.")
EXAG = float(spec.get("exaggeration") or 0.5)
CFG = float(spec.get("cfg_weight") or 0.4)

refs = [w for w in sorted(SET.glob("take_*.wav")) if not w.stem.endswith("_chatterbox")
        and not w.with_name(w.stem + "_chatterbox.wav").exists()]
refs += [w for w in sorted(SET.glob("ref_*.wav"))                      # legacy candidate sets
         if not (SET / f"{spec.get('character', 'x')}_{w.stem[4:]}.wav").exists()
         and not w.with_name(w.stem + "_chatterbox.wav").exists()]
if not refs:
    print("CLONEDONE nothing to do", flush=True)
    sys.exit(0)

from chatterbox.tts import ChatterboxTTS  # noqa: E402

t0 = time.time()
m = ChatterboxTTS.from_pretrained(device="cpu")
print(f"chatterbox on cpu in {time.time() - t0:.0f}s", flush=True)
for ref in refs:
    t1 = time.time()
    wav = m.generate(LINE, audio_prompt_path=str(ref), exaggeration=EXAG, cfg_weight=CFG)
    dest = ref.with_name(ref.stem + "_chatterbox.wav")
    sf.write(dest, wav.squeeze(0).numpy(), m.sr)
    print(f"  {ref.name} -> {dest.name}: {wav.shape[-1] / m.sr:.1f}s in {time.time() - t1:.0f}s", flush=True)
print(f"CLONEDONE {len(refs)} clone(s)", flush=True)
