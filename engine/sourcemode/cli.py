"""`sourcemode` CLI (Typer).

Commands: doctor, train, voice, pose, monitor, assets, gpu, lora, library.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

# emoji=False: rich turns ":cat:" in a job label like "shoot:cat:club" into an
# emoji, and the cp1252 console then raises - it killed the GPU runner on
# 2026-10-10 and broke `gpu list`. Markup ([red]...[/red]) still works.
rprint = Console(emoji=False).print

from .config import characters_dir, load_config, outputs_dir

app = typer.Typer(name="sourcemode", no_args_is_help=True, help="SourceMode pipeline engine.")
train_app = typer.Typer(no_args_is_help=True, help="Training-set gate, preview and approval.")
voice_app = typer.Typer(no_args_is_help=True, help="Voice synthesis (Chatterbox).")
pose_app = typer.Typer(no_args_is_help=True, help="Pose transfer: same character and outfit, new pose.")
monitor_app = typer.Typer(no_args_is_help=True, help="Live readout of the GPU box for the control panel.")
assets_app = typer.Typer(no_args_is_help=True, help="In-game asset production: background removal, review sheets.")
gpu_app = typer.Typer(no_args_is_help=True, help="Serialised GPU work: one ordered queue, one runner, one job at a time.")
library_app = typer.Typer(no_args_is_help=True, help="The library: every set by character, dated. plan writes the table; apply moves.")
lora_app = typer.Typer(no_args_is_help=True, help="The locked LoRA per character: lock, status, verify, restage.")
judge_app = typer.Typer(no_args_is_help=True, help="Blind judge sets: build one from renders for the Judging tab.")
app.add_typer(train_app, name="train")
app.add_typer(judge_app, name="judge")
app.add_typer(voice_app, name="voice")
app.add_typer(pose_app, name="pose")
app.add_typer(monitor_app, name="monitor")
app.add_typer(assets_app, name="assets")
app.add_typer(gpu_app, name="gpu")
app.add_typer(lora_app, name="lora")
app.add_typer(library_app, name="library")


@judge_app.command("pair")
def judge_pair(
    set_id: str = typer.Argument(..., help="Judge set id, e.g. pair_amanda_pack."),
    a: Path = typer.Option(..., "--a", help="First render root: files, or one folder per look."),
    b: Path = typer.Option(..., "--b", help="Second render root, laid out the same way."),
    arm_a: str = typer.Option(..., "--arm-a", help="What A is, e.g. 'edit on magenta'."),
    arm_b: str = typer.Option(..., "--arm-b", help="What B is, e.g. 't2i on grey'."),
    title: str = typer.Option(None, "--title", help="Title on the Judging tab (default: the set id)."),
    question: str = typer.Option("Which is better? Tap the check under it.", "--question"),
    pattern: str = typer.Option("*.png", "--pattern", help="Which files count inside each root or look folder."),
    reference: Path = typer.Option(None, "--reference", help="Her reference photo, shown on the page."),
):
    """A side-by-side judge set: every name present in both roots is one pair,
    A's image against B's, which side is which fixed at random per pair.
    Picking the check under one keeps it and rejects the other; neither rejects both."""
    from .assets.judge import judge_root, pair_set  # noqa: PLC0415

    cfg, _ = _ctx()
    out, unpaired = pair_set(judge_root(cfg), set_id, title or set_id, a, b, arm_a=arm_a, arm_b=arm_b,
                             question=question, pattern=pattern, reference=reference)
    n = len(json.loads(out.read_text(encoding="utf-8"))["items"]) // 2
    rprint(f"{n} pairs -> {out}   ({arm_a} vs {arm_b})")
    if unpaired:
        rprint(f"[yellow]{len(unpaired)} in one root only, not paired:[/yellow] {', '.join(unpaired[:12])}"
               + (" …" if len(unpaired) > 12 else ""))


@library_app.command("plan")
def library_plan():
    """Write library/_plan.md and _plan.json: old folder -> new folder. Moves nothing."""
    from . import library as L  # noqa: PLC0415
    from .assets import appearance as A  # noqa: PLC0415
    from .assets.judge import judge_root  # noqa: PLC0415

    cfg = load_config()
    out = outputs_dir(cfg)
    chars = {c for c in A._load()["look"] if not c.startswith("_")} | set(A.key_characters())
    for sub in ("lora-datasets", "shoots", "game-assets", "photosets"):
        if (out / sub).is_dir():
            chars |= {p.name.split("_")[0].lower() for p in (out / sub).iterdir() if p.is_dir() and not p.name.startswith("_")}
    rows = L.plan(out, judge_root(cfg), chars)
    pj, pm = L.write_plan(rows, L.library_dir(cfg))
    by = {}
    for r in rows:
        by[r["action"]] = by.get(r["action"], 0) + 1
    rprint(f"{len(rows)} rows: " + ", ".join(f"{k} {v}" for k, v in sorted(by.items())))
    rprint(f"read [bold]{pm}[/bold]; apply with: sourcemode library apply")


@library_app.command("apply")
def library_apply(
    plan_file: Path | None = typer.Option(None, "--plan", help="Defaults to library/_plan.json."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would move; touch nothing."),
):
    """Move every `move` row of the plan, rewrite the judge sets, link keepers into kept/."""
    import time  # noqa: PLC0415

    from . import library as L  # noqa: PLC0415
    from .assets.judge import judge_root  # noqa: PLC0415

    cfg = load_config()
    lib = L.library_dir(cfg)
    pf = plan_file or lib / "_plan.json"
    rows = json.loads(pf.read_text(encoding="utf-8"))
    for line in L.apply(rows, outputs_dir(cfg), lib, judge_root(cfg), dry_run=dry_run):
        rprint(line)
    if not dry_run:
        done = pf.with_name(f"_plan.applied-{time.strftime('%Y%m%d-%H%M%S')}.json")
        pf.rename(done)
        rprint(f"plan archived as {done.name}")


@library_app.command("prune")
def library_prune(
    apply: bool = typer.Option(False, "--apply", help="Delete the rows in library/_prune.json."),
    dry_run: bool = typer.Option(False, "--dry-run", help="With --apply: print what would go; delete nothing."),
    ab_days: int = typer.Option(7, "--ab-days", help="A/B sets older than this are listed."),
):
    """What a locked winner makes redundant: her sweeps, old A/B sets, her losing checkpoints. Plan first; --apply deletes."""
    from . import library as L  # noqa: PLC0415
    from .assets.judge import judge_root  # noqa: PLC0415

    cfg = load_config()
    lib = L.library_dir(cfg)
    if not apply:
        rows = L.prune_plan(cfg, outputs_dir(cfg), judge_root(cfg), ab_days=ab_days)
        pj, pm = L.write_prune(rows, lib)
        by = {}
        for r in rows:
            by[r["kind"]] = by.get(r["kind"], 0) + 1
        rprint(f"{len(rows)} rows ({sum(r['bytes'] for r in rows) / 1e9:.1f} GB): "
               + ", ".join(f"{k} {v}" for k, v in sorted(by.items())))
        rprint(f"read [bold]{pm}[/bold]; delete with: sourcemode library prune --apply")
        return
    rows = json.loads((lib / "_prune.json").read_text(encoding="utf-8"))
    for line in L.prune_apply(cfg, rows, judge_root(cfg), dry_run=dry_run):
        rprint(line)


@lora_app.command("lock")
def lora_lock(
    character: str = typer.Argument(..., help="Character id, e.g. zara."),
    epoch: int | None = typer.Option(None, "--epoch", help="Epoch to lock; resolved in the dataset's lora folders."),
    file: Path | None = typer.Option(None, "--file", help="Lock this exact .safetensors instead of resolving an epoch."),
    dataset: str | None = typer.Option(None, "--dataset", help="Defaults to <character>_v2."),
    output_name: str | None = typer.Option(None, "--output-name", help="Checkpoint prefix when it differs from the dataset (priyanka_v2b, daisy_ext)."),
    basis: str = typer.Option("", "--basis", help="The evidence: which set, how many kept."),
):
    """Lock her LoRA: copy it to library/loras, stage it in ComfyUI, record it in characters/loras.json."""
    from .train.epochs import checkpoint_for  # noqa: PLC0415
    from .train.locked import LockError, lock  # noqa: PLC0415

    cfg = load_config()
    ds = dataset or f"{character.lower()}_v2"
    src = file
    if src is None:
        if epoch is None:
            raise typer.BadParameter("give --epoch or --file")
        hit = checkpoint_for(outputs_dir(cfg), ds, output_name or ds, epoch)
        if not hit:
            rprint(f"[red]no checkpoint for {ds} epoch {epoch} on disk[/red]")
            raise typer.Exit(1)
        src = Path(hit)
    try:
        row = lock(cfg, character, src, epoch=epoch, dataset=ds, basis=basis, log=rprint)
    except LockError as exc:
        rprint(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    rprint(f"[green]locked[/green] {character}: {row['file']} sha256 {row['sha256'][:12]}  -> characters/loras.json")


@lora_app.command("unlock")
def lora_unlock(character: str = typer.Argument(..., help="Character id.")):
    """Remove her lock and vault copy. Also drops her epoch-choices record so the board shows no pick."""
    from .train.locked import LockError, unlock  # noqa: PLC0415

    cfg = load_config()
    try:
        row = unlock(cfg, character)
    except LockError as exc:
        rprint(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    choice = outputs_dir(cfg) / "epoch-choices" / f"{character.lower()}.json"
    if choice.is_file():
        choice.unlink()
        rprint("epoch choice removed")
    rprint(f"unlocked {character}: {row['file']}" if row else f"{character} was not locked")


@lora_app.command("status")
def lora_status():
    """Every locked character, where her file is, and whether both copies verify."""
    from .train.locked import registry_path, verify  # noqa: PLC0415

    cfg = load_config()
    rows = verify(cfg)
    if not rows:
        rprint(f"nothing locked yet ({registry_path()})")
        return
    for r in rows:
        mark = "[green]ok[/green]" if r["ok"] else "[red]" + "; ".join(r["problems"]) + "[/red]"
        bk = "" if r["backup_ok"] is None else (" backup" if r["backup_ok"] else " [red]no backup[/red]")
        rprint(f"{r['character']:10s} {r['name']:24s} <- {r['file']:34s} ep {str(r['epoch'] or '?'):>3s}  {mark}{bk}   {r['basis']}")
    bad = [r for r in rows if not r["ok"]]
    rprint(f"{len(rows)} locked, {len(bad)} with a problem")


@lora_app.command("backup")
def lora_backup():
    """Mirror every locked LoRA into [paths] lora_backup (his Google Drive folder), hash-verified.
    A lock mirrors itself as it is made; this is the catch-up for the ones made before, or while the drive was away."""
    from .train.locked import LockError, backup_all  # noqa: PLC0415

    try:
        rows = backup_all(load_config(), log=rprint)
    except LockError as exc:
        rprint(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    bad = [r for r in rows if not r["ok"]]
    for r in bad:
        rprint(f"[red]{r['character']}: {r['problem']}[/red]")
    rprint(f"{len(rows) - len(bad)} of {len(rows)} backed up")
    if bad:
        raise typer.Exit(1)


@lora_app.command("rename")
def lora_rename(apply: bool = typer.Option(False, "--apply", help="Do it. Without this, print the plan.")):
    """One name per character: every copy outside the training folder becomes <character>.safetensors.
    Jeremy, 2026-10-15. Copies verify by hash before any old-named copy is removed; strays are set aside in _previous/."""
    from .train.locked import rename_apply, rename_plan  # noqa: PLC0415

    cfg = load_config()
    if not apply:
        n = 0
        for r in rename_plan(cfg):
            if r["problem"]:
                rprint(f"[red]{r['character']}: {r['problem']}[/red]")
                continue
            for what, src, dst in r["moves"]:
                rprint(f"{r['character']:10s} {what:8s} {src} -> {dst}"); n += 1
            for p in r["deletes"]:
                rprint(f"{r['character']:10s} remove   {p}"); n += 1
        rprint(f"{n} steps; run with --apply" if n else "nothing to rename")
        return
    for line in rename_apply(cfg, log=rprint):
        rprint(line)


@lora_app.command("verify")
def lora_verify():
    """Exit 1 if any locked LoRA is missing from the vault or ComfyUI, or differs from its hash."""
    from .train.locked import verify  # noqa: PLC0415

    bad = [r for r in verify(load_config()) if r["problems"]]
    for r in bad:
        rprint(f"[red]{r['character']}: {'; '.join(r['problems'])}[/red]")
    if bad:
        raise typer.Exit(1)
    rprint("[green]every locked LoRA verifies[/green]")


@lora_app.command("restage")
def lora_restage(character: str = typer.Argument(..., help="Character id.")):
    """Copy her vault file back into ComfyUI."""
    from .train.locked import LockError, restage  # noqa: PLC0415

    try:
        rprint(f"staged {restage(load_config(), character)}")
    except LockError as exc:
        rprint(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


@assets_app.command("plan")
def assets_plan(
    character: str = typer.Argument(..., help="Character id as the game knows it (e.g. priyanka)."),
    out: Path = typer.Option(..., "--out", help="Where to write the plan JSON."),
    lora: str = typer.Option(None, "--lora", help="Identity LoRA (relative to ComfyUI loras dir)."),
    source_asset: Path = typer.Option(None, "--source", help="A 2:3 render of her to condition on (wardrobe/framing)."),
    reference: Path = typer.Option(None, "--reference", help="Closeup used to score identity."),
    looks: Path = typer.Option(None, "--looks", help='JSON {category: [{"outfit":..., "hair":...}, ...]} in look order.'),
    game_root: Path = typer.Option(None, "--game-root", help="Game repo; existing looks are read so new numbers extend, not collide."),
    pose: str = typer.Option("standing", "--pose"),
    pack: str = typer.Option("28", "--pack", help="28 = the standard six-category pack; or category=count,... e.g. casual=2,work=1"),
):
    """Decide look numbers up front: the plan is where <category>_<NN> identities are born."""
    import json  # noqa: PLC0415

    from .assets.catalog import PACK_28, existing_looks, make_plan, plan_slots  # noqa: PLC0415

    counts = PACK_28 if pack == "28" else {k: int(v) for k, v in (kv.split("=") for kv in pack.split(","))}
    look_map = json.loads(looks.read_text(encoding="utf-8")) if looks else None
    plan = make_plan(character, counts=counts, pose=pose, lora=lora,
                     source_asset=str(source_asset) if source_asset else None,
                     reference=str(reference) if reference else None, looks=look_map)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=1), encoding="utf-8")
    slots = plan_slots(plan)
    blank = sum(1 for s in slots if not s["outfit"] or not s["hair"])
    rprint(f"plan for [cyan]{character}[/cyan]: {len(slots)} looks -> {out}")
    # the pack replaces her looks in the game, so say what it will overwrite
    shipped = existing_looks(game_root / "src" / "assets" / "characters" / character / "outfits") if game_root else {}
    if shipped:
        rprint(f"  replaces her shipped looks: {shipped}")
    if blank:
        rprint(f"  [yellow]{blank} looks have no outfit/hair yet[/yellow] — fill them in before `assets render`")


@assets_app.command("lingerie")
def assets_lingerie(
    character: str = typer.Argument(..., help="Character id as the game knows it."),
    ship: bool = typer.Option(False, "--ship", help="Copy the staged files into the game repo. Your approval; nothing else writes there."),
    game_root: Path = typer.Option(None, "--game-root", help="The game repo (default: the one the Characters tab ships to)."),
):
    """Stage her kept Lingerie-pack shots as the game's intimate art; --ship copies them in.

    Writes outputs/game-assets/<char>/intimate/: lingerie_01.webp (the base the wardrobe
    button checks for) and <char>_lingerie_<pose>.webp per kept pose, which the chat
    switches to on "kneel", "crawl", "spread your legs"... plus the characterAppearance.js
    line the base file needs."""
    from .assets import intimate as I  # noqa: PLC0415
    from .assets.looks import GAME_ROOT  # noqa: PLC0415
    from .config import outputs_dir  # noqa: PLC0415

    cfg = load_config()
    out = outputs_dir(cfg)
    try:
        rec = I.stage(cfg, out, character)
    except ValueError as exc:
        rprint(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    rprint(f"staged {len(rec['files'])} files for [cyan]{character}[/cyan] in {I.staging_dir(out, character)}")
    rprint(f"  poses: {', '.join(rec['poses'])}; base from {rec['base_from']}")
    rprint("  characterAppearance.js needs:\n" + rec["registration"])
    if ship:
        try:
            s = I.ship(out, character, game_root or GAME_ROOT)
        except ValueError as exc:
            rprint(f"[red]{exc}[/red]")
            raise typer.Exit(1) from exc
        rprint(f"shipped {len(s['files'])} files ({s['overwrote']} overwritten) -> {s['to']}")
    else:
        rprint("  not shipped: add --ship to copy them into the game")


@assets_app.command("render")
def assets_render(
    plan: Path = typer.Option(..., "--plan"),
    out: Path = typer.Option(Path("outputs/game-assets"), "--out"),
    shots: int = typer.Option(4, "--shots", help="Candidates per look; the best one is placed."),
    seed: int = typer.Option(7100, "--seed"),
    only: str = typer.Option(None, "--only", help="Comma list of look ids, e.g. casual_01,work_03"),
    render_pass: str = typer.Option("medium", "--pass"),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Render every look in the plan at the game's 2:3 grid with a keyable background; sidecars carry the slot."""
    import json  # noqa: PLC0415

    from .assets.catalog import plan_slots  # noqa: PLC0415
    from .assets.render import render_plan, shot_prompt  # noqa: PLC0415

    cfg, _ = _ctx()
    p = json.loads(plan.read_text(encoding="utf-8"))
    want = set(only.split(",")) if only else None
    if dry_run:
        for s in plan_slots(p):
            if not want or s["id"] in want:
                rprint(f"[cyan]{s['id']}[/cyan] x{shots}: {shot_prompt(p['character'], s, p.get('trigger'))[:110]}…")
        return
    from .render.client import ComfyUIClient  # noqa: PLC0415

    client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
    if not client.is_reachable():
        rprint("[red]ComfyUI is not reachable[/red]")
        raise typer.Exit(2)
    res = render_plan(cfg, client, p, out, shots=shots, seed=seed, render_pass=render_pass, log=rprint, only=want)
    rprint(f"{len(res)} shots in {out / p['character'] / 'renders'}")


@assets_app.command("place")
def assets_place(
    plan: Path = typer.Option(..., "--plan"),
    cutouts: Path = typer.Option(..., "--cutouts", help="Folder of `assets cutout` results (sidecars are read)."),
    out: Path = typer.Option(Path("outputs/game-assets"), "--out", help="Staging root; files land in <out>/<char>/outfits/."),
    pick: str = typer.Option(None, "--pick", help="Overrides: look_id=filename,... e.g. casual_03=shot_02_s7374.png"),
    work_locations: str = typer.Option(None, "--work-locations", help="Comma list for the wardrobePacks.js line."),
):
    """Name and sort the best cutout of every look into the game's outfits layout, with a mapping sheet."""
    import json  # noqa: PLC0415

    from .assets.catalog import mapping_sheet, pack_registration, place  # noqa: PLC0415

    p = json.loads(plan.read_text(encoding="utf-8"))
    sides = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(cutouts.rglob("*.json"))]
    sides = [s for s in sides if "outputs" in s]
    picks = dict(kv.split("=") for kv in pick.split(",")) if pick else None
    m = place(sides, p, out, pick=picks)
    for s in m["slots"]:
        sc = f" {s['score']:.3f}" if s.get("score") is not None else ""
        fl = f" [yellow]{' '.join(s['flags'])}[/yellow]" if s["flags"] else ""
        ov = " (override)" if s["overridden"] else ""
        rprint(f"  {s['file']:38} <- {Path(s['from']).name}{sc}{fl}{ov}  ({s['candidates']} candidates)")
    if m["missing"]:
        rprint(f"[yellow]missing:[/yellow] {', '.join(m['missing'])}")
    sheet = mapping_sheet(m, out, out / p["character"] / "review" / "mapping_checkerboard.jpg")
    rprint(f"staged {len(m['slots'])} files in {out / p['character'] / 'outfits'}   sheet: {sheet}")
    rprint("wardrobePacks.js line:\n" + pack_registration(p, work_locations=work_locations.split(",") if work_locations else None))


@assets_app.command("cutout")
def assets_cutout(
    inputs: list[Path] = typer.Argument(..., help="Renders (files or folders) to cut out."),
    out: Path = typer.Option(..., "--out", help="Folder for the RGBA results and sidecars."),
    model: str = typer.Option(None, "--model", help="rembg model (default [assets].cutout_model; birefnet-portrait for sharper hair)."),
    size: str = typer.Option(None, "--size", help="Fit onto a transparent canvas, e.g. 1024x1536 (the game's asset grid). Default: keep the render's size."),
    game: bool = typer.Option(False, "--game", help="Shorthand for --size <[assets].game_size> --webp."),
    webp: bool = typer.Option(False, "--webp", help="Also write RGBA WebP next to the PNG."),
    no_matting: bool = typer.Option(False, "--no-matting", help="Skip alpha matting (faster, harder hair edges)."),
    chroma: str = typer.Option(None, "--chroma", help="Key the backdrop instead of using rembg: magenta (#FF00FF), green (#00FF00), or auto to detect whatever uniform colour the plate actually has."),
    despill: float = typer.Option(1.0, "--despill", help="How hard to pull keyed-colour spill out of hair edges (0 disables)."),
    sheet: bool = typer.Option(True, "--sheet/--no-sheet", help="Write a checkerboard review sheet in --out/_review."),
    pattern: str = typer.Option("*.png", "--pattern", help="Which files to pick up inside folders."),
    dry_run: bool = typer.Option(False, "--dry-run"),
):
    """Remove the background from renders -> RGBA PNG (+WebP), alpha report, review sheet.

    The report only annotates: flags are hollow / clipped / islands / tiny; nothing is rejected."""
    from .assets.cutout import (  # noqa: PLC0415
        GREEN, MAGENTA, auto_chroma_remover, checkerboard_sheet, chroma_remover, collect,
        cutout_batch, hybrid_remover, parse_size, rembg_remover,
    )

    cfg, _ = _ctx()
    acfg = cfg.get("assets", {})
    model = model or acfg.get("cutout_model", "isnet-general-use")
    target = parse_size(size) or (tuple(acfg.get("game_size", (1024, 1536))) if game else None)
    webp = webp or game
    files = collect(inputs, pattern)
    if not files:
        rprint(f"[red]no images matched[/red] {pattern!r} in {', '.join(map(str, inputs))}")
        raise typer.Exit(2)
    if chroma:
        model = f"chroma:{chroma}"
    rprint(f"{len(files)} renders -> {out}  model={model}  canvas={target or 'as rendered'}  webp={webp}")
    if dry_run:
        for f in files:
            rprint(f"  {f}")
        return
    if chroma:
        keys = {"magenta": MAGENTA, "green": GREEN}
        if chroma.lower() == "auto":
            remover = auto_chroma_remover(despill=despill)
        elif chroma.lower() in keys:
            remover = chroma_remover(keys[chroma.lower()], despill=despill)
        else:
            rprint(f"[red]--chroma must be auto, {' or '.join(keys)}[/red]")
            raise typer.Exit(2)
    else:
        try:
            remover = hybrid_remover() if model == "hybrid" else rembg_remover(model, matting=not no_matting)
        except ImportError:
            rprint("[red]rembg is not installed[/red] — `uv sync --inexact --extra assets`")
            raise typer.Exit(2)
    results = cutout_batch(files, out, remover=remover, model=model, size=target, webp=webp, log=rprint)
    flagged = [r for r in results if r["report"]["flags"]]
    rprint(f"done: {len(results)} cut, {len(flagged)} flagged for a look")
    if sheet:
        pngs = [Path(r["outputs"]["png"]) for r in results]
        rprint(f"review sheet: {checkerboard_sheet(pngs, out / '_review' / 'cutouts.png')}")


@monitor_app.command("serve")
def monitor_serve(
    host: str = typer.Option(None, "--host", help="Bind address (default from [monitor] in config.toml)."),
    port: int = typer.Option(None, "--port"),
):
    """Serve GPU / ComfyUI / training status over HTTP for the control panel."""
    from .monitor.service import monitor_host, serve  # noqa: PLC0415

    cfg, _ = _ctx()
    rprint(f"monitor on http://{monitor_host(cfg, host)}:{port or cfg['monitor']['port']}  (Ctrl-C to stop)")
    serve(cfg, host=host, port=port)


@monitor_app.command("status")
def monitor_status():
    """One status sample, as JSON — what the service would report right now."""
    import json  # noqa: PLC0415

    from .monitor.sampler import Sampler  # noqa: PLC0415

    cfg, _ = _ctx()
    print(json.dumps(Sampler(cfg).sample_once(), indent=2, default=str))


def _ctx():
    cfg = load_config()
    return cfg, characters_dir(cfg)


# --- top-level -------------------------------------------------------------


@app.command()
def doctor():
    """Check ComfyUI, models, musubi-tuner, InsightFace, GPU, ffmpeg."""
    from .doctor import print_doctor  # noqa: PLC0415

    cfg, _ = _ctx()
    print_doctor(cfg)


# --- train -----------------------------------------------------------------


@train_app.command("check-dataset")
def train_check_dataset(
    dataset_dir: Path,
    trigger: str = typer.Option("", "--trigger", help="Trigger token every caption must start with."),
    bucket: int = typer.Option(1024, "--bucket", help="Training bucket (longest side) the trainer will use."),
    render: str = typer.Option("1024x1536", "--render", help="Size you will generate at, WxH."),
    no_upscale: bool = typer.Option(True, "--no-upscale/--upscale",
                                    help="Mirror bucket_no_upscale: never blow an image up to fill the bucket."),
    block: bool = typer.Option(False, "--block", help="Exit non-zero if any check fails."),
):
    """Gate the TRAINING SET before spending a night on it: face resolution, caption
    variety, self-identical pairs, angle spread, identity coherence, resolution match."""
    from .gates.dataset import DatasetGateError, gate_dataset  # noqa: PLC0415

    w, _, h = render.partition("x")
    try:
        report = gate_dataset(dataset_dir, trigger=trigger, bucket_px=bucket,
                              render_size=(int(w), int(h)), no_upscale=no_upscale, block=block)
    except DatasetGateError as e:
        for finding in e.report["findings"]:
            rprint(f"[{'green' if finding['passed'] else 'red'}]"
                   f"{'PASS' if finding['passed'] else 'FAIL'}[/] {finding['check']}: {finding['detail']}")
        rprint(f"[red]{dataset_dir} is not fit to train on[/red]")
        raise typer.Exit(1) from e
    for finding in report["findings"]:
        rprint(f"[{'green' if finding['passed'] else 'yellow'}]"
               f"{'PASS' if finding['passed'] else 'FAIL'}[/] {finding['check']}: {finding['detail']}")
    rprint(f"score [bold]{report['score']}[/bold] over {report['n_images']} images"
           + ("" if report["passed"] else f" — failing: {', '.join(report['failed'])}"))


@train_app.command("preview")
def train_preview(
    dataset_dir: Path,
    trigger: str = typer.Option("", "--trigger", help="Trigger token every caption should start with."),
    render: str = typer.Option("1024x1536", "--render", help="Size you will generate at, WxH."),
    bucket: int = typer.Option(1024, "--bucket", help="Training bucket (longest side) from the dataset TOML."),
    name: str = typer.Option(None, "--name", help="Preview id; defaults to the directory name."),
    quick: bool = typer.Option(False, "--quick", help="Skip face measurement (no InsightFace)."),
):
    """Build the human read of a training set: every image beside its caption.

    Open the printed URL, look at the pictures, then approve. Nothing trains on an
    unapproved set - see `train approved`.
    """
    from .config import load_config  # noqa: PLC0415
    from .train.preview import build_preview, preview_root  # noqa: PLC0415

    cfg = load_config()
    w, _, h = render.partition("x")
    doc = build_preview(preview_root(cfg), dataset_dir, dataset_id=name, trigger=trigger,
                        render_size=(int(w), int(h)), measure=not quick, bucket_px=bucket)
    flagged = [im for im in doc["images"] if im["missing"] or im["uncaptioned"]]
    rprint(f"[bold]{doc['id']}[/bold]: {doc['n']} images, fingerprint {doc['fingerprint']}")
    if doc.get("gate"):
        g = doc["gate"]
        rprint(f"gate [{'green' if g['passed'] else 'red'}]{'pass' if g['passed'] else 'FAIL'}[/]"
               f" score {g['score']}")
        for f in g["findings"]:
            if not f["passed"]:
                rprint(f"  [red]FAIL[/red] {f['check']}: {f['detail']}")
    if flagged:
        counts: dict[str, int] = {}
        for im in flagged:
            for m in (im["missing"] or (["caption"] if im["uncaptioned"] else [])):
                counts[m] = counts.get(m, 0) + 1
        rprint("captions never naming: " + ", ".join(
            f"[yellow]{k}[/yellow] on {v}/{doc['n']}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])))
    cr = doc.get("captions", {})
    if cr:
        rprint(f"captions [{'green' if cr['passed'] else 'red'}]"
               f"{'pass' if cr['passed'] else 'FAIL'}[/] median {cr['median_words']} words")
        for f in cr["findings"]:
            if not f["passed"]:
                rprint(f"  [red]FAIL[/red] {f['check']}: {f['detail']}")
    host = cfg["monitor"]["host"]
    host = "127.0.0.1" if host == "0.0.0.0" else host  # noqa: S104
    rprint(f"review it: http://{host}:{cfg['monitor']['port']}/dataset#{doc['id']}")


@train_app.command("approved")
def train_approved(
    dataset_id: str,
    quiet: bool = typer.Option(False, "--quiet", help="Print nothing; exit code only."),
):
    """Exit 0 only if this training set has been previewed and approved as it stands.

    Training scripts call this first. Approval is bound to a fingerprint of the
    images and captions, so editing either revokes it rather than carrying forward.
    """
    from .config import load_config  # noqa: PLC0415
    from .train.preview import approval_state, preview_root  # noqa: PLC0415

    st = approval_state(preview_root(load_config()), dataset_id)
    if not quiet:
        if st["approved"]:
            rprint(f"[green]approved[/green] {dataset_id} at {st['at']} ({st['fingerprint']})")
        elif st["stale"]:
            rprint(f"[red]STALE[/red] {dataset_id}: approved as {st['approved_fingerprint']},"
                   f" now {st['fingerprint']} - images or captions changed since")
        else:
            rprint(f"[red]not approved[/red] {dataset_id} - run `sourcemode train preview` and review it")
    raise typer.Exit(0 if st["approved"] else 1)


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
    clip: Path = typer.Option(None, "--clip", help="Reference clip to clone; omit for the built-in voice."),
):
    """Synthesize speech in the character's voice (Chatterbox).

    With no --clip the built-in voice is used — that's the bootstrap path for
    giving a new character a synthetic voice.
    """
    from .voice.chatterbox import synthesize  # noqa: PLC0415

    cfg, _ = _ctx()
    out = out or outputs_dir(cfg) / "voice" / f"{character}.wav"
    result = synthesize(character, text, out, reference_clip=clip, emotion=emotion, pace=pace,
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
    pattern: str = typer.Option("*_standing.*", "--pattern", help="Which source files to pick up; image extensions only."),
    seed: int = typer.Option(8801, "--seed"),
    hair: str = typer.Option(None, "--hair", help='Describe a TIED hairstyle, e.g. "two low pigtails". Only when true — naming a style that is not there introduces it.'),
    shoes: str = typer.Option(None, "--shoes", help="Override the footwear chosen from the outfit. Visible footwear in the source is kept either way."),
    no_shoes: bool = typer.Option(False, "--no-shoes", help="Do not specify footwear at all; leave feet to the source and the pose reference."),
    refine: bool = typer.Option(False, "--refine", help="Second pass: restore face and hair from the source asset. Declines if it cannot improve on the first pass."),
    no_mask_ref: bool = typer.Option(False, "--no-mask-ref", help="Feed the pose reference with its own face intact (identity competes; for A/B only)."),
    lora: str = typer.Option(None, "--lora", help="Character identity LoRA (path relative to ComfyUI loras dir)."),
    lora_strength: float = typer.Option(0.7, "--lora-strength"),
    render_pass: str = typer.Option("draft", "--pass", help="draft = 4-step lightning (fast, smoother skin). medium = full steps, no lightning (slower, keeps texture)."),
    skeleton: bool = typer.Option(False, "--skeleton", help="Also pass a stick figure as image3: zero identity, but no depth. Use WITH the masked photo, not instead of it."),
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
    # The default pattern is extension-agnostic on purpose: it used to be
    # *_standing.webp while the game's assets are .png, so a whole batch matched
    # nothing, exited 2 per folder, and looked from the log like it had run.
    sources = [p for p in sorted(Path(assets).glob(pattern))
               if p.suffix.lower() in {".png", ".webp", ".jpg", ".jpeg"}][:limit]
    if not sources:
        have = {p.suffix.lower() for p in Path(assets).glob("*") if p.is_file()}
        rprint(f"[red]no files matching {pattern} in {assets}[/red]")
        if have:
            rprint(f"[yellow]that folder contains: {', '.join(sorted(have))}[/yellow]")
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
                  shoes=shoes, no_shoes=no_shoes, refine=refine,
                  mask_reference=not no_mask_ref, skeleton=skeleton,
                  render_pass=render_pass, lora=lora, lora_strength=lora_strength, log=rprint)
    rprint(f"\n[green]{ok}/{len(sources)}[/green] written to {out}")
    rprint("Review these before copying anything into a game repo.")
    raise typer.Exit(0 if ok == len(sources) else 1)



# --- gpu queue -------------------------------------------------------------
#
# Why a queue at all: before this, run order lived in whichever one-off
# PowerShell script a session wrote, each with its own wait loop - nineteen
# copies of the same loop in engine/scripts/eval, all of which proceed anyway
# after four hours. Nothing starts GPU work now except by being in this list.


def _gpu_paths():
    cfg = load_config()
    from .gpu import queue as q  # noqa: PLC0415

    out = outputs_dir(cfg)
    return out, q.queue_path(out)


@gpu_app.command("add")
def gpu_add(
    kind: str = typer.Argument(..., help="train | eval | assets | other - a label for the readout."),
    label: str = typer.Argument(..., help="What it operates on, e.g. zara_v2."),
    cmd: list[str] = typer.Argument(..., help="The command, after a literal -- separator."),
    cwd: str = typer.Option(None, "--cwd", help="Default: the engine directory."),
    requires_approval: str = typer.Option(None, "--requires-approval",
                                          help="Dataset id whose approval is re-checked at start time."),
    note: str = typer.Option("", "--note"),
    allow_duplicate: bool = typer.Option(False, "--allow-duplicate",
                                         help="Queue this even though the same kind+label is already queued."),
    no_check: bool = typer.Option(False, "--no-check",
                                  help="Skip the preflight (script exists and compiles, checkpoints and "
                                       "approval present, disk space) and queue it anyway."),
    cpu: bool = typer.Option(False, "--cpu",
                             help="The CPU lane: never touches the card, runs beside the card's job, "
                                  "capped threads, low priority. Only for work that truly needs no GPU."),
):
    """Append a job to the END of the queue. Appending is how work is requested."""
    from .config import ENGINE_ROOT  # noqa: PLC0415
    from .gpu import queue as q  # noqa: PLC0415

    out, path = _gpu_paths()
    doc = q.load(path)
    dup = q.duplicate_of(doc, kind, label)
    if dup and not allow_duplicate:
        rprint(f"[red]{dup['id']} is already {dup['status']} for {kind}:{label}[/red]"
               " - pass --allow-duplicate if you really mean to run it twice")
        raise typer.Exit(1)
    # A job that dies in its first minute is a bug in the invocation, not a
    # result (jordan_v2: 1 s on disk space; mira_v2: 5 s on a path, three times).
    # Everything the script's own guards would refuse is checked here, before
    # the job can wait hours for the card and then fail.
    if not no_check:
        from .gpu.preflight import preflight  # noqa: PLC0415
        from .train.preview import preview_root  # noqa: PLC0415

        problems = preflight({"cmd": list(cmd), "cwd": cwd or str(ENGINE_ROOT),
                              "requires_approval": requires_approval},
                             out, preview_root(load_config()))
        if problems:
            rprint("[red]not queued[/red] - this job would fail at once:")
            for p in problems:
                rprint(f"  - {p}")
            rprint("fix it, or pass --no-check to queue it anyway")
            raise typer.Exit(1)
    # What the job will produce, decided once here and shown back, so a wrong
    # read of the command is visible now and not on the page an hour later.
    from .monitor.queue_page import expect_for  # noqa: PLC0415

    expect = expect_for(load_config(), list(cmd))
    job = q.add(doc, kind=kind, label=label, cmd=list(cmd), cwd=cwd or str(ENGINE_ROOT),
                requires_approval=requires_approval, note=note, expect=expect,
                lane="cpu" if cpu else "gpu")
    q.save(path, doc)
    rprint(f"[green]queued[/green] {job['id']} {kind}:{label}{' (cpu lane)' if cpu else ''} "
           f"at position {len(doc['jobs'])}")
    if expect:
        rprint(f"  will produce {expect['total']} images ({expect['what']})"
               + (f" in {expect['dir']}" if expect.get("dir") else ""))


@gpu_app.command("list")
def gpu_list(all_jobs: bool = typer.Option(False, "--all", help="Include finished and cancelled jobs.")):
    """What is running, what is next, in order."""
    from .gpu import queue as q  # noqa: PLC0415
    from .gpu.busy import gpu_busy  # noqa: PLC0415
    from .gpu.lease import holder, lease_path  # noqa: PLC0415

    out, path = _gpu_paths()
    doc = q.load(path)
    lease = holder(lease_path(out))
    rprint(f"runner: [green]up[/green] (PID {lease['pid']})" if lease else "runner: [red]NOT RUNNING[/red]")
    if doc["paused"]:
        rprint(f"[red]queue PAUSED[/red]: {doc['pause_reason']}")
    held = gpu_busy()
    if held:
        rprint("card busy: " + ", ".join(f"PID {h['pid']} ({h['pattern']})" for h in held))
    nxt = q.head(doc)
    for i, j in enumerate(doc["jobs"]):
        if not all_jobs and j["status"] in ("done", "cancelled"):
            continue
        marks = []
        if q.lane_of(j) == "cpu":
            marks.append("cpu lane")
        if j["hold"]:
            marks.append("HELD")
        if nxt and j["id"] == nxt["id"]:
            marks.append("NEXT")
        colour = {"running": "cyan", "failed": "red", "queued": "white"}.get(j["status"], "bright_black")
        rprint(f" {i:>2}. [{colour}]{j['id']} {j['status']:<9}[/{colour}] {j['kind']}:{j['label']}"
               f" {' '.join(marks)}" + (f" exit={j['exit_code']}" if j["exit_code"] not in (None, 0) else ""))
    if not doc["jobs"]:
        rprint(" (empty)")


@gpu_app.command("move")
def gpu_move(job_id: str, position: int = typer.Argument(..., help="0-based target position.")):
    """Reorder. The file order is the run order, so this is how the order changes."""
    from .gpu import queue as q  # noqa: PLC0415

    out, path = _gpu_paths()
    doc = q.load(path)
    q.move(doc, job_id, position)
    q.save(path, doc)
    gpu_list(all_jobs=False)


@gpu_app.command("hold")
def gpu_hold(job_id: str, release_it: bool = typer.Option(False, "--release", help="Un-hold it.")):
    """Hold a job in place but make it unrunnable - the only way the runner moves
    past a job it is waiting on. Deliberate by design: never a timeout."""
    from .gpu import queue as q  # noqa: PLC0415

    out, path = _gpu_paths()
    doc = q.load(path)
    job = q.set_hold(doc, job_id, not release_it)
    q.save(path, doc)
    rprint(f"{job['id']} {job['label']}: " + ("released" if release_it else "HELD"))


@gpu_app.command("cancel")
def gpu_cancel(job_id: str):
    """Cancel a queued job. A running job is not cancellable from here."""
    from .gpu import queue as q  # noqa: PLC0415

    out, path = _gpu_paths()
    doc = q.load(path)
    try:
        job = q.cancel(doc, job_id)
    except ValueError as exc:
        rprint(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    q.save(path, doc)
    rprint(f"cancelled {job['id']} {job['label']}")


@gpu_app.command("restart")
def gpu_restart():
    """Ask the runner to exit once BOTH lanes are idle, so a new runner with new
    code takes over between jobs and never under one. The logon task is started
    again by whoever asked; nothing running is touched."""
    from .gpu.runner import RESTART_FLAG  # noqa: PLC0415

    out, _ = _gpu_paths()
    flag = out / "gpu-queue" / RESTART_FLAG
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("restart requested\n", encoding="utf-8")
    rprint(f"restart requested: {flag} - the runner exits when both lanes are idle; "
           f"start the 'SourceMode GPU Runner' task again after it does")


@gpu_app.command("resume")
def gpu_resume():
    """Clear a pause (a fast failure pauses the queue so it is not burned through)."""
    from .gpu import queue as q  # noqa: PLC0415

    out, path = _gpu_paths()
    doc = q.load(path)
    was = doc["pause_reason"]
    q.resume(doc)
    q.save(path, doc)
    rprint(f"resumed (was paused: {was or 'not paused'})")


@gpu_app.command("run")
def gpu_run(
    once: bool = typer.Option(False, "--once", help="Take at most one job, then exit."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report what it would start; never exec."),
    poll: float = typer.Option(60.0, "--poll", help="Seconds between checks while waiting."),
    cpu_threads: int = typer.Option(8, "--cpu-threads",
                                    help="Cores the CPU lane may use; the card's job keeps the rest."),
    cpu_min_free_gb: float = typer.Option(12.0, "--cpu-min-free-gb",
                                          help="The CPU lane starts nothing while free RAM is under this."),
):
    """The single runner. One logon task runs this; a second instance refuses to start."""
    from .gpu.runner import Runner  # noqa: PLC0415

    out, _ = _gpu_paths()
    log_path = out / "logs" / "gpu-runner.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        # 2026-10-10: rich's rprint turned ":cat:" in "shoot:cat:club" into an
        # emoji, the cp1252 console could not encode it, and the runner died
        # mid-START with the job's process already launched. The file is the
        # record, so it is written first; the console copy is plain text and
        # a failure to print it is never fatal.
        line = f"{q_now()}  {msg}"
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + chr(10))
        try:
            print(line, flush=True)
        except (UnicodeEncodeError, OSError):
            try:
                print(line.encode("ascii", "replace").decode("ascii"), flush=True)
            except OSError:
                pass

    try:
        Runner(out, log=log, poll=poll, cpu_threads=cpu_threads,
               cpu_min_free_gb=cpu_min_free_gb).serve(once=once, dry_run=dry_run)
    except RuntimeError as exc:
        rprint(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


def q_now() -> str:
    from .gpu.queue import now  # noqa: PLC0415

    return now()


if __name__ == "__main__":
    app()
