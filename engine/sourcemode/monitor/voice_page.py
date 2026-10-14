"""Her voice, on the Characters tab: describe it, hear takes, pick one.

Jeremy, 2026-10-14: "There must be some way to actually create these from
scratch" - Parler-TTS makes a voice from a text description, Chatterbox then
speaks every line from the take he picks. The section lives on the
Characters page beside her LoRA and her wardrobe; these are its routes.

    GET  /voices/{char}            her record + every voice set with its takes
    POST /voices/{char}/make       {description, takes, name} -> ONE queued job
                                   (Parler takes, then the Chatterbox read of each)
    POST /voices/{char}/use        {reference, description?, seed?, model?} -> the record
    POST /voices/{char}/clear      forget the record (the files stay)
    GET  /voices/file?path=        a wav under the library or outputs/voice
"""

from __future__ import annotations

import json
import re
from pathlib import Path

#: a starting description in Parler's register; he edits it
TEMPLATE = ("A young woman with a warm, slightly breathy voice speaks at a relaxed, unhurried pace "
            "with a playful lilt. Her pitch is moderately high. ")


def make_command(engine_root: Path, set_dir: Path) -> list[str]:
    """Parler takes, then the Chatterbox read of each, as ONE job: two isolated
    uv environments because their transformers pins disagree (4.46 vs 5.2)."""
    uv = "uv"
    s1 = (f"& {uv} run --isolated --with parler-tts --with soundfile python "
          f"scripts/voice/make_voice_parler.py '{set_dir}'")
    s2 = (f"& {uv} run --isolated --with chatterbox-tts --with 'setuptools<81' --with soundfile python "
          f"scripts/voice/clone_check.py '{set_dir}'")
    return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
            f"{s1}; if ($LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}; {s2}; exit $LASTEXITCODE"]


def voice_router(cfg: dict):
    from fastapi import APIRouter, Body, HTTPException  # noqa: PLC0415
    from fastapi.responses import FileResponse  # noqa: PLC0415

    from ..config import ENGINE_ROOT, outputs_dir  # noqa: PLC0415
    from ..library import find_set, library_dir, write_set_json  # noqa: PLC0415
    from ..voice import record as R  # noqa: PLC0415

    r = APIRouter()

    def _char(char: str) -> str:
        c = (char or "").strip().lower()
        if not re.match(r"^[a-z][a-z0-9_]{0,31}$", c):
            raise HTTPException(400, "a character id is required")
        return c

    def _inside(p: str, roots: list[Path]) -> Path:
        try:
            q = Path(p).resolve()
        except OSError as exc:
            raise HTTPException(404) from exc
        for root in roots:
            try:
                q.relative_to(root.resolve())
                if q.is_file():
                    return q
            except ValueError:
                continue
        raise HTTPException(404)

    # declared before /voices/{char}, or "file" would be read as a character
    @r.get("/voices/file")
    def _file(path: str):
        p = _inside(path, [library_dir(cfg), outputs_dir(cfg) / "voice"])
        return FileResponse(p, media_type="audio/wav")

    @r.get("/voices/{char}")
    def _get(char: str) -> dict:
        c = _char(char)
        return {"character": c, "voice": R.get(c), "sets": R.takes(library_dir(cfg), c),
                "template": TEMPLATE, "reference_text": R.REFERENCE_TEXT, "check_line": R.CHECK_LINE}

    @r.post("/voices/{char}/make")
    def _make(char: str, body: dict = Body(default={})) -> dict:
        from ..gpu import queue as q  # noqa: PLC0415
        from ..gpu.preflight import preflight  # noqa: PLC0415

        c = _char(char)
        desc = str(body.get("description") or "").strip()
        if len(desc) < 12:
            raise HTTPException(400, "describe the voice - a sentence or two, in Parler's register")
        try:
            takes = int(body.get("takes") or 3)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "takes must be a number") from exc
        if not 1 <= takes <= 6:
            raise HTTPException(400, "takes must be 1 to 6")
        name = str(body.get("name") or "").strip() or re.sub(r"[^a-z0-9]+", " ", desc.lower()).strip()[:24]
        d = find_set(cfg, c, "voice", name, create=True)
        if (d / "spec.json").is_file() and any(d.glob("take_*.wav")):
            raise HTTPException(409, f"{d.name} already has takes - give this voice a new name")
        text = desc if desc.rstrip().endswith(R.QUALITY_TAIL.rstrip(".")) else f"{desc.rstrip()} {R.QUALITY_TAIL}"
        spec = {"character": c, "description": text, "text": R.REFERENCE_TEXT, "takes": takes,
                "seed": int(body.get("seed") or 1100), "model": "parler-tts/parler-tts-mini-v1",
                "check_line": R.CHECK_LINE, "exaggeration": 0.5, "cfg_weight": 0.4, "name": name}
        (d / "spec.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False), encoding="utf-8")
        write_set_json(d, character=c, kind="voice", name=name, date=d.name[:10], judge_sets=[])
        cmd = make_command(ENGINE_ROOT, d)
        out = outputs_dir(cfg)
        bad = preflight({"cmd": cmd, "cwd": str(ENGINE_ROOT)}, out)
        if bad:
            raise HTTPException(409, "would fail at once: " + "; ".join(bad))
        doc = q.load(q.queue_path(out))
        label = f"{c}:voice:{name}"
        dup = q.duplicate_of(doc, "voice", label)
        if dup:
            raise HTTPException(409, f"that voice is already {dup['status']} in the queue")
        job = q.add(doc, kind="voice", label=label, cmd=cmd, cwd=str(ENGINE_ROOT),
                    note=f"{takes} Parler take(s) + Chatterbox reads, CPU, from the Characters tab")
        q.save(q.queue_path(out), doc)
        return {"queued": job["id"], "set": str(d)}

    @r.post("/voices/{char}/use")
    def _use(char: str, body: dict = Body(default={})) -> dict:
        c = _char(char)
        ref = _inside(str(body.get("reference") or ""), [library_dir(cfg), outputs_dir(cfg) / "voice"])
        if ref.suffix.lower() != ".wav":
            raise HTTPException(400, "the reference must be a wav")
        meta = {}
        if ref.with_suffix(".json").is_file():
            try:
                meta = json.loads(ref.with_suffix(".json").read_text(encoding="utf-8"))
            except ValueError:
                meta = {}
        rec = R.set_voice(c, reference=ref, description=str(body.get("description") or meta.get("description") or ""),
                          model=str(body.get("model") or meta.get("model") or ""),
                          seed=body.get("seed", meta.get("seed")))
        return {"character": c, "voice": rec}

    @r.post("/voices/{char}/clear")
    def _clear(char: str) -> dict:
        c = _char(char)
        return {"character": c, "cleared": R.clear(c)}

    return r
