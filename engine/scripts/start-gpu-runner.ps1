# Start the single GPU job runner. It takes one job at a time from
# outputs/gpu-queue/queue.json, in that file's order, and waits - indefinitely -
# while anything else is using the card. A second instance refuses to start,
# because the first holds outputs/gpu-queue/runner.lease.
#
# The runner writes its own UTF-8 log at outputs/logs/gpu-runner.log. The
# redirect below is only for stray console output, and PowerShell's *>> writes
# UTF-16, so read gpu-runner.log - not this one.
$ErrorActionPreference = "Continue"
$log = "C:\dev\sourcemode\engine\outputs\logs"
New-Item -ItemType Directory -Force -Path $log | Out-Null
Set-Location "C:\dev\sourcemode\engine"
$uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
if (-not (Test-Path $uv)) { $uv = "uv" }
& $uv run sourcemode gpu run *>> "$log\gpu-runner.console.log"
