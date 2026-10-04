# Run the hair-conformance test once Sandra's assets release the card. COUNT-based
# marker wait; never kills anything. ASCII only.
$ErrorActionPreference = "Continue"
$PY  = "C:\dev\sourcemode\engine\.venv\Scripts\python.exe"
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\amanda_conformance.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
function Count { if (Test-Path "$L\sandra_assets.log") { @(Select-String -Path "$L\sandra_assets.log" -Pattern "SANDRAASSETSDONE").Count } else { 0 } }
Set-Location "C:\dev\sourcemode\engine"
$base = Count
Log "waiting for a NEW SANDRAASSETSDONE (already present: $base)"
$w = 0
while ((Count) -le $base) { Start-Sleep 60; $w += 60; if ($w -gt 43200) { Log "ABORT: sandra assets never finished in 12h"; exit 1 } }
$w = 0
while ($true) {
  $busy = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like 'python*' -and ($_.CommandLine -like '*qwen_image_train_network*' -or $_.CommandLine -like '*dense_epoch_eval.py*' -or
    $_.CommandLine -like '*sourcemode*assets*' -or $_.CommandLine -like '*caption_from_vl*' -or $_.CommandLine -like '*loragen_local*') }).Count
  if ($busy -eq 0) { break }
  Start-Sleep 60; $w += 60
  if ($w -gt 7200) { Log "card busy 2h after the marker - proceeding"; break }
}
try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8188/free -ContentType application/json -Body '{"unload_models":true,"free_memory":true}' | Out-Null } catch {}
Start-Sleep 10
Log "START amanda conformance test (4 arms x 4)"
$p = Start-Process -FilePath $PY -NoNewWindow -Wait -PassThru -ArgumentList @("scripts\eval\amanda_conformance.py") `
     -RedirectStandardOutput "$L\amanda_conformance.stdout.log" -RedirectStandardError "$L\amanda_conformance.stderr.log"
Log "END exit=$($p.ExitCode)  AMANDACONFDONE"
