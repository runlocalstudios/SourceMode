"""Places, takes, verdicts and the ship into the game.

Jeremy, 2026-11-02: "I'd prefer to create things myself than rely on trusting
licensing for other peoples' stuff ... I care that it's easy for me to generate,
review and then pipe into the game sort of how sourcemode does that with
pictures." One looping track per district and per venue, no silence between.

- `music/places.json` (repo root) holds each place's prompt. Its `id` is the file
  the game plays: `src/assets/music/<id>.mp3`. A venue id is the game's location
  id; a district id is `district_<district>`.
- Takes are rendered by ACE-Step 1.5 XL through ComfyUI (`workflows/ace15_music.json`),
  one queue job per batch (`scripts/music/make_takes.py`), into
  `library/_music/<place>/take_NNNN.mp3`, each with a sidecar `take_NNNN.json`
  holding the prompt, seed, model and his verdict.
- Shipping one take trims its silence, evens its loudness (EBU R128, so no place
  is louder than another) and writes it to the game. That, on the Music tab, is the
  only thing here that writes into the game repo.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from ..config import ENGINE_ROOT

#: the two ACE-Step 1.5 XL models, settings from ComfyUI 0.25.1's own templates
MODELS = {
    "turbo": {"file": "acestep_v1.5_xl_turbo_bf16.safetensors", "steps": 8, "cfg": 1.0,
              "label": "Turbo (fast drafts)"},
    "sft": {"file": "acestep_v1.5_xl_sft_bf16.safetensors", "steps": 50, "cfg": 7.0,
            "label": "SFT (slower, finer)"},
}
#: Jeremy, 2026-11-02: the slower, finer setting is the default
DEFAULT_MODEL = "sft"
KEYS = [f"{root} {q}" for q in ("major", "minor")
        for root in ("C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B")]
VERDICTS = ("keep", "reject")
EDITABLE = ("tags", "bpm", "keyscale", "seconds")
TARGET_LUFS = -18          # quiet enough to sit under dialogue; every place lands here
BITRATE = "160k"
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,47}$")
_TAKE = re.compile(r"^take_(\d{4})\.mp3$")


# --- places ----------------------------------------------------------------------

def places_path() -> Path:
    return ENGINE_ROOT.parent / "music" / "places.json"


def _load(path: Path | None = None) -> dict:
    return json.loads((path or places_path()).read_text(encoding="utf-8"))


def places(path: Path | None = None) -> list[dict]:
    return list(_load(path).get("places") or [])


def place(place_id: str, path: Path | None = None) -> dict:
    for p in places(path):
        if p["id"] == place_id:
            return p
    raise KeyError(f"no music place {place_id!r}")


def check_place_id(place_id: str) -> str:
    if not _ID.match(place_id or ""):
        raise ValueError(f"not a place id: {place_id!r}")
    return place_id


def update_place(place_id: str, fields: dict, path: Path | None = None) -> dict:
    """Write his edits to a place's prompt. Only the prompt fields move."""
    path = path or places_path()
    doc = _load(path)
    for p in doc.get("places") or []:
        if p["id"] != place_id:
            continue
        for k in EDITABLE:
            if k not in fields:
                continue
            v = fields[k]
            if k == "tags":
                v = str(v).strip()
                if len(v) < 12:
                    raise ValueError("describe the music - a line of style tags")
            elif k == "bpm":
                v = int(v)
                if not 40 <= v <= 200:
                    raise ValueError("bpm must be 40 to 200")
            elif k == "seconds":
                v = int(v)
                if not 30 <= v <= 360:
                    raise ValueError("length must be 30 to 360 seconds")
            elif k == "keyscale" and v not in KEYS:
                raise ValueError(f"not a key: {v!r}")
            p[k] = v
        _write_json(path, doc)
        return p
    raise KeyError(f"no music place {place_id!r}")


def _write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# --- takes -----------------------------------------------------------------------

def music_root(cfg: dict) -> Path:
    from ..library import library_dir  # noqa: PLC0415

    return library_dir(cfg) / "_music"


def place_dir(cfg: dict, place_id: str) -> Path:
    return music_root(cfg) / check_place_id(place_id)


def next_take_number(folder: Path) -> int:
    nums = [int(m.group(1)) for f in folder.glob("take_*.mp3") if (m := _TAKE.match(f.name))]
    return max(nums, default=0) + 1


def takes(cfg: dict, place_id: str) -> list[dict]:
    """Every take for a place, newest first, with its sidecar."""
    d = place_dir(cfg, place_id)
    out = []
    for f in sorted(d.glob("take_*.mp3"), reverse=True):
        if not _TAKE.match(f.name):
            continue
        meta = {}
        side = f.with_suffix(".json")
        if side.is_file():
            try:
                meta = json.loads(side.read_text(encoding="utf-8"))
            except ValueError:
                meta = {}
        out.append({"name": f.stem, "path": str(f), "verdict": meta.get("verdict"),
                    "model": meta.get("model"), "seed": meta.get("seed"), "bpm": meta.get("bpm"),
                    "keyscale": meta.get("keyscale"), "seconds": meta.get("seconds"),
                    "tags": meta.get("tags"), "made": meta.get("made"),
                    "render_s": meta.get("render_s")})
    return out


def take_path(cfg: dict, place_id: str, name: str) -> Path:
    if not re.match(r"^take_\d{4}$", name or ""):
        raise ValueError(f"not a take: {name!r}")
    f = place_dir(cfg, place_id) / f"{name}.mp3"
    if not f.is_file():
        raise FileNotFoundError(f"{place_id} has no {name}")
    return f


def set_verdict(cfg: dict, place_id: str, name: str, verdict: str | None) -> dict:
    if verdict not in (*VERDICTS, None):
        raise ValueError(f"verdict must be keep, reject or none, not {verdict!r}")
    f = take_path(cfg, place_id, name)
    side = f.with_suffix(".json")
    meta = json.loads(side.read_text(encoding="utf-8")) if side.is_file() else {}
    if verdict is None:
        meta.pop("verdict", None)
    else:
        meta["verdict"] = verdict
    _write_json(side, meta)
    return meta


def write_spec(cfg: dict, place_id: str, *, count: int, model: str, seed: int | None = None) -> Path:
    """Freeze the prompt as it stands into a spec the queued job reads, so an edit
    made while the job waits does not change what it renders."""
    if model not in MODELS:
        raise ValueError(f"model must be one of {sorted(MODELS)}")
    if not 1 <= count <= 8:
        raise ValueError("takes must be 1 to 8")
    p = place(place_id)
    d = place_dir(cfg, place_id)
    d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    spec = {"place": place_id, "label": p.get("label"), "tags": p["tags"], "bpm": int(p["bpm"]),
            "keyscale": p["keyscale"], "seconds": int(p["seconds"]), "count": count, "model": model,
            "seed": int(seed) if seed is not None else int(time.time()) % 1_000_000_000}
    out = d / f"_spec_{stamp}.json"
    _write_json(out, spec)
    return out


def make_command(spec_path: Path) -> list[str]:
    py = ENGINE_ROOT / ".venv" / "Scripts" / "python.exe"
    return [str(py), str(ENGINE_ROOT / "scripts" / "music" / "make_takes.py"), str(spec_path)]


# --- rendering (the queued job) ---------------------------------------------------

def build_workflow(cfg: dict, *, model: str, tags: str, seed: int, bpm: int, seconds: float,
                   keyscale: str, prefix: str, timesig: str = "4") -> dict:
    """The API-format graph for one take, from workflows/ace15_music.json."""
    from ..config import workflows_dir  # noqa: PLC0415

    m = MODELS[model]
    raw = json.loads((workflows_dir(cfg) / "ace15_music.json").read_text(encoding="utf-8"))
    raw.pop("_meta", None)
    vals = {"MODEL": m["file"], "TAGS": tags, "LYRICS": "[Instrumental]", "SEED": int(seed),
            "BPM": int(bpm), "SECONDS": float(seconds), "KEYSCALE": keyscale, "TIMESIG": timesig,
            "STEPS": m["steps"], "CFG": m["cfg"], "PREFIX": prefix}

    def sub(v):
        if isinstance(v, str) and v.startswith("{{") and v.endswith("}}"):
            return vals[v[2:-2]]
        return v

    for node in raw.values():
        node["inputs"] = {k: sub(v) for k, v in node["inputs"].items()}
    return raw


def render_spec(cfg: dict, spec_path: Path, *, client=None, log=print) -> list[Path]:
    """Render every take a spec asks for, numbered after the takes already there."""
    from ..render.client import ComfyUIClient  # noqa: PLC0415

    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    d = place_dir(cfg, spec["place"])
    client = client or ComfyUIClient(cfg["comfyui"]["host"], int(cfg["comfyui"]["port"]))
    made = []
    for i in range(int(spec["count"])):
        n = next_take_number(d)
        seed = int(spec["seed"]) + i
        t = time.time()
        wf = build_workflow(cfg, model=spec["model"], tags=spec["tags"], seed=seed, bpm=spec["bpm"],
                            seconds=spec["seconds"], keyscale=spec["keyscale"],
                            prefix=f"sourcemode/music/{spec['place']}")
        entry = client.wait(client.submit(wf), timeout_s=3600)
        files = [f for f in client.outputs(entry) if str(f.get("filename", "")).endswith(".mp3")]
        if not files:
            raise RuntimeError(f"take {i + 1} came back with no mp3")
        dest = d / f"take_{n:04d}.mp3"
        client.fetch(files[0], dest)
        _write_json(dest.with_suffix(".json"), {
            "place": spec["place"], "model": spec["model"], "seed": seed, "tags": spec["tags"],
            "bpm": spec["bpm"], "keyscale": spec["keyscale"], "seconds": spec["seconds"],
            "made": time.strftime("%Y-%m-%dT%H:%M:%S"), "render_s": round(time.time() - t, 1),
            "spec": Path(spec_path).name})
        made.append(dest)
        log(f"take {i + 1}/{spec['count']}: {dest.name} in {time.time() - t:.0f}s")
    return made


# --- shipping ---------------------------------------------------------------------

def ffmpeg_exe(cfg: dict) -> str:
    exe = (cfg.get("music") or {}).get("ffmpeg") or shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg is not on PATH - set [music] ffmpeg in config.toml")
    return exe


def process_command(exe: str, src: Path, dest: Path) -> list[str]:
    """Trim silence at both ends, even out loudness, encode for the browser.

    No fade is added: the game loops the track by fading its end into its own
    start, and a baked-in fade-out would dip twice."""
    trim = "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.05"
    chain = ",".join([trim, "areverse", trim, "areverse",
                      f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11"])
    return [exe, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-af", chain,
            "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", BITRATE, "-map_metadata", "-1",
            str(dest)]


def game_music_dir(game_root: Path | None = None) -> Path:
    if game_root is None:
        from ..assets.looks import GAME_ROOT as game_root  # noqa: PLC0415, N811
    return Path(game_root) / "src" / "assets" / "music"


def shipped(cfg: dict) -> dict:
    p = music_root(cfg) / "shipped.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def ship(cfg: dict, place_id: str, name: str, *, game_root: Path | None = None, run=subprocess.run) -> dict:
    """His approval: process the take and write it as the place's track in the game."""
    place(place_id)
    src = take_path(cfg, place_id, name)
    from ..config import outputs_dir  # noqa: PLC0415

    work = outputs_dir(cfg) / "music"
    work.mkdir(parents=True, exist_ok=True)
    staged = work / f"{place_id}.mp3"
    r = run(process_command(ffmpeg_exe(cfg), src, staged), capture_output=True, text=True, check=False)
    if r.returncode != 0 or not staged.is_file():
        raise RuntimeError("ffmpeg failed: " + (r.stderr or "").strip()[-400:])
    dest_dir = game_music_dir(game_root)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{place_id}.mp3"
    replaced = dest.is_file()
    shutil.copy2(staged, dest)
    set_verdict(cfg, place_id, name, "keep")
    rec = {"take": name, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "to": str(dest),
           "bytes": dest.stat().st_size, "replaced": replaced}
    doc = shipped(cfg)
    doc[place_id] = rec
    _write_json(music_root(cfg) / "shipped.json", doc)
    return rec
