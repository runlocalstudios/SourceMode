"""Make a voice from a description: Parler-TTS reads the reference text N times.

    uv run --isolated --with parler-tts --with soundfile python \
        scripts/voice/make_voice_parler.py <set_dir>

<set_dir>/spec.json: {character, description, text, takes, seed, model}
Writes <set_dir>/take_NN.wav (+ .json) - the reference clips Chatterbox will
clone from. Nothing of the engine is imported: this runs in its own env
because Parler pins transformers 4.46 and Chatterbox pins 5.2.

Parler-TTS (Apache 2.0, code and weights): the description IS the voice. No
sample of anyone goes in, so the voice is fully synthetic - the one thing a
commercial game can ship without a likeness question.
"""

import json
import sys
import time
from pathlib import Path

import soundfile as sf

SET = Path(sys.argv[1])
spec = json.loads((SET / "spec.json").read_text(encoding="utf-8"))
MODEL = spec.get("model") or "parler-tts/parler-tts-mini-v1"
desc = spec["description"].strip()
text = spec["text"].strip()
n = int(spec.get("takes") or 3)
base = int(spec.get("seed") or 1100)

todo = [t for t in range(1, n + 1) if not (SET / f"take_{t:02d}.wav").exists()]
if not todo:
    print("VOICEDONE nothing to do", flush=True)
    sys.exit(0)

import torch  # noqa: E402
from parler_tts import ParlerTTSForConditionalGeneration  # noqa: E402
from transformers import AutoTokenizer  # noqa: E402

device = "cuda" if torch.cuda.is_available() else "cpu"
t0 = time.time()
model = ParlerTTSForConditionalGeneration.from_pretrained(MODEL).to(device)
tok = AutoTokenizer.from_pretrained(MODEL)
print(f"{MODEL} on {device} in {time.time() - t0:.0f}s", flush=True)
sr = int(model.config.sampling_rate)
desc_ids = tok(desc, return_tensors="pt").input_ids.to(device)
text_ids = tok(text, return_tensors="pt").input_ids.to(device)

for t in todo:
    seed = base + t * 100
    torch.manual_seed(seed)
    t1 = time.time()
    with torch.no_grad():
        gen = model.generate(input_ids=desc_ids, prompt_input_ids=text_ids)
    audio = gen.cpu().numpy().squeeze()
    dest = SET / f"take_{t:02d}.wav"
    sf.write(dest, audio, sr)
    secs = round(len(audio) / sr, 2)
    dest.with_suffix(".json").write_text(json.dumps({
        "take": t, "seed": seed, "seconds": secs, "sr": sr, "model": MODEL,
        "description": desc, "text": text, "render_s": round(time.time() - t1, 1)}, indent=1),
        encoding="utf-8")
    print(f"  take {t}: {secs}s in {time.time() - t1:.0f}s (seed {seed})", flush=True)

print(f"VOICEDONE {spec.get('character')} {len(todo)} take(s)", flush=True)
