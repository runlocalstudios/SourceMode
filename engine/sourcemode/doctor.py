"""`sourcemode doctor`: environment probes. Prints a table, never crashes."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table


def _check(fn):
    try:
        return fn()
    except Exception as err:  # noqa: BLE001 — doctor must never crash
        return (False, f"error: {err}")


def run_doctor(cfg: dict) -> list[tuple[str, bool, str]]:
    from .gates.identity import insightface_available  # noqa: PLC0415
    from .render.client import ComfyUIClient  # noqa: PLC0415

    rows: list[tuple[str, bool, str]] = []

    def comfy():
        client = ComfyUIClient(cfg["comfyui"]["host"], cfg["comfyui"]["port"])
        ok = client.is_reachable()
        note = "reachable" if ok else "NOT reachable (start C:\\ComfyUI\\start.bat)"
        return ok, f"{client.base} {note}"

    rows.append(("comfyui", *_check(comfy)))

    def models():
        models_dir = Path(cfg["paths"]["models"])
        wanted = {
            "diffusion_models": [cfg["models"]["wan_i2v_low_fp8"], cfg["models"]["wan_i2v_high_fp8"]],
            "vae": [cfg["models"]["wan_vae"]],
            "text_encoders": [cfg["models"]["umt5"]],
        }
        missing = [
            f"{sub}/{name}"
            for sub, names in wanted.items()
            for name in names
            if not (models_dir / sub / name).exists()
        ]
        if missing:
            return False, f"missing: {', '.join(missing)}"
        return True, f"all Wan 2.2 files present under {models_dir}"

    rows.append(("models", *_check(models)))

    def musubi():
        path = Path(cfg["training"]["musubi_tuner_path"])
        ok = (path / "src" / "musubi_tuner" / "wan_train_network.py").exists()
        return ok, str(path) + ("" if ok else " (wan_train_network.py not found)")

    rows.append(("musubi-tuner", *_check(musubi)))

    def insight():
        ok = insightface_available()
        return ok, "importable" if ok else "not installed (uv sync --extra gates) — gates will annotate as unavailable"

    rows.append(("insightface", *_check(insight)))

    def gpu():
        try:
            import torch  # noqa: PLC0415
        except ImportError:
            return False, "torch not installed in engine venv (GPU work runs in ComfyUI/musubi venvs)"
        if torch.cuda.is_available():
            return True, torch.cuda.get_device_name(0)
        return False, "torch installed but no CUDA device visible"

    rows.append(("gpu (torch)", *_check(gpu)))

    def ffmpeg():
        import shutil  # noqa: PLC0415

        path = shutil.which("ffmpeg")
        return (path is not None), path or "not on PATH (video gate scoring needs it)"

    rows.append(("ffmpeg", *_check(ffmpeg)))

    return rows


def print_doctor(cfg: dict) -> None:
    console = Console()
    table = Table(title="sourcemode doctor")
    table.add_column("check")
    table.add_column("ok")
    table.add_column("details", overflow="fold")
    for name, ok, details in run_doctor(cfg):
        table.add_row(name, "[green]OK[/green]" if ok else "[red]--[/red]", str(details))
    console.print(table)
