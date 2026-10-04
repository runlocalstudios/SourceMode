"""Generate every line for the selfie videos in one pass. CPU only.

cfg_weight is held at ONE value across the whole set. Chatterbox's docs note ~0.3
slows delivery; 0.4 is unhurried without dragging. Holding it constant is half of
the fix for Jeremy's note that later legs sped up - the other half is that each
12 s video gets ONE continuous clip rather than one per leg, so there is no seam
in the audio timeline for the pacing to change at.
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import torchaudio
from chatterbox.tts import ChatterboxTTS
from selfie_video_plan import LINES_6S, LINES_12S

OUT = Path("outputs/voice/jojo_latenight"); OUT.mkdir(parents=True, exist_ok=True)
EXAG, CFG = 0.6, 0.4          # flirty but not theatrical; unhurried

m = ChatterboxTTS.from_pretrained(device="cpu")
print(f"sr={m.sr}  exaggeration={EXAG}  cfg_weight={CFG} (held constant)")

jobs = [(f"clip6_{i+1}", t) for i, t in enumerate(LINES_6S)] + \
       [(f"clip12_{i+1}", t) for i, t in enumerate(LINES_12S)]
for name, text in jobs:
    dest = OUT / f"{name}.wav"
    if dest.exists():
        print(f"  {name}: exists, skipping"); continue
    t0 = time.time()
    wav = m.generate(text, exaggeration=EXAG, cfg_weight=CFG)
    torchaudio.save(str(dest), wav, m.sr)
    print(f"  {name}: {wav.shape[-1]/m.sr:5.1f}s audio in {time.time()-t0:3.0f}s")
print("VOICEDONE")
