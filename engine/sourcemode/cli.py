"""`sourcemode` CLI (Typer).

Commands: doctor, source, gates, prompts, render, train, bootstrap, voice, run.
Every GPU-dependent path has --dry-run; every gate has --no-gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich import print as rprint

from .config import characters_dir, load_config, outputs_dir

app = typer.Typer(name="sourcemode", no_args_is_help=True, help="SourceMode pipeline engine.")
source_app = typer.Typer(no_args_is_help=True, help="CharacterSource management.")
gates_app = typer.Typer(no_args_is_help=True, help="Quality gates (pure scorers — annotate, never block).")
prompts_app = typer.Typer(no_args_is_help=True, help="Prompt compilation.")
render_app = typer.Typer(no_args_is_help=True, help="ComfyUI rendering.")
train_app = typer.Typer(no_args_is_help=True, help="LoRA training command builders + checkpoint selection.")
bootstrap_app = typer.Typer(no_args_is_help=True, help="Character-sheet dataset bootstrap.")
voice_app = typer.Typer(no_args_is_help=True, help="Voice synthesis (Chatterbox).")
pose_app = typer.Typer(no_args_is_help=True, help="Pose transfer: same character and outfit, new pose.")
app.add_typer(source_app, name="source")
app.add_typer(gates_app, name="gates")
app.add_typer(prompts_app, name="prompts")
app.add_typer(render_app, name="render")
app.add_typer(train_app, name="train")
app.add_typer(bootstrap_app, name="bootstrap")
app.add_typer(voice_app, name="voice")
app.add_typer(pose_app, name="pose")


def _ctx():
    cfg = load_config()
    return cfg, characters_dir(cfg)


def _load(character: str):
    from .source import load_source  # noqa: PLC0415

    cfg, chars = _ctx()
    return cfg, chars, load_source(chars, character)


def _scorer(cfg, chars):
    from .gates.identity import IdentityScorer  # noqa: PLC0415

    return IdentityScorer(chars)


def _decomposer(cfg, name: str):
    from .prompts.decompose import Qwen3Decomposer, RuleBasedDecomposer  # noqa: PLC0415

    if name == "qwen3":
        return Qwen3Decomposer(cfg["decomposer"]["qwen3_url"], cfg["decomposer"]["qwen3_model"])
    return RuleBasedDecomposer()


# --- top-level -------------------------------------------------------------


@app.command()
def doctor():
    """Check ComfyUI, models, musubi-tuner, InsightFace, GPU, ffmpeg."""
    from .doctor import print_doctor  # noqa: PLC0415

    cfg, _ = _ctx()
    print_doctor(cfg)


@app.command()
def run(
    character: str,
    brief: str = typer.Option(..., "--brief"),
    render_pass: str = typer.Option("draft", "--pass"),
    decomposer: str = typer.Option("rules", "--decomposer", help="rules|qwen3"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    no_gate: bool = typer.Option(False, "--no-gate"),
    candidates: int = typer.Option(4, "--candidates"),
    seed: int = typer.Option(1234, "--seed"),
    sync_db: bool = typer.Option(False, "--sync-db"),
    no_wan_lora: bool = typer.Option(False, "--no-wan-lora", help="A/B: render video without the Wan identity LoRA (keyframe LoRA still on)."),
):
    """Full pipeline: compile -> keyframes -> video -> gates -> results.yaml."""
    from .orchestrate.run import run_scene  # noqa: PLC0415

    cfg, chars, src = _load(character)
    if no_wan_lora:
        src = src.model_copy(
            update={"lora_paths": src.lora_paths.model_copy(update={"wan_low_noise": None, "wan_high_noise": None})}
        )
        rprint("[yellow]A/B mode:[/yellow] Wan identity LoRA disabled for this run")
    gates_enabled = cfg["gates"]["identity_enabled"] and not no_gate
    client = None
    if not dry_run:
        from .render.client import ComfyUIClient  # noqa: PLC0415

        client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
    results = run_scene(
        cfg, src, chars, outputs_dir(cfg), brief, _decomposer(cfg, decomposer),
        render_pass=render_pass, client=client,
        scorer=_scorer(cfg, chars) if gates_enabled else None,
        dry_run=dry_run, gates_enabled=gates_enabled,
        candidates=candidates, seed=seed,
    )
    if sync_db:
        from .orchestrate.db import sync_results  # noqa: PLC0415

        sync_results(src, brief, results)
    rprint(f"[green]done[/green] -> {results['results_path']}")


# --- source ----------------------------------------------------------------


@source_app.command("show")
def source_show(character: str):
    _, _, src = _load(character)
    rprint(json.dumps(src.model_dump(), indent=2))


@source_app.command("sync")
def source_sync(character: str):
    """Upsert the character + source JSON into Neon (DATABASE_URL_UNPOOLED)."""
    from .orchestrate.db import sync_character  # noqa: PLC0415

    _, _, src = _load(character)
    ok = sync_character(src, log=rprint)
    raise typer.Exit(0 if ok else 1)


@source_app.command("approve")
def source_approve(character: str):
    """Mark the current source version approved (immutable except operational fields)."""
    from .source import save_source  # noqa: PLC0415

    _, chars, src = _load(character)
    if src.approved:
        rprint(f"[yellow]{character} {src.version} is already approved[/yellow]")
        raise typer.Exit(0)
    save_source(chars, src.model_copy(update={"approved": True}))
    rprint(f"[green]{character} {src.version} approved[/green]")


@source_app.command("bump")
def source_bump(character: str):
    from .source import bump_version  # noqa: PLC0415

    _, chars = _ctx()
    bumped = bump_version(chars, character)
    rprint(f"[green]{character}[/green] bumped to {bumped.version} (unapproved)")


# --- gates -----------------------------------------------------------------


@gates_app.command("calibrate")
def gates_calibrate(
    character: str,
    negative: Path = typer.Option(None, "--negative", help="Image of a clearly-different face to check separation."),
):
    """Pairwise similarity over the approved sheet -> per-character threshold."""
    from .gates.identity import IdentityScorer, calibrate_identity_full  # noqa: PLC0415

    _, chars, src = _load(character)
    updated, stats = calibrate_identity_full(chars, src)

    names = [Path(f).name for f in stats["files"]]
    width = max(len(n) for n in names)
    rprint("[bold]pairwise cosine similarity[/bold]")
    header = " " * (width + 2) + "  ".join(f"{i:>6d}" for i in range(len(names)))
    rprint(header)
    for i, row in enumerate(stats["matrix"]):
        cells = "  ".join(f"{v:6.3f}" for v in row)
        rprint(f"{names[i]:<{width}} [{i}] {cells}")
    if stats["skipped"]:
        rprint(f"[yellow]no face found in: {stats['skipped']}[/yellow]")
    rprint(
        f"mean={stats['mean']} std={stats['std']} -> "
        f"[green]threshold={updated.identity_threshold}[/green] embedding={updated.identity_embedding_path}"
    )

    unreliable = stats["mean"] < 0.35
    if negative is not None:
        result = IdentityScorer(chars).score(negative, updated)
        if result.score is None:
            rprint(f"[yellow]negative check: {result.details or 'no score'}[/yellow]")
        else:
            margin = stats["mean"] - result.score
            separated = result.score < stats["mean"] - stats["std"]
            rprint(
                f"negative face similarity={result.score:.4f} "
                f"(intra mean {stats['mean']}, margin {margin:.4f}) -> "
                + ("[green]separated[/green]" if separated else "[red]NOT separated (within 1 std of positives)[/red]")
            )
            unreliable = unreliable or not separated
    if unreliable:
        rprint(
            "[red]scorer looks unreliable on this character's style[/red] — "
            "set gates.identity_mode = \"advisory\" in engine/config.toml"
        )


@gates_app.command("report")
def gates_report(
    directory: Path,
    character: str = typer.Option(..., "--character"),
    name: str = typer.Option(None, "--name", help="Output stem (default <character>_<dirname>)."),
):
    """Score every image in a folder -> CSV + sorted contact sheet in outputs/review/."""
    from .gates.report import report_directory  # noqa: PLC0415

    cfg, chars, src = _load(character)
    summary = report_directory(directory, src, _scorer(cfg, chars), outputs_dir(cfg) / "review", name=name)
    rprint(summary)


@gates_app.command("strip")
def gates_strip(
    video: Path,
    character: str = typer.Option(..., "--character"),
    out: Path = typer.Option(None, "--out", help="Default: <video dir>/<stem>_strip.png"),
    stride: int = typer.Option(12, "--stride"),
):
    """Frame strip PNG: every Nth frame with its identity score printed under it."""
    from .gates.strip import frame_strip  # noqa: PLC0415

    cfg, chars, src = _load(character)
    out = out or video.parent / f"{video.stem}_strip.png"
    stats = frame_strip(video, src, _scorer(cfg, chars), out, stride=stride, fps=float(cfg["video"]["fps"]))
    rprint(stats)


@gates_app.command("score")
def gates_score(
    asset: Path,
    character: str = typer.Option(..., "--character"),
    no_gate: bool = typer.Option(False, "--no-gate"),
    stride: int = typer.Option(None, "--stride", help="Video frame stride (default from config)."),
):
    """Score an image or video against the character's identity embedding."""
    cfg, chars, src = _load(character)
    if no_gate or not cfg["gates"]["identity_enabled"]:
        rprint("[yellow]gate bypassed[/yellow] (--no-gate or config toggle)")
        raise typer.Exit(0)
    scorer = _scorer(cfg, chars)
    if asset.suffix.lower() in {".mp4", ".webm", ".webp", ".mov", ".mkv", ".gif"}:
        from .gates.video import score_video  # noqa: PLC0415

        result = score_video(asset, src, scorer, stride=stride or cfg["gates"]["frame_stride"],
                             fps=float(cfg["video"]["fps"]))
    else:
        result = scorer.score(asset, src)
    rprint({"score": result.score, "passed": result.passed, "details": result.details, **result.extras})


# --- prompts ---------------------------------------------------------------


@prompts_app.command("compile")
def prompts_compile(
    character: str,
    brief: str = typer.Option(..., "--brief"),
    decomposer: str = typer.Option("rules", "--decomposer", help="rules|qwen3"),
):
    """Compile a brief into outputs/scenes/<slug>/scene.yaml."""
    from .prompts.compile import compile_scene, write_scene  # noqa: PLC0415

    cfg, chars, src = _load(character)
    scene = compile_scene(src, brief, _decomposer(cfg, decomposer))
    path = write_scene(scene, outputs_dir(cfg))
    rprint(f"[green]compiled[/green] {len(scene['shots'])} shots -> {path}")


# --- render ----------------------------------------------------------------


@render_app.command("shot")
def render_shot(
    scene_yaml: Path,
    idx: int = typer.Option(..., "--idx"),
    render_pass: str = typer.Option("draft", "--pass"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    image: str = typer.Option("keyframe_placeholder.png", "--image", help="ComfyUI input image name for I2V."),
    seed: int = typer.Option(1234, "--seed"),
):
    """Render one shot's video from a compiled scene YAML."""
    from .prompts.compile import load_scene  # noqa: PLC0415
    from .render.passes import build_video_workflow, loras_summary, models_summary  # noqa: PLC0415
    from .render.sidecar import write_sidecar  # noqa: PLC0415
    from .source import load_source  # noqa: PLC0415

    cfg, chars = _ctx()
    scene = load_scene(scene_yaml)
    src = load_source(chars, scene["character_id"])
    shots = [s for s in scene["shots"] if s["spec"]["idx"] == idx]
    if not shots:
        rprint(f"[red]no shot idx {idx} in {scene_yaml}[/red]")
        raise typer.Exit(2)
    shot = shots[0]
    workflow, settings = build_video_workflow(
        cfg, src, positive=shot["video_prompt"], negative=shot["negative"],
        image_name=image, seed=seed, render_pass=render_pass,
        duration_s=shot["spec"]["duration_s"],
    )
    if dry_run:
        rprint(json.dumps(workflow, indent=2))
        raise typer.Exit(0)
    from .render.client import ComfyUIClient  # noqa: PLC0415

    client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
    prompt_id = client.submit(workflow)
    entry = client.wait(prompt_id)
    files = client.outputs(entry)
    dest = Path(scene_yaml).parent / f"shot_{idx:02d}" / "video.mp4"
    out = client.fetch(files[0], dest) if files else None
    if out:
        write_sidecar(out, source_version=src.version, prompt_hash=shot["prompt_hash"], seed=seed,
                      models=models_summary(settings), loras=loras_summary(settings),
                      render_pass=render_pass, settings={"kind": "video"})
    rprint(f"rendered -> {out}")


@render_app.command("smoke")
def render_smoke(
    workflow: str = typer.Option(..., "--workflow", help="qwen_image_edit | qwen_image_t2i | wan22_i2v"),
    prompt: str = typer.Option(..., "--prompt"),
    character: str = typer.Option("gwen", "--character"),
    image: Path = typer.Option(None, "--image", help="Local input image (required for edit/i2v)."),
    negative: str = typer.Option(None, "--negative", help="Default: the character's negative_block."),
    render_pass: str = typer.Option("draft", "--pass"),
    seed: int = typer.Option(42, "--seed"),
    width: int = typer.Option(None, "--width"),
    height: int = typer.Option(None, "--height"),
    duration: float = typer.Option(2.0, "--duration", help="I2V only, seconds."),
    dry_run: bool = typer.Option(False, "--dry-run"),
    wan_low_lora: str = typer.Option(
        None, "--wan-low-lora",
        help="Override the wan_low_noise LoRA (ComfyUI-relative name) — checkpoint selection renders.",
    ),
    image_lora: str = typer.Option(
        None, "--image-lora",
        help="Override the image LoRA (ComfyUI-relative name) — checkpoint comparison renders.",
    ),
):
    """Small real render straight to outputs/smoke/, with timing."""
    import time  # noqa: PLC0415

    from .render.client import ComfyUIClient  # noqa: PLC0415
    from .render.passes import (  # noqa: PLC0415
        build_edit_workflow,
        build_keyframe_workflow,
        build_video_workflow,
        loras_summary,
        models_summary,
    )
    from .render.sidecar import write_sidecar  # noqa: PLC0415

    cfg, chars, src = _load(character)
    overrides = {}
    if wan_low_lora is not None:
        overrides["wan_low_noise"] = wan_low_lora
    if image_lora is not None:
        overrides["image_lora"] = image_lora
    if overrides:
        src = src.model_copy(update={"lora_paths": src.lora_paths.model_copy(update=overrides)})
    neg = negative if negative is not None else src.negative_block
    client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
    if not dry_run and not client.is_reachable():
        rprint("[red]ComfyUI is not reachable[/red] — start it with C:\\ComfyUI\\start.bat and retry")
        raise typer.Exit(2)

    image_name = "smoke_input.png"
    if image is not None and not dry_run:
        image_name = client.upload_image(image)

    if workflow == "qwen_image_edit":
        if image is None:
            rprint("[red]--image is required for qwen_image_edit[/red]")
            raise typer.Exit(2)
        nodes, settings = build_edit_workflow(
            cfg, src, instruction=prompt, negative=neg, image_name=image_name,
            seed=seed, render_pass=render_pass, filename_prefix="sourcemode/smoke_edit",
        )
    elif workflow == "qwen_image_t2i":
        nodes, settings = build_keyframe_workflow(
            cfg, src, positive=prompt, negative=neg, seed=seed, render_pass=render_pass,
            width=width or 1024, height=height or 1024,
        )
    elif workflow == "wan22_i2v":
        if image is None:
            rprint("[red]--image is required for wan22_i2v[/red]")
            raise typer.Exit(2)
        nodes, settings = build_video_workflow(
            cfg, src, positive=prompt, negative=neg, image_name=image_name,
            seed=seed, render_pass=render_pass, duration_s=duration,
            width=width, height=height,
        )
        nodes[next(k for k, v in nodes.items() if v["class_type"] == "SaveVideo")]["inputs"][
            "filename_prefix"
        ] = "sourcemode/smoke_video"
    else:
        rprint(f"[red]unknown workflow {workflow!r}[/red]")
        raise typer.Exit(2)

    if dry_run:
        rprint(json.dumps(nodes, indent=2))
        raise typer.Exit(0)

    started = time.monotonic()
    prompt_id = client.submit(nodes)
    entry = client.wait(prompt_id)
    files = client.outputs(entry)
    elapsed = time.monotonic() - started
    if not files:
        rprint(f"[red]no output files in history for prompt {prompt_id}[/red]")
        raise typer.Exit(1)
    smoke_dir = outputs_dir(cfg) / "smoke"
    fetched = []
    for desc in files:
        dest = smoke_dir / desc["filename"].replace("/", "_")
        client.fetch(desc, dest)
        fetched.append(dest)
    write_sidecar(
        fetched[0], source_version=src.version, prompt_hash="smoke", seed=seed,
        models=models_summary(settings), loras=loras_summary(settings),
        render_pass=render_pass, settings={"kind": "smoke", "workflow": workflow},
    )
    rprint(f"[green]smoke ok[/green] {workflow} in {elapsed:.1f}s -> " + ", ".join(str(p) for p in fetched))


# --- train -----------------------------------------------------------------


def _train_common(character: str, dataset: Path | None):
    cfg, chars, src = _load(character)
    dataset_dir = dataset or chars / src.character_id / "dataset"
    from .train.dataset import validate_captions  # noqa: PLC0415

    entries = validate_captions(dataset_dir, src.trigger_token)  # fails loudly
    rprint(f"[green]captions ok[/green] {len(entries)} images, trigger {src.trigger_token!r}")
    return cfg, chars, src, dataset_dir


def _print_plan(plan: dict) -> None:
    rprint(
        f"[bold]{plan['kind']}[/bold]: {plan['n_images']} images x {plan['num_repeats']} repeats = "
        f"{plan['steps_per_epoch']} steps/epoch x {plan['max_train_epochs']} epochs = {plan['total_steps']} steps"
    )
    rprint(f"[bold]dataset toml[/bold] -> {plan['dataset_toml_path']}\n{plan['dataset_toml']}")
    if "sample_prompts" in plan:
        rprint(f"[bold]sample prompts[/bold] -> {plan['sample_prompts_path']}\n{plan['sample_prompts']}")
    for cmd in plan["commands"]:
        rprint(" ".join(f'"{c}"' if " " in c else c for c in cmd))


def _run_plan(chars, src, plan, dataset_dir):
    from .train.run import execute_plan, write_manifest, write_plan_files  # noqa: PLC0415

    write_plan_files(plan)
    manifest = write_manifest(chars, src, plan, dataset_dir)
    rprint(f"[green]manifest[/green] -> {manifest}")
    execute_plan(plan, log=rprint)
    rprint(f"[green]training complete[/green] checkpoints in {plan['output_dir']}")


@train_app.command("image")
def train_image(
    character: str,
    dataset: Path = typer.Option(None, "--dataset", help="Default: characters/<id>/dataset."),
    output_dir: Path = typer.Option(None, "--output-dir", help="Default: outputs/training/<id>/lora_image."),
    epochs: int = typer.Option(None, "--epochs", help="Default: ~2500 total steps."),
    blocks_to_swap: int = typer.Option(0, "--blocks-to-swap", help="Retry with 16 on OOM."),
    dry_run: bool = typer.Option(True, "--dry-run/--run", help="--run executes (blocks until training ends)."),
    seed: int = typer.Option(42, "--seed"),
):
    """Qwen-Image identity LoRA via musubi-tuner: cache latents -> cache TE -> train."""
    from .train.image import build_image_lora_cmd  # noqa: PLC0415

    cfg, chars, src, dataset_dir = _train_common(character, dataset)
    out = output_dir or outputs_dir(cfg) / "training" / src.character_id / "lora_image"
    plan = build_image_lora_cmd(
        cfg, src, dataset_dir, output_dir=out, max_train_epochs=epochs,
        blocks_to_swap=blocks_to_swap, seed=seed,
    )
    _print_plan(plan)
    if not dry_run:
        _run_plan(chars, src, plan, dataset_dir)


@train_app.command("wan")
def train_wan(
    character: str,
    expert: str = typer.Option("low", "--expert", help="low|high"),
    dataset: Path = typer.Option(None, "--dataset", help="Default: characters/<id>/dataset."),
    output_dir: Path = typer.Option(None, "--output-dir", help="Default: outputs/training/<id>/lora_wan_<expert>."),
    epochs: int = typer.Option(None, "--epochs", help="Default: ~2500 total steps."),
    blocks_to_swap: int = typer.Option(0, "--blocks-to-swap", help="Retry with 10 on OOM."),
    dry_run: bool = typer.Option(True, "--dry-run/--run", help="--run executes (blocks until training ends)."),
    seed: int = typer.Option(42, "--seed"),
):
    """Wan 2.2 expert LoRA via musubi-tuner (task i2v-A14B), images-only likeness training."""
    from .train.wan import build_wan_lora_cmd  # noqa: PLC0415

    cfg, chars, src, dataset_dir = _train_common(character, dataset)
    out = output_dir or outputs_dir(cfg) / "training" / src.character_id / f"lora_wan_{expert}"
    plan = build_wan_lora_cmd(
        cfg, src, dataset_dir, expert, output_dir=out, max_train_epochs=epochs,
        blocks_to_swap=blocks_to_swap, seed=seed,
    )
    _print_plan(plan)
    if not dry_run:
        _run_plan(chars, src, plan, dataset_dir)


@train_app.command("select")
def train_select(
    checkpoint_dir: Path,
    character: str = typer.Option(..., "--character"),
    by: str = typer.Option("mean", "--by", help="mean (image LoRA) | min (video LoRA, worst frame)"),
    inertia: bool = typer.Option(True, "--inertia/--no-inertia", help="Flag near-identical samples (prompt inertia)."),
):
    """Score sample images from each checkpoint and rank by identity (frontal samples only)."""
    from .train.select import rank_checkpoints  # noqa: PLC0415

    cfg, chars, src = _load(character)
    ranking = rank_checkpoints(checkpoint_dir, src, _scorer(cfg, chars), by=by, check_inertia=inertia)
    for row in ranking:
        rprint(row)
    if not ranking:
        rprint("[yellow]no checkpoint sample images found[/yellow]")


# --- bootstrap -------------------------------------------------------------


@bootstrap_app.command("sheet")
def bootstrap_sheet_cmd(
    character: str,
    dry_run: bool = typer.Option(False, "--dry-run"),
    no_gate: bool = typer.Option(False, "--no-gate"),
    render_pass: str = typer.Option("final", "--pass"),
    seed_base: int = typer.Option(1000, "--seed-base"),
):
    """Build the Qwen-Image-Edit sheet dataset (images + caption .txt + manifest.json)."""
    from .bootstrap.sheet import bootstrap_sheet  # noqa: PLC0415

    cfg, chars, src = _load(character)
    gates_enabled = cfg["gates"]["identity_enabled"] and not no_gate
    client = None
    scorer = _scorer(cfg, chars) if gates_enabled else None
    if not dry_run:
        from .render.sheet import SheetRenderer  # noqa: PLC0415

        client = SheetRenderer(cfg, chars, render_pass=render_pass, seed_base=seed_base, log=rprint)
        if not client.client.is_reachable():
            rprint("[red]ComfyUI is not reachable[/red] — start it with C:\\ComfyUI\\start.bat and retry")
            raise typer.Exit(2)
    summary = bootstrap_sheet(cfg, src, chars, client=client, scorer=scorer,
                              dry_run=dry_run, gates_enabled=gates_enabled, log=rprint)
    rprint(summary)


# --- voice -----------------------------------------------------------------


@voice_app.command("say")
def voice_say(
    character: str,
    text: str,
    emotion: str = typer.Option("neutral", "--emotion"),
    pace: str = typer.Option("normal", "--pace"),
    out: Path = typer.Option(None, "--out"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    device: str = typer.Option(None, "--device", help="cuda|cpu (default: auto-detect)."),
    seed: int = typer.Option(None, "--seed", help="Repeatable take."),
):
    """Synthesize speech in the character's voice (Chatterbox).

    With no voice.reference_clip the built-in voice is used — that's the
    bootstrap path for giving a new character a synthetic voice.
    """
    from .voice.chatterbox import synthesize  # noqa: PLC0415

    cfg, chars, src = _load(character)
    out = out or outputs_dir(cfg) / "voice" / f"{character}.wav"
    result = synthesize(src, text, out, chars, emotion=emotion, pace=pace,
                        dry_run=dry_run, device=device, seed=seed, log=rprint)
    rprint(result)


# --- pose ------------------------------------------------------------------


def _pose_ctx():
    from .config import resolve_path  # noqa: PLC0415

    cfg = load_config()
    p = cfg["pose"]
    return cfg, resolve_path(p["library"]), str(resolve_path(p["landmarker"]))


@pose_app.command("list")
def pose_list():
    """Show available poses, their variants and the metrics each one gates on."""
    from .pose import POSES, gates  # noqa: PLC0415

    _, library, _ = _pose_ctx()
    for name, pose in POSES.items():
        target, _, _ = gates(pose)
        have = [v for v in pose["variants"] if (library / f"{name}_{v}.png").exists()]
        missing = [v for v in pose["variants"] if v not in have]
        rprint(f"[bold]{name}[/bold]  gates: {', '.join(sorted(target))}")
        rprint(f"  references: {len(have)}/{len(pose['variants'])} present"
               + (f" [yellow](missing: {', '.join(missing)})[/yellow]" if missing else ""))


@pose_app.command("make-ref")
def pose_make_ref(
    pose: str = typer.Argument(..., help="Pose name (see `sourcemode pose list`)."),
    variant: str = typer.Option(None, "--variant", help="Just this one variant."),
    seed: int = typer.Option(8801, "--seed"),
):
    """Render this pose's reference photos, measure them, keep the best."""
    from .pose import POSES  # noqa: PLC0415
    from .pose.transfer import make_reference  # noqa: PLC0415
    from .render.client import ComfyUIClient  # noqa: PLC0415

    if pose not in POSES:
        rprint(f"[red]unknown pose {pose!r}[/red] — try: {', '.join(POSES)}")
        raise typer.Exit(2)
    cfg, library, landmarker = _pose_ctx()
    client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
    if not client.is_reachable():
        rprint("[red]ComfyUI is not reachable[/red]")
        raise typer.Exit(2)
    wanted = [variant] if variant else list(POSES[pose]["variants"])
    for j, v in enumerate(wanted):
        rprint(f"  [cyan]{v}[/cyan]:")
        make_reference(cfg, client, pose, v, library, landmarker, seed + j * 1000, log=rprint)


@pose_app.command("transfer")
def pose_transfer_cmd(
    pose: str = typer.Argument(..., help="Pose name (see `sourcemode pose list`)."),
    assets: Path = typer.Option(..., "--assets", help="Folder of source *_standing.webp renders."),
    out: Path = typer.Option(None, "--out", help="Where results go (default: config [pose].outputs)."),
    variant: str = typer.Option(None, "--variant", help="Pin one variant instead of random."),
    limit: int = typer.Option(3, "--limit"),
    candidates: int = typer.Option(4, "--candidates", help="Renders per image; best wins."),
    pattern: str = typer.Option("*_standing.webp", "--pattern"),
    seed: int = typer.Option(8801, "--seed"),
    hair: str = typer.Option(None, "--hair", help='Describe a TIED hairstyle, e.g. "two low pigtails". Only when true — naming a style that is not there introduces it.'),
    shoes: str = typer.Option(None, "--shoes", help="Override the footwear chosen from the outfit. Visible footwear in the source is kept either way."),
    no_shoes: bool = typer.Option(False, "--no-shoes", help="Do not specify footwear at all; leave feet to the source and the pose reference."),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Re-pose every matching asset, keeping its outfit and identity."""
    from .pose import POSES  # noqa: PLC0415
    from .pose.transfer import transfer  # noqa: PLC0415
    from .render.client import ComfyUIClient  # noqa: PLC0415

    if pose not in POSES:
        rprint(f"[red]unknown pose {pose!r}[/red] — try: {', '.join(POSES)}")
        raise typer.Exit(2)
    cfg, library, landmarker = _pose_ctx()
    sources = sorted(Path(assets).glob(pattern))[:limit]
    if not sources:
        rprint(f"[red]no {pattern} in {assets}[/red]")
        raise typer.Exit(2)

    out = out or outputs_dir(cfg) / "pose-transfer"
    rprint(f"{len(sources)} image(s) -> {pose}, {candidates} candidates each")
    for s in sources:
        rprint(f"  {s.name}")
    if dry_run:
        raise typer.Exit(0)

    client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
    if not client.is_reachable():
        rprint("[red]ComfyUI is not reachable[/red]")
        raise typer.Exit(2)
    ok = transfer(cfg, client, sources, pose, library, Path(out), landmarker,
                  variant=variant, candidates=candidates, seed=seed, hair=hair,
                  shoes=shoes, no_shoes=no_shoes, log=rprint)
    rprint(f"\n[green]{ok}/{len(sources)}[/green] written to {out}")
    rprint("Review these before copying anything into a game repo.")
    raise typer.Exit(0 if ok == len(sources) else 1)


if __name__ == "__main__":
    app()
