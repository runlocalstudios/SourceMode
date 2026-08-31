"""Gate protocol. Gates are PURE SCORERS: (asset, source) -> score.

They annotate; they never block unless an explicit flag says so. Every gate
has a --no-gate bypass at the CLI and a config toggle ([gates] in config.toml).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..source import CharacterSource


@dataclass
class GateResult:
    score: float | None
    passed: bool | None
    details: str = ""
    extras: dict = field(default_factory=dict)


class Scorer(Protocol):
    def score(self, asset_path: Path, source: CharacterSource) -> GateResult: ...
