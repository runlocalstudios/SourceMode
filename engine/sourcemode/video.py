"""Video: one still of her becomes a clip, through Wan 2.2 I2V.

Jeremy, 2026-10-14: "We never set up the video capability to create from an
existing asset or to generate a new T2I then animate?" We had the graph (the
I2V builder in render/passes, verified against his working ComfyUI graph) and
the S2V template, and every clip so far was a session running a script by
hand. This is the product path: a spec the Video tab writes, a queue job that
renders it, clips in her library.

    source   a keeper from her library (a judged keep), or a new still rendered
             through her LoRA first - identity lives in the still, because Qwen
             character LoRAs do not apply to Wan
    motion   what happens, in his words, plus one pacing clause repeated on
             every leg (his note on the stitched Jojo videos: legs sped up at
             the seams unless the pace was stated the same way in each)
    length   anything up to the per-leg cap renders as one leg; longer is
             chained - the last frame of leg N, colour-matched back to the
             ORIGINAL source so drift does not compound, starts leg N+1, and the
             legs are stitched dropping each seam's duplicated frame. Ported
             from the reference implementation (e2egen/video.py), which is the
             read-only source of truth for the chaining
    takes    N clips from the same still on different seeds; the keeper is a
             choice he makes after, not a default the pipeline guesses

Output: library/<character>/<date>_video_<name>/
    source.png        the still as fed to Wan (bucketed, centre-cropped)
    source_src.png    the still as it was (the keeper, or the T2I render)
    take_01.mp4 ...   one per take; a chained take also keeps _legs/take_01_leg_01.mp4
    take_01.json      spec, seeds, frames, timing
    spec.json         the request as queued
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

FRAMINGS = {
    "chest": "framed from the chest up",
    "waist": "framed from the waist up",
    "thighs": "framed from the upper thighs up",
}
QUALITIES = {
    # render pass -> (label, seconds of card time per second of clip, note).
    # medium = the 4-step Lightning pass: ~10 min per 6 s at 1024x1280, measured
    # 2026-08-31 on the 5090 (config.toml [render.medium]). final = 28 steps,
    # ~2.4 h per 6 s. The still, when one is rendered, costs about a minute.
    "medium": ("Quick (4-step Lightning)", 100.0, "about 10 minutes per 6 seconds"),
    "final": ("Full (28 steps)", 1440.0, "about 2.4 hours per 6 seconds - overnight work"),
}
STILL_SECONDS = 60.0
PACING = "natural unhurried movement, a steady camera"
NEGATIVE = ("blurry, distorted, deformed hands, extra limbs, warped face, static, frozen, "
            "flicker, jump cut, watermark, text, low quality")
#: what the Motion chips offer - starting points he edits, never the whole menu
MOTIONS = (
    ("looks up and smiles", "she looks up into the camera and breaks into a warm smile"),
    ("slow turn", "she turns slowly toward the camera, her hair swinging with the turn"),
    ("walks closer", "she walks slowly toward the camera, relaxed, holding eye contact"),
    ("laughs", "she laughs, head tipping back a little, then looks back into the camera"),
    ("hair over shoulder", "she pushes her hair back over one shoulder and holds the look"),
    ("leans in", "she leans in toward the camera with a slow, knowing smile"),
    ("talks", "she talks to the camera, animated, hands moving a little as she speaks"),
    ("wind", "a soft breeze moves her hair and the fabric of her clothes, she holds the pose"),
)


@dataclass
class VideoSpec:
    character: str
    motion: str
    seconds: float = 5.0
    quality: str = "medium"
    takes: int = 1
    name: str = ""
    # source: {"kind": "keeper", "path": ...} or
    #         {"kind": "still", "outfit": ..., "hair": ..., "setting": ..., "framing": "waist"}
    source: dict = field(default_factory=dict)
    seed: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> "VideoSpec":
        known = {f: d[f] for f in cls.__dataclass_fields__ if f in d}
        return cls(**known)


def validate(spec: VideoSpec, *, leg_cap_s: float, max_seconds: float = 30.0) -> list[str]:
    """Plain sentences for what is wrong; empty means it can be queued."""
    p: list[str] = []
    c = (spec.character or "").strip().lower()
    if not c or any(x in c for x in ("/", "\\", "..")):
        p.append("a character is required")
    if not (spec.motion or "").strip():
        p.append("say what happens - the motion line is empty")
    if not (0.5 <= float(spec.seconds) <= max_seconds):
        p.append(f"length must be between 0.5 and {max_seconds:g} seconds")
    if spec.quality not in QUALITIES:
        p.append(f"quality must be one of {', '.join(QUALITIES)}")
    if not (1 <= int(spec.takes) <= 6):
        p.append("takes must be 1 to 6")
    kind = (spec.source or {}).get("kind")
    if kind == "keeper":
        if not (spec.source.get("path") and Path(spec.source["path"]).is_file()):
            p.append("the keeper is not on disk")
    elif kind == "still":
        if not (spec.source.get("outfit") or "").strip():
            p.append("the new still needs an outfit line")
        if spec.source.get("framing", "waist") not in FRAMINGS:
            p.append(f"framing must be one of {', '.join(FRAMINGS)}")
    else:
        p.append("pick a keeper or describe a new still")
    return p


def legs_for(seconds: float, leg_cap_s: float) -> list[float]:
    """Equal legs, each at or under the cap: 8 s at a 6 s cap is two legs of 4,
    never a 6 and a 2 - the short leg would read as a different pace."""
    import math  # noqa: PLC0415

    seconds = float(seconds)
    n = max(1, math.ceil(seconds / leg_cap_s - 1e-9))
    return [round(seconds / n, 2)] * n


def leg_cap_seconds(cfg: dict) -> float:
    v = cfg["video"]
    return (int(v.get("max_frames", 81)) - 1) / int(v["fps"])


def estimate_seconds(spec: VideoSpec) -> float:
    rate = QUALITIES[spec.quality][1]
    still = STILL_SECONDS if (spec.source or {}).get("kind") == "still" else 0.0
    return still + rate * float(spec.seconds) * int(spec.takes)


def ffmpeg_exe(cfg: dict | None = None) -> str | None:
    """ffmpeg on PATH, else [video].ffmpeg from config, else the one copy this
    machine is known to have. None when there is none - the job must fail at
    the guard, not after an hour of legs."""
    cand = [shutil.which("ffmpeg"), ((cfg or {}).get("video") or {}).get("ffmpeg"),
            r"C:\ProgramData\HP\LCDDisplayHelper\bin\ffmpeg.exe"]
    for c in cand:
        if c and Path(c).is_file():
            return str(c)
    return None


# --- the still ---------------------------------------------------------------

def normalize_source(src: Path, dest: Path, width: int, height: int) -> tuple[int, int]:
    """Resize and centre-crop the still to the Wan bucket, saved as PNG. A still
    renders at the training bucket (1024x1536) so her face keeps its pixels, and
    comes DOWN to the video bucket here."""
    from PIL import Image  # noqa: PLC0415

    img = Image.open(src).convert("RGB")
    scale = max(width / img.width, height / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - width) // 2, (img.height - height) // 2
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.crop((left, top, left + width, top + height)).save(dest)
    return width, height


def still_slot(spec: VideoSpec) -> dict:
    """The one-off slot the still renders through `shot_prompt`: a standing
    portrait, her outfit and hair from the spec, facing the camera."""
    s = spec.source
    return {"id": "still", "look": 1, "category": "casual", "pose": "standing", "turn": "front",
            "expression": "closed-lip", "outfit": s.get("outfit", ""),
            "hair": s.get("hair") or "her hair worn loose", "shoes": True,
            "framing_natural": FRAMINGS.get(s.get("framing", "waist"), FRAMINGS["waist"]),
            "setting": s.get("setting") or ""}


# --- the legs ---------------------------------------------------------------

def extract_last_frame(video: Path, dest: Path, *, ffmpeg: str, run=subprocess.run) -> None:
    """The reference's ffmpeg idiom: decode the final second with -update so the
    last frame wins."""
    run([ffmpeg, "-y", "-loglevel", "error", "-sseof", "-1", "-i", str(video),
         "-update", "1", "-frames:v", "9999", str(dest)],
        check=True, capture_output=True, text=True)
    if not dest.exists():
        raise RuntimeError(f"ffmpeg produced no last frame from {video}")


def color_match(frame: Path, reference: Path, dest: Path) -> None:
    """LAB mean/std transfer of `frame` toward `reference`. The anchor is always
    the ORIGINAL source, never the previous leg: leg-to-leg matching still lets
    the warm, saturated drift compound."""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    f = cv2.imread(str(frame)).astype(np.float32)
    r = cv2.imread(str(reference)).astype(np.float32)
    f_lab = cv2.cvtColor(f / 255.0, cv2.COLOR_BGR2LAB)
    r_lab = cv2.cvtColor(r / 255.0, cv2.COLOR_BGR2LAB)
    out = np.empty_like(f_lab)
    for c in range(3):
        fm, fs = f_lab[:, :, c].mean(), f_lab[:, :, c].std()
        rm, rs = r_lab[:, :, c].mean(), r_lab[:, :, c].std()
        out[:, :, c] = (f_lab[:, :, c] - fm) * (rs / max(fs, 1e-6)) + rm
    bgr = cv2.cvtColor(out, cv2.COLOR_LAB2BGR)
    cv2.imwrite(str(dest), np.clip(bgr * 255.0, 0, 255).astype(np.uint8))


def stitch_args(legs: list[Path], dest: Path, fps: int, *, ffmpeg: str) -> list[str]:
    """One ffmpeg pass: drop frame 0 of every leg after the first (it is the
    previous leg's last frame again - keeping it stutters at each seam)."""
    args = [ffmpeg, "-y", "-loglevel", "error"]
    for leg in legs:
        args += ["-i", str(leg)]
    parts = []
    for i in range(len(legs)):
        sel = "null" if i == 0 else "select='gte(n,1)',setpts=N/FRAME_RATE/TB"
        parts.append(f"[{i}:v]{sel}[v{i}]")
    chain = "".join(f"[v{i}]" for i in range(len(legs)))
    parts.append(f"{chain}concat=n={len(legs)}:v=1:a=0[out]")
    return args + ["-filter_complex", ";".join(parts), "-map", "[out]",
                   "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(fps), str(dest)]


def stitch(legs: list[Path], dest: Path, fps: int, *, ffmpeg: str, run=subprocess.run) -> None:
    run(stitch_args(legs, dest, fps, ffmpeg=ffmpeg), check=True, capture_output=True, text=True)


def video_output(files: list[dict]) -> dict | None:
    """The clip among a prompt's outputs. The key varies by node and version
    (core SaveVideo lists under "images" with an animated flag, VHS under
    "gifs"), so pick by extension, never by key."""
    for f in files:
        if str(f.get("filename", "")).lower().endswith((".mp4", ".webm", ".mov")):
            return f
    return None


def render_take(cfg: dict, client, spec: VideoSpec, source_png: Path, out_dir: Path, *,
                take: int, seed: int, log=print) -> dict:
    """One take: every leg through ComfyUI, chained, stitched. Returns the record."""
    from .render.passes import build_video_workflow, snap_frames  # noqa: PLC0415

    v = cfg["video"]
    fps = int(v["fps"])
    ff = ffmpeg_exe(cfg)
    legs = legs_for(spec.seconds, leg_cap_seconds(cfg))
    if len(legs) > 1 and not ff:
        raise RuntimeError("a chained clip needs ffmpeg and there is none on this machine")
    width, height = int(v["width"]), int(v["height"])
    leg_dir = out_dir / "_legs"
    start = source_png
    leg_files: list[Path] = []
    record = {"take": take, "seed": seed, "legs": [], "fps": fps, "width": width, "height": height,
              "quality": spec.quality, "motion": spec.motion, "pacing": PACING}
    for i, secs in enumerate(legs, start=1):
        t0 = time.monotonic()
        uploaded = client.upload_image(start)
        positive = f"{spec.motion.strip().rstrip('.')}. {PACING}."
        wf, settings = build_video_workflow(
            cfg, spec.character, positive=positive, negative=NEGATIVE, image_name=uploaded,
            seed=seed + i, render_pass=spec.quality, duration_s=secs, width=width, height=height)
        files = client.outputs(client.wait(client.submit(wf), timeout_s=4 * 3600))
        clip = video_output(files)
        if clip is None:
            raise RuntimeError(f"take {take} leg {i}: ComfyUI returned no video file")
        if len(legs) == 1:
            leg_path = out_dir / f"take_{take:02d}.mp4"
        else:
            leg_dir.mkdir(exist_ok=True)
            leg_path = leg_dir / f"take_{take:02d}_leg_{i:02d}.mp4"
        client.fetch(clip, leg_path)
        leg_files.append(leg_path)
        record["legs"].append({"leg": i, "seconds": secs, "frames": settings["LENGTH"],
                               "seed": seed + i, "file": str(leg_path),
                               "render_s": round(time.monotonic() - t0, 1)})
        log(f"  take {take} leg {i}/{len(legs)}: {settings['LENGTH']} frames in "
            f"{time.monotonic() - t0:.0f}s")
        if i < len(legs):
            raw = leg_dir / f"take_{take:02d}_leg_{i:02d}_last.png"
            matched = leg_dir / f"take_{take:02d}_leg_{i + 1:02d}_start.png"
            extract_last_frame(leg_path, raw, ffmpeg=ff)
            color_match(raw, source_png, matched)
            start = matched
    final = out_dir / f"take_{take:02d}.mp4"
    if len(leg_files) > 1:
        stitch(leg_files, final, fps, ffmpeg=ff)
    total = sum(lg["frames"] for lg in record["legs"]) - (len(leg_files) - 1)
    record["file"] = str(final)
    record["seconds"] = round(total / fps, 2)
    final.with_suffix(".json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    return record


# --- speech: the still talks ---------------------------------------------------------

#: Wan2.2-S2V's own recipe (the ComfyUI template, 2026-10-14): 16 fps, 77-frame
#: chunks, 20 steps at cfg 6. One pass is allowed up to 121 frames here, the cap
#: the September selfie plan settled on before RAM ran out; longer needs chained
#: chunks through WanSoundImageToVideoExtend, not built yet. 720x1280 is the
#: model's 720p portrait bucket, not the I2V 1024x1280.
S2V = {"fps": 16, "chunk": 77, "max_frames": 121, "width": 720, "height": 1280,
       "steps": 20, "cfg": 6.0, "shift": 8.0,
       "pacing": ("she speaks at an unhurried, even pace, her head and shoulders moving gently "
                  "and only a little, a steady camera")}


def speech_frames(seconds: float, *, fps: int = S2V["fps"], max_frames: int = S2V["max_frames"]) -> int | None:
    """Frames that COVER the line, snapped UP to 4n+1: the clip must run as long
    as she talks (the first selfie pass asked for 6 s against 3.3 s of audio and
    would have been half a clip of silent staring). None when one pass cannot."""
    import math  # noqa: PLC0415

    n = math.ceil(float(seconds) * fps) + 1          # frames, so (n-1)/fps >= seconds
    n = max(5, n + ((4 - (n - 1) % 4) % 4))
    return n if n <= max_frames else None


def s2v_workflow(cfg: dict, *, positive: str, negative: str, image_name: str, audio_name: str,
                 frames: int, seed: int, prefix: str, steps: int | None = None,
                 cfg_scale: float | None = None) -> tuple[dict, dict]:
    """The S2V graph: still + wav in, an mp4 WITH the voice out (the audio is
    wired into CreateVideo). Returns (nodes, settings) like the I2V builder."""
    from .config import workflows_dir  # noqa: PLC0415
    from .render.workflow import load_template, substitute  # noqa: PLC0415

    m = cfg["models"]
    settings = {"UNET": m["wan_s2v_fp8"], "UMT5": m["umt5"], "VAE": m["wan_vae"],
                "AUDIO_ENCODER": m["wan_audio_encoder"], "SHIFT": S2V["shift"],
                "POSITIVE": positive, "NEGATIVE": negative, "IMAGE": image_name, "AUDIO": audio_name,
                "WIDTH": S2V["width"], "HEIGHT": S2V["height"], "LENGTH": int(frames), "SEED": int(seed),
                "STEPS": int(steps or S2V["steps"]), "CFG": float(cfg_scale or S2V["cfg"]),
                "FPS": float(S2V["fps"]), "PREFIX": prefix}
    return substitute(load_template(workflows_dir(cfg), "wan22_s2v"), settings), settings


# --- what the tab shows ---------------------------------------------------------

def keepers(judge_root: Path, character: str, *, limit: int = 120) -> list[dict]:
    """Her judged keepers, newest first: every item he marked keep in a set
    written for her, that is still on disk. The judge sets are the one record
    of what he kept, whatever folder the file has since moved to. The newest
    120 by when the file was made (Jeremy, 2026-10-28: 60 is not enough "when
    I'm generating a TON of pics of characters")."""
    out: list[dict] = []
    sets_dir = judge_root / "sets"
    for sp in sorted(sets_dir.glob("*.json")) if sets_dir.is_dir() else []:
        try:
            s = json.loads(sp.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if (s.get("meta") or {}).get("character") != character or s.get("mode") == "pair":
            continue
        vp = judge_root / "verdicts" / f"{s['id']}.json"
        if not vp.is_file():
            continue
        v = json.loads(vp.read_text(encoding="utf-8"))
        for it in s["items"]:
            p = Path(it["path"])
            if v.get(it["id"]) == "keep" and p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                out.append({"path": str(p), "set": s["id"], "title": s.get("title", s["id"]),
                            "item": it["id"], "mtime": p.stat().st_mtime})
    out.sort(key=lambda r: -r["mtime"])
    seen: set[str] = set()
    uniq = []
    for r in out:
        if r["path"] not in seen:
            seen.add(r["path"]); uniq.append(r)
    return uniq[:limit]


def clips(library: Path, character: str) -> list[dict]:
    """Her video sets, newest first, with every take that finished."""
    home = library / character
    out = []
    for d in sorted(home.glob("*_video_*"), reverse=True) if home.is_dir() else []:
        if not d.is_dir():
            continue
        spec = {}
        sp = d / "spec.json"
        if sp.is_file():
            try:
                spec = json.loads(sp.read_text(encoding="utf-8"))
            except ValueError:
                spec = {}
        takes = []
        # a set from before this tab (jojo's September clips) has no spec and no
        # take_ files: every mp4 in it is a clip, and it is done
        files = sorted(d.glob("take_*.mp4")) if spec else sorted(d.glob("*.mp4"))
        for mp4 in files:
            rec = {}
            if mp4.with_suffix(".json").is_file():
                try:
                    rec = json.loads(mp4.with_suffix(".json").read_text(encoding="utf-8"))
                except ValueError:
                    rec = {}
            takes.append({"file": str(mp4), "seconds": rec.get("seconds"), "seed": rec.get("seed"),
                          "legs": len(rec.get("legs") or []), "bytes": mp4.stat().st_size})
        out.append({"folder": str(d), "name": d.name, "date": d.name[:10], "spec": spec,
                    "source": str(d / "source_src.png") if (d / "source_src.png").is_file() else None,
                    "takes": takes,
                    "done": not spec or (bool(takes) and len(takes) >= int(spec.get("takes") or 1))})
    return out


def spec_path(outputs: Path, spec: VideoSpec) -> Path:
    d = outputs / "video-specs"
    d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return d / f"{spec.character}_{stamp}_{os.getpid()}.json"


def write_spec(path: Path, spec: VideoSpec) -> Path:
    path.write_text(json.dumps(asdict(spec), indent=1, ensure_ascii=False), encoding="utf-8")
    return path
