# Start the engine monitor (GPU / ComfyUI / training readout on :8787).
# Bind address comes from [monitor] in engine/config.toml; override with
# $env:SOURCEMODE_MONITOR_HOST (e.g. the Tailscale address) before launching.
$ErrorActionPreference = "Continue"
$log = "C:\dev\sourcemode\engine\outputs\logs"
New-Item -ItemType Directory -Force -Path $log | Out-Null
Set-Location "C:\dev\sourcemode\engine"
$uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
if (-not (Test-Path $uv)) { $uv = "uv" }
& $uv run sourcemode monitor serve *>> "$log\monitor.log"
