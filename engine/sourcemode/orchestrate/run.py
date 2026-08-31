"""End-to-end scene run:

compile -> per shot: keyframe render (N candidates, pick best identity score if
available, else first) -> video render -> video gate score -> sidecar ->
results.yaml. --dry-run writes the fully substituted workflow JSONs and never
POSTs. Gates annotate; they never block.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from ..gates.base import Scorer
from ..gates.video import score_video
from ..prompts.compile import compile_scene, scene_slug, write_scene
from ..prompts.decompose import Decomposer
from ..render.passes import (
    build_keyframe_workflow,
    build_video_workflow,
    loras_summary,
    models_summary,
)
from ..render.sidecar import write_sidecar
from ..source import CharacterSource


def _render(client, workflow: dict, dest: Path) -> Path | None:
    prompt_id = client.submit(workflow)
    entry = client.wait(prompt_id)
    files = client.outputs(entry)
    if not files:
        return None
    return client.fetch(files[0], dest)


def run_scene(
    cfg: dict,
    source: CharacterSource,
    characters_root: Path,
    outputs_root: Path,
    brief: str,
    decomposer: Decomposer,
    *,
    render_pass: str = "draft",
    client=None,
    scorer: Scorer | None = None,
    dry_run: bool = False,
    gates_enabled: bool = True,
    candidates: int = 4,
    seed: int = 1234,
    log=print,
) -> dict:
    scene = compile_scene(source, brief, decomposer)
    slug = scene_slug(brief)
    scene_path = write_scene(scene, outputs_root, slug)
    scene_dir = scene_path.parent
    log(f"scene compiled -> {scene_path} ({len(scene['shots'])} shots)")

    if not dry_run and client is None:
        raise ValueError("a render client is required unless --dry-run")

    results = {"scene": str(scene_path), "pass": render_pass, "dry_run": dry_run, "shots": []}

    for shot in scene["shots"]:
        idx = shot["spec"]["idx"]
        shot_dir = scene_dir / f"shot_{idx:02d}"
        shot_dir.mkdir(parents=True, exist_ok=True)
        shot_result: dict = {"idx": idx, "prompt_hash": shot["prompt_hash"], "candidates": []}

        # --- keyframes: N candidates, pick best identity score if available ---
        best: tuple[float, Path] | None = None
        first: Path | None = None
        for c in range(candidates):
            cand_seed = seed + idx * 100 + c
            workflow, settings = build_keyframe_workflow(
                cfg, source,
                positive=shot["keyframe_prompt"], negative=shot["negative"],
                seed=cand_seed, render_pass=render_pass,
            )
            if dry_run:
                (shot_dir / f"keyframe_c{c}.workflow.json").write_text(
                    json.dumps(workflow, indent=2), encoding="utf-8"
                )
                shot_result["candidates"].append({"seed": cand_seed, "score": None, "dry_run": True})
                continue

            dest = shot_dir / f"keyframe_c{c}.png"
            rendered = _render(client, workflow, dest)
            if rendered is None:
                shot_result["candidates"].append({"seed": cand_seed, "score": None, "failed": True})
                continue
            write_sidecar(
                rendered,
                source_version=source.version, prompt_hash=shot["prompt_hash"], seed=cand_seed,
                models=models_summary(settings), loras=loras_summary(settings),
                render_pass=render_pass, settings={"kind": "keyframe"},
            )
            if first is None:
                first = rendered
            score = None
            if gates_enabled and scorer is not None:
                gate = scorer.score(rendered, source)
                score = gate.score
            shot_result["candidates"].append({"seed": cand_seed, "score": score, "path": str(rendered)})
            if score is not None and (best is None or score > best[0]):
                best = (score, rendered)

        keyframe = best[1] if best else first
        shot_result["keyframe"] = str(keyframe) if keyframe else None

        # --- video ---
        if dry_run:
            workflow, settings = build_video_workflow(
                cfg, source,
                positive=shot["video_prompt"], negative=shot["negative"],
                image_name="keyframe_placeholder.png", seed=seed + idx,
                render_pass=render_pass, duration_s=shot["spec"]["duration_s"],
            )
            (shot_dir / "video.workflow.json").write_text(json.dumps(workflow, indent=2), encoding="utf-8")
            shot_result["video"] = None
        elif keyframe is None:
            shot_result["video"] = None
            shot_result["error"] = "no keyframe rendered"
        else:
            image_name = client.upload_image(keyframe)
            workflow, settings = build_video_workflow(
                cfg, source,
                positive=shot["video_prompt"], negative=shot["negative"],
                image_name=image_name, seed=seed + idx,
                render_pass=render_pass, duration_s=shot["spec"]["duration_s"],
            )
            # the wan22_i2v template ends in SaveVideo mp4-h264
            video_path = _render(client, workflow, shot_dir / "video.mp4")
            shot_result["video"] = str(video_path) if video_path else None
            if video_path:
                write_sidecar(
                    video_path,
                    source_version=source.version, prompt_hash=shot["prompt_hash"], seed=seed + idx,
                    models=models_summary(settings), loras=loras_summary(settings),
                    render_pass=render_pass, settings={"kind": "video", "length": settings["LENGTH"]},
                )
                if gates_enabled and scorer is not None:
                    gate = score_video(video_path, source, scorer, fps=float(cfg["video"]["fps"]))
                    shot_result["gate"] = {
                        "score": gate.score, "passed": gate.passed,
                        "details": gate.details, **gate.extras,
                    }

        results["shots"].append(shot_result)

    results_path = scene_dir / "results.yaml"
    results_path.write_text(yaml.safe_dump(results, sort_keys=False), encoding="utf-8")
    results["results_path"] = str(results_path)
    log(f"results -> {results_path}")
    return results
