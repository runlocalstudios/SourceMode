# Restart the monitor onto its scheduled task, and prove the new code is live.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\restart-monitor.ps1 [-Expect <text>]
#
# Stop-ScheduledTask does NOT stop the monitor: the uv -> sourcemode -> python
# tree keeps port 8787, the restarted task cannot bind, and the page serves the
# old code (2026-10-05, and about fifteen hand restarts since). So: kill the tree
# that owns the port, then start the task - never a hand launch, because the
# bind address comes from the user env var SOURCEMODE_MONITOR_HOST=0.0.0.0 that a
# session shell does not inherit, and a hand launch binds loopback and silently
# cuts Tailscale access from the phone.
#
# -Expect <text>: a string that must appear in the served hub page after the
# restart - a new tab name, a new route - so "restarted" cannot mean "serving
# yesterday's file". Fails (exit 1) if the monitor does not answer or the text
# is missing. ASCII only.
param([string]$Expect = "")
$ErrorActionPreference = "Continue"
function Log($m) { Write-Output ("{0}  {1}" -f (Get-Date -Format s), $m) }

$port = 8787
$runnerLease = "C:\dev\sourcemode\engine\outputs\gpu-queue\runner.lease"
$runnerPid = 0
if (Test-Path $runnerLease) {
  try { $runnerPid = [int]((Get-Content $runnerLease -Raw | ConvertFrom-Json).pid) } catch {}
}

$pids = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
          Select-Object -ExpandProperty OwningProcess -Unique)
foreach ($p in $pids) {
  # The GPU runner is a sibling logon task, never part of this tree - but a
  # wrong PID here would kill a training, so refuse outright if it ever matches.
  if ($runnerPid -and $p -eq $runnerPid) { Log "ABORT: port $port is owned by the GPU runner (PID $p)"; exit 1 }
  $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$p").CommandLine
  Log "stopping PID $p : $cmd"
  & taskkill.exe /PID $p /T /F | Out-Null
}
for ($i = 0; $i -lt 30; $i++) {
  if (-not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) { break }
  Start-Sleep 2
}
if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
  Log "ABORT: port $port is still held after stopping $($pids -join ', ')"
  exit 1
}

Stop-ScheduledTask -TaskName "SourceMode Monitor" -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName "SourceMode Monitor"
Log "started task SourceMode Monitor; waiting for it to answer"

for ($i = 0; $i -lt 36; $i++) {
  try {
    Invoke-RestMethod -Uri "http://127.0.0.1:$port/healthz" -TimeoutSec 5 | Out-Null
    break
  } catch { Start-Sleep 5 }
  if ($i -eq 35) { Log "FAILED: monitor did not answer on $port within 3 minutes - see outputs\logs\monitor.err.log"; exit 1 }
}
$who = (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess
Log "monitor is up on $port (PID $who, from its task)"

if ($Expect) {
  $body = ""
  try { $body = (Invoke-WebRequest -Uri "http://127.0.0.1:$port/" -TimeoutSec 10 -UseBasicParsing).Content } catch {}
  if ($body -notlike "*$Expect*") {
    Log "FAILED: the served page does not contain '$Expect' - the restart is serving old code"
    exit 1
  }
  Log "served page contains '$Expect' - the new code is live"
}
exit 0
