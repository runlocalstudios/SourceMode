"""Female voice candidates for jojo: Kokoro makes the reference, Chatterbox clones it.

Chatterbox has no pitch or gender control - the voice IS the reference clip, and
with none it uses its built-in voice, which measures 145-154 Hz (male range). That
is what every clip in outputs/voice/jojo_latenight/ was. So each candidate here is:

  ref_<voice>.wav   ~15 s from a Kokoro-82M female voice (Apache 2.0 weights)
  jojo_<voice>.wav  Chatterbox reading jojo's first line with that ref as prompt

Higgs Audio v2 was the first idea; its weights are NOT Apache 2.0 (Boson Higgs
Audio 2 Community License, inherits the Llama 3 AUP), so it is not used.

Runs in an isolated uv env so the engine venv the runner uses is not touched:
  uv run --isolated --with kokoro --with chatterbox-tts --with "setuptools<81" \
      --with soundfile python scripts/video/voice_candidates.py <out_dir>
"""
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent))
from selfie_video_plan import LINES_6S  # noqa: E402

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
VOICES = ["af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky"]
EXAG, CFG = 0.6, 0.4   # same as make_voice.py, so only the voice changes
REF_TEXT = ("Hi, it's me. I just wanted to tell you about my day, because honestly it "
            "was kind of a lot. I spent the whole morning running errands, and then I "
            "got coffee with my sister, and we ended up talking for hours. Anyway, "
            "I'm home now, and I'm finally relaxing.")

from kokoro import KPipeline  # noqa: E402

pipe = KPipeline(lang_code="a")
for v in VOICES:
    dest = OUT / f"ref_{v}.wav"
    if dest.exists():
        continue
    audio = np.concatenate([np.asarray(a) for _, _, a in pipe(REF_TEXT, voice=v)])
    sf.write(dest, audio, 24000)
    print(f"  ref {v}: {len(audio)/24000:4.1f}s", flush=True)

from chatterbox.tts import ChatterboxTTS  # noqa: E402

m = ChatterboxTTS.from_pretrained(device="cpu")
for v in VOICES:
    dest = OUT / f"jojo_{v}.wav"
    if dest.exists():
        continue
    t0 = time.time()
    wav = m.generate(LINES_6S[0], audio_prompt_path=str(OUT / f"ref_{v}.wav"),
                     exaggeration=EXAG, cfg_weight=CFG)
    sf.write(dest, wav.squeeze(0).numpy(), m.sr)
    print(f"  jojo {v}: {wav.shape[-1]/m.sr:4.1f}s in {time.time()-t0:3.0f}s", flush=True)
print("VOICEDONE")
