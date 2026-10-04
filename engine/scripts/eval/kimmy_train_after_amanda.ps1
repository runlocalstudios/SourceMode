# Train kimmy_v2 (approved 2026-10-02) overnight, after Amanda's v3 pack releases the
# card. Jeremy, 2026-10-03 01:20: "train kimmy when the GPU is freed up i'm goin to
# bed". 78 images x 2 repeats = 156 steps/epoch, 24 epochs, then the asset-prompt eval
# (epochs 16-24) so a judge set is waiting in the morning. COUNT-based marker wait plus
# an idle check; never kills anything. ASCII only.
$ErrorActionPreference = "Continue"
# Repo paths, never a session scratchpad. These two used to point into one
# Claude session's temp directory, which meant (a) every script here broke the
# moment that directory was cleaned, and (b) an edit to the repo's
# train_character.ps1 was silently not picked up by the scripts that invoke it.
$SP  = "C:\dev\sourcemode\engine\scripts"
$EV  = "C:\dev\sourcemode\engine\scripts\eval"
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\kimmy_train_wait.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
function Count { if (Test-Path "$L\amanda_assets.log") { @(Select-String -Path "$L\amanda_assets.log" -Pattern "AMANDAASSETSDONE").Count } else { 0 } }
Set-Location "C:\dev\sourcemode\engine"
$base = Count
Log "waiting for a NEW AMANDAASSETSDONE (already present: $base), 6h cap"
$w = 0
while ((Count) -le $base) { Start-Sleep 60; $w += 60; if ($w -ge 21600) { Log "6h passed - proceeding without the marker"; break } }
$w = 0
while ($true) {
  $busy = @(Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'python*' -or $_.Name -like 'sourcemode*') -and
    ($_.CommandLine -like '*qwen_image_train_network*' -or $_.CommandLine -like '*dense_epoch_eval.py*' -or
     $_.CommandLine -like '*assets*render*' -or $_.CommandLine -like '*assets*cutout*' -or
     $_.CommandLine -like '*caption_from_vl*' -or $_.CommandLine -like '*hair_recheck*' -or
     $_.CommandLine -like '*loragen_local*') }).Count
  if ($busy -eq 0) { break }
  Start-Sleep 60; $w += 60; if ($w -gt 10800) { Log "card busy 3h - proceeding"; break }
}
try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8188/free -ContentType application/json -Body '{"unload_models":true,"free_memory":true}' | Out-Null } catch {}
Start-Sleep 10
Log "START kimmy_v2 training"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SP\train_character.ps1" -Ds kimmy_v2 -Char kimmy
Log "END kimmy_v2 exit=$LASTEXITCODE  KIMMYTRAINWAITDONE"
