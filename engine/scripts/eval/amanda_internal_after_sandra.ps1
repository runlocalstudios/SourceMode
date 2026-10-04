# Amanda's 80-shot INTERNAL set (arm C hair recipe, fitted outfits, appearance
# clause) once Sandra's three-quarter re-render releases the card. Jeremy judged
# arm C 'solid' on 2026-10-01 and asked for closer, chest-up framing where possible.
# Output goes to the judge set cull_amanda_internal. COUNT-based wait, never kills
# anything. ASCII only.
$ErrorActionPreference = "Continue"
$PY  = "C:\dev\sourcemode\engine\.venv\Scripts\python.exe"
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\amanda_internal.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
function Count { if (Test-Path "$L\sandra_assets.log") { @(Select-String -Path "$L\sandra_assets.log" -Pattern "SANDRAASSETSDONE").Count } else { 0 } }
Set-Location "C:\dev\sourcemode\engine"

$base = Count
Log "waiting for a NEW SANDRAASSETSDONE (already present: $base)"
$w = 0
while ((Count) -le $base) { Start-Sleep 60; $w += 60; if ($w -gt 64800) { Log "ABORT: sandra never finished in 18h"; exit 1 } }
Log "sandra assets done"
$w = 0
while ($true) {
  $busy = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like 'python*' -and ($_.CommandLine -like '*caption_from_vl*' -or $_.CommandLine -like '*hair_confirm2*' -or $_.CommandLine -like '*caption_images_by_qwen*' -or $_.CommandLine -like '*sourcemode*assets*' -or $_.CommandLine -like '*qwen_image_train_network*' -or
    $_.CommandLine -like '*dense_epoch_eval.py*') }).Count
  if ($busy -eq 0) { break }
  Start-Sleep 60; $w += 60
  if ($w -gt 10800) { Log "card busy 3h after the marker - proceeding"; break }
}
try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8188/free -ContentType application/json -Body '{"unload_models":true,"free_memory":true}' | Out-Null } catch {}
Start-Sleep 10

Log "START amanda INTERNAL generation (80 shots, arm C recipe, fitted outfits, appearance clause)"
$p = Start-Process -FilePath $PY -NoNewWindow -Wait -PassThru -ArgumentList @(
      "scripts\eval\loragen_local.py", "amanda", "--seeds", "outputs\seeds\amanda", "--internal") `
    -RedirectStandardOutput "$L\amanda_internal.stdout.log" -RedirectStandardError "$L\amanda_internal.stderr.log"
Log "END generation exit=$($p.ExitCode)"
if ($p.ExitCode -ne 0) { Log "generation FAILED - no judge set"; exit 1 }

Log "building judge set cull_amanda_internal"
$q = Start-Process -FilePath $PY -NoNewWindow -Wait -PassThru -ArgumentList @("scripts\eval\amanda_seeded_judgeset.py", "cull_amanda_internal", "outputs\loragen_local\amanda_internal") `
    -RedirectStandardOutput "$L\amanda_internal_judge.stdout.log" -RedirectStandardError "$L\amanda_internal_judge.stderr.log"
Log "END judge set exit=$($q.ExitCode)  AMANDAINTERNALDONE"
