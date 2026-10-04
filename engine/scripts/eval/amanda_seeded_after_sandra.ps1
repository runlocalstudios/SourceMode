# Amanda's 80-shot set from the four REAL hair seeds, once Sandra releases the card.
#
# Jeremy's strategy, 2026-09-30: four high-fidelity front-facing Grok shots, one
# per hairstyle, each with its own outfit and background, so every generated image
# is ONE step from a real photo. All four are identity-gated (0.78-1.00 vs her,
# nearest other identity <= 0.56). Earrings on the half-up and bun seeds are faint
# and he accepted them; the ponytail seed was replaced to remove them.
#
# Output goes to a JUDGE SET, not straight to captioning: this generator is not yet
# trusted the way Codex is ("not all of the photos look like her"), so he culls
# blind first. The keepers get captioned afterwards.
#
# Marker wait is COUNT-based and a second guard waits for an idle card, because the
# marker lands before the eval releases the GPU. PowerShell, not nohup'd bash.
# ASCII only.
$ErrorActionPreference = "Continue"
$PY  = "C:\dev\sourcemode\engine\.venv\Scripts\python.exe"
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\amanda_seeded.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
function Count { if (Test-Path "$L\sandra_v2.log") { @(Select-String -Path "$L\sandra_v2.log" -Pattern "SANDRA_V2TRAINDONE").Count } else { 0 } }
Set-Location "C:\dev\sourcemode\engine"

$base = Count
Log "waiting for a NEW SANDRA_V2TRAINDONE (already present: $base)"
$w = 0
while ((Count) -le $base) { Start-Sleep 60; $w += 60; if ($w -gt 64800) { Log "ABORT: sandra never finished in 18h"; exit 1 } }
Log "sandra done"
$w = 0
while ($true) {
  $busy = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like 'python*' -and ($_.CommandLine -like '*caption_from_vl*' -or $_.CommandLine -like '*hair_confirm2*' -or $_.CommandLine -like '*caption_images_by_qwen*' -or $_.CommandLine -like '*qwen_image_train_network*' -or
    $_.CommandLine -like '*dense_epoch_eval.py*') }).Count
  if ($busy -eq 0) { break }
  Start-Sleep 60; $w += 60
  if ($w -gt 10800) { Log "card busy 3h after the marker - proceeding"; break }
}
try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8188/free -ContentType application/json -Body '{"unload_models":true,"free_memory":true}' | Out-Null } catch {}
Start-Sleep 10

Log "START amanda seeded generation (80 shots, 4 real seeds)"
$p = Start-Process -FilePath $PY -NoNewWindow -Wait -PassThru -ArgumentList @(
      "scripts\eval\loragen_local.py", "amanda", "--seeds", "outputs\seeds\amanda") `
    -RedirectStandardOutput "$L\amanda_seeded.stdout.log" -RedirectStandardError "$L\amanda_seeded.stderr.log"
Log "END generation exit=$($p.ExitCode)"
if ($p.ExitCode -ne 0) { Log "generation FAILED - no judge set"; exit 1 }

Log "building judge set cull_amanda_seeded"
$q = Start-Process -FilePath $PY -NoNewWindow -Wait -PassThru -ArgumentList @("scripts\eval\amanda_seeded_judgeset.py") `
    -RedirectStandardOutput "$L\amanda_seeded_judge.stdout.log" -RedirectStandardError "$L\amanda_seeded_judge.stderr.log"
Log "END judge set exit=$($q.ExitCode)  AMANDASEEDEDDONE"
