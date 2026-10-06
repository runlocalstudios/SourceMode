# Restart ComfyUI onto its scheduled task (headless, logs to outputs/logs/comfyui.log).
#
# Queued, never run by hand: the queue runs one job at a time, so nothing else is
# using ComfyUI when this stops it. Jeremy, 2026-10-06: ComfyUI was running from a
# hand-started shell, not from "SourceMode ComfyUI", so the conhost --headless
# change could not reach it until it was restarted.
#
# Fails (exit 1) if ComfyUI does not answer again - a restart that leaves the
# renderer down must not read as done.
$ErrorActionPreference = "Continue"
function Log($m) { Write-Output ("{0}  {1}" -f (Get-Date -Format s), $m) }

$port = 8188
$pids = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
          Select-Object -ExpandProperty OwningProcess -Unique)
foreach ($p in $pids) {
  $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$p").CommandLine
  Log "stopping PID $p : $cmd"
  & taskkill.exe /PID $p /T /F | Out-Null
}
# the port must actually be free before the task starts, or it cannot bind
for ($i = 0; $i -lt 30; $i++) {
  if (-not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) { break }
  Start-Sleep 2
}
if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
  Log "ABORT: port $port is still held after stopping $($pids -join ', ')"
  exit 1
}

Stop-ScheduledTask -TaskName "SourceMode ComfyUI" -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName "SourceMode ComfyUI"
Log "started task SourceMode ComfyUI; waiting for it to answer"

for ($i = 0; $i -lt 60; $i++) {
  try {
    Invoke-RestMethod -Uri "http://127.0.0.1:$port/system_stats" -TimeoutSec 5 | Out-Null
    Log "ComfyUI is up on $port (from its task, headless)"
    exit 0
  } catch { Start-Sleep 5 }
}
Log "FAILED: ComfyUI did not answer on $port within 5 minutes - see outputs\logs\comfyui.log"
exit 1
