"""What a job would die of in its first minute, found BEFORE it is queued.

A job that exits in seconds is a bug in the invocation, not a result: jordan_v2
(2026-10-08) failed in one second on disk space and paused the queue; mira_v2
failed three times in five seconds on a path; three trainings in a row died at
37 s on a missing TOML; a 60-render A/B died four seconds after waiting seven
hours for the card, on a flag in the wrong slot. Every one of those was knowable
from the command line and the files on disk, with no GPU and no model.

`preflight(job, outputs)` returns the problems as plain sentences, empty when
the job may be queued. It never loads a model and never writes anything. The
per-script checks mirror the guards at the top of each script - when one of
those changes, change it here too.
"""

from __future__ import annotations

import py_compile
import shutil
import subprocess
import sys
from pathlib import Path

# train_character.ps1 refuses under this; 24 checkpoints need about 30 GB
TRAIN_DISK_GB = 45


def _flag(cmd: list[str], name: str, default: str | None = None) -> str | None:
    return cmd[cmd.index(name) + 1] if name in cmd and cmd.index(name) + 1 < len(cmd) else default


def _positional(cmd: list[str]) -> list[str]:
    """argv without the valued flags that the eval scripts split out themselves."""
    out, it = [], iter(cmd)
    for a in it:
        if a.startswith("--") and a not in ("--apply", "--all", "--force", "--allow-incomplete-appearance",
                                            "--no-description", "--fp8_vl", "--loragen-only", "--no-base"):
            next(it, None)
        elif not a.startswith("--"):
            out.append(a)
    return out


def _script(cmd: list[str], cwd: Path) -> Path | None:
    for a in cmd:
        if a.lower().endswith((".py", ".ps1")):
            p = Path(a)
            return p if p.is_absolute() else cwd / p
    return None


def _ps1_parses(path: Path) -> str | None:
    ps = shutil.which("powershell.exe") or shutil.which("powershell")
    if not ps:
        return None
    code = ("$t=$null;$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile("
            f"'{path}',[ref]$t,[ref]$e); if($e.Count){{$e[0].Message; exit 1}}")
    r = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-Command", code],
                       capture_output=True, text=True, timeout=60)
    return None if r.returncode == 0 else (r.stdout.strip() or "parse error")


def _appearance_problem(character: str, *, allow_incomplete: bool = False) -> str | None:
    """The sweep and every shoot refuse an unconfirmed record; say so now."""
    if allow_incomplete:
        return None
    from ..assets.appearance import check  # noqa: PLC0415

    st = check(character)
    if st["ok"]:
        return None
    return f"{character}'s appearance record is not ready: " + "; ".join(st["missing"]) + \
        " - confirm it on the Looks tab first"


def _ckpt_dir_problem(d: Path) -> str | None:
    if not d.is_dir():
        return f"checkpoint folder {d} does not exist"
    if not any(d.glob("*.safetensors")):
        return f"no checkpoints in {d}"
    return None


# --- per-script guards ----------------------------------------------------------

def _train_character(cmd: list[str], cwd: Path, outputs: Path, previews_root: Path | None) -> list[str]:
    out = []
    ds = _flag(cmd, "-Ds")
    if not ds:
        return ["train_character.ps1 needs -Ds <dataset>"]
    ds_dir = outputs / "lora-datasets" / ds
    if not (ds_dir / "image_src").is_dir():
        out.append(f"{ds_dir / 'image_src'} does not exist")
    existing = list((ds_dir / "lora").glob("*.safetensors")) if (ds_dir / "lora").is_dir() else []
    if existing and "-Force" not in cmd:
        out.append(f"{ds}/lora already holds {len(existing)} checkpoints - the script refuses without -Force")
    if previews_root is not None:
        from ..train.preview import approval_state  # noqa: PLC0415

        st = approval_state(previews_root, ds)
        if not st["approved"]:
            out.append(f"{ds} is not approved as it stands" + (" (stale: images or captions changed)"
                                                              if st.get("stale") else ""))
    free_gb = shutil.disk_usage(str(outputs if outputs.exists() else Path.cwd())).free / 2**30
    if free_gb < TRAIN_DISK_GB:
        out.append(f"{free_gb:.1f} GB free on the outputs drive; a training needs {TRAIN_DISK_GB} GB")
    char = _flag(cmd, "-Char") or ds.rsplit("_", 1)[0]
    p = _appearance_problem(char)
    if p:
        out.append(p + " (the post-training sweep refuses without it)")
    return out


def _dense_epoch_eval(cmd: list[str], cwd: Path, outputs: Path, previews_root: Path | None) -> list[str]:
    # positional: script char sub total start end trigger ckpt [scenes] [offset]
    pos = _positional(cmd)
    i = next((k for k, c in enumerate(pos) if c.endswith("dense_epoch_eval.py")), None)
    if i is None or len(pos) < i + 8:
        return ["dense_epoch_eval.py needs: <char> <sub> <total> <start> <end> <trigger> <ckpt_dir> [scenes]"]
    out = []
    char, sub, total = pos[i + 1], pos[i + 2], pos[i + 3]
    for name, v in (("total", total), ("start", pos[i + 4]), ("end", pos[i + 5])):
        if not v.lstrip("-").isdigit():
            out.append(f"{name} must be a number, got {v!r} - a flag in a positional slot?")
    ck = Path(pos[i + 7])
    ck = ck if ck.is_absolute() else cwd / ck
    p = _ckpt_dir_problem(ck)
    if p:
        out.append(p)
    elif total.isdigit():
        eps = [int(x) for x in (_flag(cmd, "--epochs") or "").split(",") if x.strip().isdigit()]
        for ep in eps:
            name = f"{sub}.safetensors" if ep == int(total) else f"{sub}-{ep:06d}.safetensors"
            if not (ck / name).is_file():
                out.append(f"epoch {ep}: {name} is not in {ck}")
    p = _appearance_problem(char, allow_incomplete="--allow-incomplete-appearance" in cmd)
    if p:
        out.append(p)
    return out


def _prompt_ab(cmd: list[str], cwd: Path, outputs: Path, previews_root: Path | None) -> list[str]:
    # positional: script char sub epoch ckpt_dir trigger
    pos = _positional(cmd)
    i = next((k for k, c in enumerate(pos) if c.endswith("prompt_ab.py")), None)
    if i is None or len(pos) < i + 6:
        return ["prompt_ab.py needs: <char> <sub> <epoch> <ckpt_dir> <trigger> --find ... --arms ..."]
    out = []
    sub, ep, ck = pos[i + 2], pos[i + 3], Path(pos[i + 4])
    ck = ck if ck.is_absolute() else cwd / ck
    if not ep.isdigit():
        out.append(f"epoch must be a number, got {ep!r}")
    p = _ckpt_dir_problem(ck)
    if p:
        out.append(p)
    elif ep.isdigit() and not any((ck / n).is_file() for n in (f"{sub}-{int(ep):06d}.safetensors", f"{sub}.safetensors")):
        out.append(f"no checkpoint for epoch {ep} in {ck}")
    if not _flag(cmd, "--find"):
        out.append("--find is required")
    if len([a for a in (_flag(cmd, "--arms") or "").split("|") if "=" in a]) < 2:
        out.append("--arms needs at least two, as 'A=text|B=text'")
    p = _appearance_problem(pos[i + 1])
    if p:
        out.append(p)
    return out


def _run_shoots(cmd: list[str], cwd: Path, outputs: Path, previews_root: Path | None) -> list[str]:
    pos = _positional(cmd)
    i = next((k for k, c in enumerate(pos) if c.endswith("run_shoots.py")), None)
    if i is None or len(pos) < i + 3:
        return ["run_shoots.py needs: <char> <shoot_ids,comma,separated>"]
    out = []
    char = pos[i + 1]
    from ..assets.lora import resolve_lora  # noqa: PLC0415
    from ..config import load_config  # noqa: PLC0415

    try:
        if resolve_lora(load_config(), char) is None:
            out.append(f"{char} has no chosen checkpoint - pick her epoch on the judge page first")
    except Exception as ex:  # noqa: BLE001
        out.append(f"could not resolve {char}'s LoRA: {ex}")
    p = _appearance_problem(char)
    if p:
        out.append(p)
    return out


GUARDS = {
    "train_character.ps1": _train_character,
    "dense_epoch_eval.py": _dense_epoch_eval,
    "prompt_ab.py": _prompt_ab,
    "run_shoots.py": _run_shoots,
}


def preflight(job: dict, outputs: Path, previews_root: Path | None = None) -> list[str]:
    """Everything that would make this job fail at once. Empty means queue it."""
    cmd = list(job.get("cmd") or [])
    problems: list[str] = []
    if not cmd:
        return ["the job has no command"]
    cwd = Path(job.get("cwd") or ".")
    if not cwd.is_dir():
        return [f"cwd {cwd} does not exist"]
    exe = cmd[0]
    if not (Path(exe).is_file() or shutil.which(exe)):
        problems.append(f"{exe} is not an executable on this machine")
    script = _script(cmd, cwd)
    if script is not None:
        if not script.is_file():
            problems.append(f"script {script} does not exist")
        elif script.suffix.lower() == ".py":
            try:
                py_compile.compile(str(script), doraise=True, cfile=None)
            except py_compile.PyCompileError as ex:
                problems.append(f"{script.name} does not compile: {ex.msg.strip().splitlines()[-1]}")
        elif script.suffix.lower() == ".ps1":
            err = _ps1_parses(script)
            if err:
                problems.append(f"{script.name} does not parse: {err}")
    if job.get("requires_approval") and previews_root is not None:
        from ..train.preview import approval_state  # noqa: PLC0415

        if not approval_state(previews_root, job["requires_approval"])["approved"]:
            problems.append(f"{job['requires_approval']} is not approved as it stands")
    if script is not None and script.is_file():
        guard = GUARDS.get(script.name)
        if guard:
            try:
                problems += guard(cmd, cwd, outputs, previews_root)
            except Exception as ex:  # noqa: BLE001
                problems.append(f"preflight for {script.name} itself failed: {ex!r}")
    return problems


if __name__ == "__main__":  # python -m sourcemode.gpu.preflight -- <cmd...>
    from ..config import load_config, outputs_dir  # noqa: PLC0415
    from ..train.preview import preview_root  # noqa: PLC0415

    argv = sys.argv[2:] if len(sys.argv) > 1 and sys.argv[1] == "--" else sys.argv[1:]
    cfg = load_config()
    ps = preflight({"cmd": argv, "cwd": str(Path.cwd())}, outputs_dir(cfg), preview_root(cfg))
    print("\n".join(ps) if ps else "ok")
    raise SystemExit(1 if ps else 0)
