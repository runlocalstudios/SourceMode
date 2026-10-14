"""Her voice: the reference clip Chatterbox clones from, recorded per character.

Jeremy, 2026-10-14: "once I pick a voice for each character or create one,
can those be loaded into the characters screen as well?" The clip is the
audio twin of her locked LoRA, so it gets the same treatment: one record in
characters/voices.json, chosen by him, read by everything that speaks.

    characters/voices.json
    {
      "amanda": {
        "reference": "C:/.../library/amanda/2026-10-14_voice_bright/take_02.wav",
        "description": "a young woman, bright and slightly breathy ...",
        "model": "parler-tts-mini-v1", "seed": 2200,
        "chosen_at": "2026-10-14T18:02:11+00:00"
      }
    }

A voice is MADE from a description (Parler-TTS, Apache 2.0: the description is
the whole source, no sample of anyone), or picked from a candidate clip; it is
USED by Chatterbox, which clones zero-shot from the first 10 seconds of it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VOICES = ROOT / "characters" / "voices.json"

#: Parler's own recommended tail - without it the takes come back roomy and far
QUALITY_TAIL = ("The recording is of very high quality, with the speaker's voice sounding "
                "clear and very close up.")
#: ~15 s of natural speech for the reference clip (Chatterbox reads the first 10)
REFERENCE_TEXT = ("Hi, it's me. I just wanted to tell you about my day, because honestly it "
                  "was kind of a lot. I spent the whole morning running errands, and then I "
                  "got coffee with my sister, and we ended up talking for hours. Anyway, "
                  "I'm home now, and I'm finally relaxing.")
#: the line the clone reads back, so he hears the voice as Chatterbox will use it
CHECK_LINE = "Hey you. I was starting to think you'd forgotten about me. Come sit with me for a minute."


def _load(path: Path | None = None) -> dict:
    p = path or VOICES
    if not p.is_file():
        return {}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in doc.items() if not k.startswith("_")}


def get(character: str, path: Path | None = None) -> dict | None:
    rec = _load(path).get(character.lower())
    if not rec:
        return None
    rec = dict(rec)
    rec["on_disk"] = bool(rec.get("reference")) and Path(rec["reference"]).is_file()
    return rec


def set_voice(character: str, *, reference: Path | str, description: str = "", model: str = "",
              seed: int | None = None, path: Path | None = None) -> dict:
    """Record her voice. The clip must exist: a record pointing at nothing is
    how a job dies an hour in."""
    ref = Path(reference)
    if not ref.is_file():
        raise FileNotFoundError(f"{ref} is not on disk")
    p = path or VOICES
    doc = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    doc.setdefault("_comment", ["Her reference clip, chosen on the Characters tab. Chatterbox clones "
                                "from it zero-shot; S2V and every voice job read it from here."])
    rec = {"reference": str(ref), "description": description, "model": model, "seed": seed,
           "chosen_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())}
    doc[character.lower()] = rec
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)
    return rec


def clear(character: str, path: Path | None = None) -> bool:
    p = path or VOICES
    if not p.is_file():
        return False
    doc = json.loads(p.read_text(encoding="utf-8"))
    if character.lower() not in doc:
        return False
    doc.pop(character.lower())
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)
    return True


def takes(library: Path, character: str) -> list[dict]:
    """Her voice sets, newest first: every take with its description and, when
    the clone pass has run, the Chatterbox read of the check line."""
    home = library / character.lower()
    out = []
    for d in sorted(home.glob("*_voice_*"), reverse=True) if home.is_dir() else []:
        if not d.is_dir():
            continue
        spec = {}
        if (d / "spec.json").is_file():
            try:
                spec = json.loads((d / "spec.json").read_text(encoding="utf-8"))
            except ValueError:
                spec = {}
        rows = []
        for wav in sorted(d.glob("take_*.wav")):
            if wav.stem.endswith("_chatterbox"):
                continue
            meta = {}
            if wav.with_suffix(".json").is_file():
                try:
                    meta = json.loads(wav.with_suffix(".json").read_text(encoding="utf-8"))
                except ValueError:
                    meta = {}
            clone = wav.with_name(wav.stem + "_chatterbox.wav")
            rows.append({"file": str(wav), "take": wav.stem, "seed": meta.get("seed"),
                         "seconds": meta.get("seconds"), "description": meta.get("description"),
                         "clone": str(clone) if clone.is_file() else None})
        # legacy candidate sets (ref_*.wav + <char>_*.wav pairs) show as takes too
        if not rows:
            for wav in sorted(d.glob("ref_*.wav")):
                clone = d / f"{character.lower()}_{wav.stem[4:]}.wav"
                rows.append({"file": str(wav), "take": wav.stem, "seed": None, "seconds": None,
                             "description": spec.get("description") or wav.stem[4:],
                             "clone": str(clone) if clone.is_file() else None})
        out.append({"folder": str(d), "name": d.name, "date": d.name[:10], "spec": spec, "takes": rows,
                    "done": bool(rows) and len(rows) >= int(spec.get("takes") or len(rows) or 1)})
    return out
