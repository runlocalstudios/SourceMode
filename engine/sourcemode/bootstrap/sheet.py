"""Bootstrap a character sheet dataset via Qwen-Image-Edit jobs.

Builds the job list from sheet_edit_prompts, submits via the render client
(or prints in dry-run), writes images + caption .txt files to
characters/<id>/dataset/, then — if gates are enabled and available — scores
each image and moves drifters below threshold to dataset/_rejected/.
Gates annotate; the move-to-_rejected only happens when scoring actually ran.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..gates.base import Scorer
from ..prompts.templates import sheet_edit_prompts
from ..source import CharacterSource


def bootstrap_sheet(
    cfg: dict,
    source: CharacterSource,
    characters_root: Path,
    *,
    client=None,
    scorer: Scorer | None = None,
    dry_run: bool = False,
    gates_enabled: bool = True,
    log=print,
) -> dict:
    jobs = sheet_edit_prompts(source)
    char_dir = characters_root / source.character_id
    dataset_dir = char_dir / "dataset"
    rejected_dir = dataset_dir / "_rejected"

    if dry_run:
        for job in jobs:
            log(f"[dry-run] {job['slug']}: {job['instruction']}")
        return {"jobs": len(jobs), "rendered": 0, "rejected": 0, "dry_run": True}

    if client is None:
        raise ValueError("a render client is required unless --dry-run")

    dataset_dir.mkdir(parents=True, exist_ok=True)
    rendered = 0
    rejected = 0
    for job in jobs:
        image_path = dataset_dir / f"{job['slug']}.png"
        caption_path = dataset_dir / f"{job['slug']}.txt"
        result = client.render_sheet_job(source, job, image_path)
        if not result:
            log(f"render failed for {job['slug']}, skipping")
            continue
        caption_path.write_text(job["caption"] + "\n", encoding="utf-8")
        rendered += 1

        if gates_enabled and scorer is not None:
            gate = scorer.score(image_path, source)
            if gate.score is not None and gate.passed is False:
                rejected_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(image_path), rejected_dir / image_path.name)
                shutil.move(str(caption_path), rejected_dir / caption_path.name)
                rejected += 1
                log(f"rejected {job['slug']} (score {gate.score:.3f} < threshold)")

    return {"jobs": len(jobs), "rendered": rendered, "rejected": rejected, "dry_run": False}
