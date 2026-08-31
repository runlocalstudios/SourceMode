"""ShotSpec: one shot of a scene, in standard cinematography vocabulary."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SHOT_SIZES = ("ECU", "CU", "MCU", "MS", "WS", "EWS")
CAMERA_MOVES = (
    "static",
    "pan",
    "tilt",
    "dolly in",
    "dolly out",
    "tracking",
    "orbital arc",
    "crane",
    "push-in",
    "whip-pan",
)
SPEEDS = ("slowly", "steadily", "briskly", "rapidly")

ShotSize = Literal["ECU", "CU", "MCU", "MS", "WS", "EWS"]
CameraMove = Literal[
    "static", "pan", "tilt", "dolly in", "dolly out", "tracking",
    "orbital arc", "crane", "push-in", "whip-pan",
]
Speed = Literal["slowly", "steadily", "briskly", "rapidly"]


class ShotSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idx: int = Field(ge=0)
    shot_size: ShotSize = "MS"
    lens: int = Field(default=35, gt=0, description="Focal length in mm.")
    camera_move: CameraMove = "static"
    motion: str = Field(min_length=1, description="What the character does.")
    speed: Speed = "steadily"
    emotion: str = "neutral"
    environment: str = Field(min_length=1)
    lighting: str = "natural light"
    grade: str = "neutral cinematic grade"
    duration_s: float = Field(default=5.0, gt=0, le=8.0)
    wardrobe_state: str = "default"
