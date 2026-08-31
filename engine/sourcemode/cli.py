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
app.add_typer(source_app, name="source")
app.add_typer(gates_app, name="gates")
app.add_typer(prompts_app, name="prompts")
app.add_typer(render_app, name="render")
app.add_typer(train_app, name="train")
app.add_typer(bootstrap_app, name="bootstrap")
app.add_typer(voice_app, name="voice")


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
):
    """Full pipeline: compile -> keyframes -> video -> gates -> results.yaml."""
    from .orchestrate.run import run_scene  # noqa: PLC0415

    cfg, chars, src = _load(character)
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


@source_app.command("bump")
def source_bump(character: str):
    from .source import bump_version  # noqa: PLC0415

    _, chars = _ctx()
    bumped = bump_version(chars, character)
    rprint(f"[green]{character}[/green] bumped to {bumped.version} (unapproved)")


# --- gates -----------------------------------------------------------------


@gates_app.command("calibrate")
def gates_calibrate(character: str):
    """Pairwise similarity over the approved sheet -> per-character threshold."""
    from .gates.identity import calibrate_identity  # noqa: PLC0415

    _, chars, src = _load(character)
    updated = calibrate_identity(chars, src)
    rprint(f"[green]calibrated[/green] threshold={updated.identity_threshold} embedding={updated.identity_embedding_path}")


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
    dest = Path(scene_yaml).parent / f"shot_{idx:02d}" / "video.webp"
    out = client.fetch(files[0], dest) if files else None
    if out:
        write_sidecar(out, source_version=src.version, prompt_hash=shot["prompt_hash"], seed=seed,
                      models=models_summary(settings), loras=loras_summary(settings),
                      render_pass=render_pass, settings={"kind": "video"})
    rprint(f"rendered -> {out}")


# --- train -----------------------------------------------------------------


@train_app.command("wan-cmd")
def train_wan_cmd(
    character: str,
    dataset_dir: Path = typer.Option(..., "--dataset"),
    expert: str = typer.Option("low", "--expert", help="low|high"),
    run: bool = typer.Option(False, "--run", help="Actually execute (default: print only)."),
):
    """Build (and optionally run) the musubi-tuner Wan 2.2 LoRA training sequence."""
    from .train.wan import build_wan_lora_cmd  # noqa: PLC0415

    cfg, _, src = _load(character)
    plan = build_wan_lora_cmd(cfg, src, dataset_dir, expert)
    rprint(f"[bold]dataset.toml[/bold] -> {plan['dataset_toml_path']}\n{plan['dataset_toml']}")
    for cmd in plan["commands"]:
        rprint(" ".join(f'"{c}"' if " " in c else c for c in cmd))
    if run:
        import subprocess  # noqa: PLC0415

        Path(plan["dataset_toml_path"]).parent.mkdir(parents=True, exist_ok=True)
        Path(plan["dataset_toml_path"]).write_text(plan["dataset_toml"], encoding="utf-8")
        for cmd in plan["commands"]:
            rprint(f"[cyan]running[/cyan] {cmd[1] if len(cmd) > 1 else cmd[0]}")
            subprocess.run(cmd, check=True)


@train_app.command("select")
def train_select(
    checkpoint_dir: Path,
    character: str = typer.Option(..., "--character"),
):
    """Score sample images from each checkpoint and rank by identity."""
    from .train.select import rank_checkpoints  # noqa: PLC0415

    cfg, chars, src = _load(character)
    ranking = rank_checkpoints(checkpoint_dir, src, _scorer(cfg, chars))
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
):
    """Build the Qwen-Image-Edit sheet dataset (images + caption .txt)."""
    from .bootstrap.sheet import bootstrap_sheet  # noqa: PLC0415

    cfg, chars, src = _load(character)
    gates_enabled = cfg["gates"]["identity_enabled"] and not no_gate
    client = None
    scorer = _scorer(cfg, chars) if gates_enabled else None
    if not dry_run:
        rprint("[yellow]live sheet rendering requires a verified Qwen-Image-Edit workflow (BACKLOG); use --dry-run for now[/yellow]")
        raise typer.Exit(2)
    summary = bootstrap_sheet(cfg, src, chars, client=client, scorer=scorer,
                              dry_run=dry_run, gates_enabled=gates_enabled)
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
):
    """Synthesize speech in the character's voice (Chatterbox)."""
    from .voice.chatterbox import synthesize  # noqa: PLC0415

    cfg, chars, src = _load(character)
    out = out or outputs_dir(cfg) / "voice" / f"{character}.wav"
    result = synthesize(src, text, out, chars, emotion=emotion, pace=pace, dry_run=dry_run)
    rprint(result)


if __name__ == "__main__":
    app()
