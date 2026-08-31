"""Scene decomposition: brief -> list[ShotSpec].

RuleBasedDecomposer is deterministic (sentence/beat split + keyword mapping).
Qwen3Decomposer posts to a local OpenAI-compatible endpoint (Ollama/LM Studio)
and is dry-run testable via an injectable transport.
"""

from __future__ import annotations

import json
import re
from typing import Callable, Protocol

from .spec import CAMERA_MOVES, ShotSpec

QWEN3_SYSTEM_PROMPT = (
    "You are a cinematographer breaking a plain-English scene into a shot list. "
    "Output ONLY JSON: a list of shots with fields idx, shot_size (ECU/CU/MCU/MS/WS/EWS), "
    "lens (mm), camera_move (one of the standard terms), motion (what the character does), "
    "speed (slowly/steadily/briskly/rapidly), emotion, environment, lighting, grade, "
    "duration_s (max 8). Never describe the character's face or body features — identity "
    "comes from a trained model. Keep each shot a single action."
)


class Decomposer(Protocol):
    def decompose(self, brief: str) -> list[ShotSpec]: ...


_SPEED_WORDS = {
    "slowly": "slowly", "slow": "slowly", "crawl": "slowly",
    "briskly": "briskly", "brisk": "briskly", "quickly": "briskly", "hurried": "briskly",
    "rapidly": "rapidly", "sprint": "rapidly", "runs": "rapidly", "dashes": "rapidly",
}

_CAMERA_KEYWORDS = [
    ("tracks", "tracking"), ("tracking", "tracking"), ("follows", "tracking"),
    ("pans", "pan"), ("pan ", "pan"),
    ("tilts", "tilt"), ("tilt ", "tilt"),
    ("dollies in", "dolly in"), ("dolly in", "dolly in"),
    ("dollies out", "dolly out"), ("dolly out", "dolly out"), ("pulls back", "dolly out"),
    ("orbits", "orbital arc"), ("orbital", "orbital arc"), ("circles", "orbital arc"),
    ("swings around", "orbital arc"), ("swings", "orbital arc"),
    ("crane", "crane"),
    ("push-in", "push-in"), ("pushes in", "push-in"), ("push in", "push-in"),
    ("whip-pan", "whip-pan"), ("whip pan", "whip-pan"),
]

# The camera clause: "…, the camera tracks her from behind then swings around".
# Leading connectors/articles are part of the clause so stripping it from the
# motion text never leaves a dangling "the"/"as"/"and".
_CAMERA_CLAUSE_RE = re.compile(r"(?:\b(?:the|a|an|as|while|and|then)\s+)*\bcamera\b[^,.;]*", re.I)
# Two camera phases joined by "then" become two shots — one move per shot is
# the only thing Wan I2V executes reliably.
_PHASE_SPLIT_RE = re.compile(r"\b(?:and\s+)?then\b", re.I)
# Connectors/prepositions left dangling at the end of the motion text after
# the camera clause was cut out ("…smiles at the" -> "…smiles").
_DANGLING_TAIL_RE = re.compile(
    r"(?:\s*,)?\s+(?:and|then|the|a|an|as|while|at|to|toward|towards|from|into|of|with)\s*$", re.I
)


def _camera_moves(beat: str, low: str) -> list[str]:
    """Camera moves for a beat: one per 'then'-joined phase of its camera
    clause, else a whole-beat keyword scan, else static."""
    clause = _CAMERA_CLAUSE_RE.search(beat)
    moves: list[str] = []
    if clause:
        for phase in _PHASE_SPLIT_RE.split(clause.group(0)):
            phase_low = phase.lower()
            for kw, move in _CAMERA_KEYWORDS:
                if kw in phase_low:
                    moves.append(move)
                    break
    if not moves:
        for kw, move in _CAMERA_KEYWORDS:
            if kw in low:
                moves.append(move)
                break
    return moves or ["static"]

_EMOTION_WORDS = (
    "worried", "anxious", "calm", "happy", "joyful", "sad", "angry", "furious",
    "afraid", "scared", "determined", "curious", "tired", "excited", "tense",
    "relieved", "confident", "melancholy", "serene", "nervous",
)

_ENVIRONMENT_HINTS = [
    (re.compile(r"\b(?:in|into|through|inside|at|across|along|down|around)\s+(?:a|an|the)\s+([^,.;]+)", re.I), 1),
]


def _split_beats(brief: str) -> list[str]:
    """Split a brief into beats: one per sentence (default one shot per sentence)."""
    parts = re.split(r"(?<=[.!?;])\s+", brief.strip())
    return [p.strip().rstrip(".!?;") for p in parts if p.strip()]


class RuleBasedDecomposer:
    """Deterministic: one shot per sentence/beat, keyword-mapped fields, 8s cap."""

    def decompose(self, brief: str) -> list[ShotSpec]:
        beats = _split_beats(brief)
        shots: list[ShotSpec] = []
        idx = 0
        for beat in beats:
            low = beat.lower()

            speed = "steadily"
            matched_speed_word = None
            for word, mapped in _SPEED_WORDS.items():
                if word in low:
                    speed = mapped
                    matched_speed_word = word
                    break

            moves = _camera_moves(beat, low)

            emotion = "neutral"
            for e in _EMOTION_WORDS:
                if re.search(rf"\b{e}\b", low):
                    emotion = e
                    break

            environment = "the scene"
            for pattern, group in _ENVIRONMENT_HINTS:
                m = pattern.search(beat)
                if m:
                    environment = m.group(group).strip()
                    break

            # Strip camera directions from the motion text so the two can't
            # carry contradictory camera terms; strip the detected speed and
            # emotion words so the template doesn't restate them; then clean
            # any connector left dangling where the camera clause was cut.
            motion = _CAMERA_CLAUSE_RE.sub("", beat)
            if matched_speed_word:
                motion = re.sub(rf"\b{re.escape(matched_speed_word)}\b", "", motion, flags=re.I)
            if emotion != "neutral":
                motion = re.sub(rf",?\s*\b{re.escape(emotion)}\b", "", motion, flags=re.I)
            motion = re.sub(r"\s{2,}", " ", motion).strip(" ,")
            while True:
                cleaned = _DANGLING_TAIL_RE.sub("", motion)
                if cleaned == motion:
                    break
                motion = cleaned
            motion = motion.strip(" ,")
            if not motion:
                motion = beat

            # One shot per camera phase; a split beat gets shorter shots.
            duration = (
                min(6.0, 4.0 + len(beat) / 80.0) if len(moves) > 1
                else min(8.0, 4.0 + len(beat) / 40.0)
            )
            for camera_move in moves:
                shots.append(
                    ShotSpec(
                        idx=idx,
                        shot_size="MS" if camera_move != "static" else "MCU",
                        lens=35,
                        camera_move=camera_move,
                        motion=motion,
                        speed=speed,
                        emotion=emotion,
                        environment=environment,
                        duration_s=duration,
                    )
                )
                idx += 1
        return shots


class Qwen3Decomposer:
    """Posts the brief to a local OpenAI-compatible chat endpoint.

    `transport` is a callable (url, payload_dict) -> response_dict, injectable
    for tests; the default uses requests.
    """

    def __init__(self, url: str, model: str = "qwen3", transport: Callable[[str, dict], dict] | None = None):
        self.url = url.rstrip("/")
        self.model = model
        self.transport = transport or self._http_transport

    @staticmethod
    def _http_transport(url: str, payload: dict) -> dict:
        import requests  # noqa: PLC0415

        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()

    def decompose(self, brief: str) -> list[ShotSpec]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": QWEN3_SYSTEM_PROMPT},
                {"role": "user", "content": brief},
            ],
            "temperature": 0.2,
        }
        response = self.transport(f"{self.url}/chat/completions", payload)
        content = response["choices"][0]["message"]["content"]
        data = _extract_json(content)
        shots = []
        for i, item in enumerate(data):
            item.setdefault("idx", i)
            item["duration_s"] = min(float(item.get("duration_s", 5.0)), 8.0)
            if item.get("camera_move") not in CAMERA_MOVES:
                item["camera_move"] = "static"
            shots.append(ShotSpec.model_validate(item))
        return shots


def _extract_json(content: str) -> list[dict]:
    """Pull the first JSON array out of a model response (tolerates code fences)."""
    content = content.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", content, re.S)
    if fence:
        content = fence.group(1).strip()
    start = content.find("[")
    end = content.rfind("]")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON array in decomposer response: {content[:200]!r}")
    return json.loads(content[start : end + 1])
