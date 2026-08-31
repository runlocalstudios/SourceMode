"""Sheet-job render adapter: bootstrap/sheet.py calls client.render_sheet_job.

Wraps ComfyUIClient with the Qwen-Image-Edit workflow: uploads the character's
canonical reference once, builds one edit workflow per job, submits, waits,
fetches the output PNG to the requested path, and writes a provenance sidecar.
Seeds are deterministic: seed_base + job index.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from ..source import CharacterSource
from .client import ComfyUIClient
from .passes import build_edit_workflow, loras_summary, models_summary
from .sidecar import write_sidecar


class SheetRenderer:
    def __init__(
        self,
        cfg: dict,
        characters_root: Path,
        *,
        client: ComfyUIClient | None = None,
        render_pass: str = "final",
        seed_base: int = 1000,
        log=print,
    ):
        self.cfg = cfg
        self.characters_root = Path(characters_root)
        self.client = client or ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
        self.render_pass = render_pass
        self.seed_base = seed_base
        self.log = log
        self._uploaded: dict[str, str] = {}  # character_id -> server-side image name
        self._job_index = 0

    def _reference_name(self, source: CharacterSource) -> str:
        if source.character_id not in self._uploaded:
            ref_rel = source.reference_images[0]
            ref_path = self.characters_root / source.character_id / ref_rel
            self._uploaded[source.character_id] = self.client.upload_image(ref_path)
        return self._uploaded[source.character_id]

    def render_sheet_job(self, source: CharacterSource, job: dict, dest: Path) -> dict | None:
        """Render one sheet job; returns a manifest entry dict, or None on failure."""
        seed = self.seed_base + self._job_index
        self._job_index += 1
        workflow, settings = build_edit_workflow(
            self.cfg,
            source,
            instruction=job["instruction"],
            negative=source.negative_block,
            image_name=self._reference_name(source),
            seed=seed,
            render_pass=self.render_pass,
            filename_prefix=f"sourcemode/{source.character_id}_sheet/{job['slug']}",
        )
        started = time.monotonic()
        try:
            prompt_id = self.client.submit(workflow)
            entry = self.client.wait(prompt_id)
            files = self.client.outputs(entry)
            if not files:
                self.log(f"no output files for {job['slug']} (prompt {prompt_id})")
                return None
            self.client.fetch(files[0], Path(dest))
        except Exception as err:  # noqa: BLE001 — one failed job must not kill the sheet
            self.log(f"render error for {job['slug']}: {err}")
            return None
        elapsed = time.monotonic() - started
        prompt_hash = hashlib.sha256(job["instruction"].encode("utf-8")).hexdigest()[:16]
        write_sidecar(
            Path(dest),
            source_version=source.version,
            prompt_hash=prompt_hash,
            seed=seed,
            models=models_summary(settings),
            loras=loras_summary(settings),
            render_pass=self.render_pass,
            settings={"kind": "sheet", "slug": job["slug"]},
        )
        return {
            "slug": job["slug"],
            "file": Path(dest).name,
            "seed": seed,
            "source_version": source.version,
            "prompt_hash": prompt_hash,
            "render_pass": self.render_pass,
            "seconds": round(elapsed, 1),
        }
