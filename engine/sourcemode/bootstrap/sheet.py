"""Bootstrap a character sheet dataset via Qwen-Image-Edit jobs.

Builds the job list from sheet_edit_prompts, submits via the render client
(or prints in dry-run), writes images + caption .txt files to
characters/<id>/dataset/ plus a manifest.json (per-image seed + provenance),
then — if gates are enabled and available — scores each image. In "gate" mode
drifters below threshold move to dataset/_rejected/; in "advisory" mode
(config gates.identity_mode) nothing moves, low scores are only flagged.
Gates annotate; the move only happens when scoring actually ran.
"""

from __future__ import annotations

import json
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

    advisory = cfg.get("gates", {}).get("identity_mode", "gate") == "advisory"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    rendered = 0
    rejected = 0
    flagged = 0
    for job in jobs:
        image_path = dataset_dir / f"{job['slug']}.png"
        caption_path = dataset_dir / f"{job['slug']}.txt"
        result = client.render_sheet_job(source, job, image_path)
        if not result:
            log(f"render failed for {job['slug']}, skipping")
            continue
        caption_path.write_text(job["caption"] + "\n", encoding="utf-8")
        rendered += 1
        entry = result if isinstance(result, dict) else {"slug": job["slug"], "file": image_path.name}
        manifest[job["slug"]] = entry

        if gates_enabled and scorer is not None:
            gate = scorer.score(image_path, source)
            if gate.score is not None:
                entry["identity_score"] = round(gate.score, 4)
            if gate.score is not None and gate.passed is False:
                if advisory:
                    flagged += 1
                    entry["flagged"] = True
                    log(f"flagged {job['slug']} (score {gate.score:.3f} < threshold; advisory mode, kept)")
                else:
                    rejected_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(image_path), rejected_dir / image_path.name)
                    shutil.move(str(caption_path), rejected_dir / caption_path.name)
                    rejected += 1
                    entry["rejected"] = True
                    log(f"rejected {job['slug']} (score {gate.score:.3f} < threshold)")

    (dataset_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return {"jobs": len(jobs), "rendered": rendered, "rejected": rejected, "flagged": flagged, "dry_run": False}
