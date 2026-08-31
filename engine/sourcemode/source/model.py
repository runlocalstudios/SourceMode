"""CharacterSource: the single source of truth for a character.

Ported from character-identity's IdentityPackage schema (see INVENTORY.md for
the field mapping). Strict models: unknown keys are a hard error, matching the
original StrictModel convention. The id regex and version pattern come from
character_identity.schemas (character.py / identity.py).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

CHARACTER_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"
VERSION_PATTERN = r"^v\d{3,}$"


class VoiceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_clip: str | None = Field(default=None, description="Canonical voice reference clip, relative to the character dir.")
    notes: str = ""


class LoraPaths(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_lora: str | None = None
    wan_low_noise: str | None = None
    wan_high_noise: str | None = None


class CharacterSource(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    character_id: str = Field(pattern=CHARACTER_ID_PATTERN)
    name: str = Field(min_length=1)
    version: str = Field(pattern=VERSION_PATTERN)
    trigger_token: str = Field(min_length=1, description='LoRA trigger, e.g. "gwen_ch".')
    invariants: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Features that must never drift (identity comes from the trained model, these are for QC — never injected into keyframe prompts).",
    )
    wardrobe_states: dict[str, str] = Field(
        default_factory=lambda: {"default": ""},
        description="Wardrobe state name -> trigger suffix.",
    )
    reference_images: list[str] = Field(default_factory=list, description="Paths relative to the character dir.")
    approved_sheet: list[str] = Field(default_factory=list, description="Approved sheet image paths, relative to the character dir.")
    identity_embedding_path: str | None = None
    identity_threshold: float | None = Field(
        default=None,
        description="Calibrated per-character threshold (mean - 2*std of approved-sheet pairwise similarity, floor 0.30). None = not calibrated.",
    )
    negative_block: str = ""
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    lora_paths: LoraPaths = Field(default_factory=LoraPaths)
    approved: bool = Field(default=False, description="Approved versions are immutable; bump to edit.")

    @field_validator("wardrobe_states")
    @classmethod
    def _default_state_present(cls, v: dict[str, str]) -> dict[str, str]:
        if "default" not in v:
            raise ValueError('wardrobe_states must contain a "default" state')
        return v

    def wardrobe_suffix(self, state: str = "default") -> str:
        if state not in self.wardrobe_states:
            raise KeyError(f"unknown wardrobe state {state!r} (have: {sorted(self.wardrobe_states)})")
        return self.wardrobe_states[state]

    def next_version(self) -> str:
        num = int(self.version[1:])
        return f"v{num + 1:03d}"
