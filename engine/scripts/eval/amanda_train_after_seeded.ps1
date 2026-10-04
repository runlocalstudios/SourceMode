# Train amanda_v2 (the approved Codex set, 73 images) once the seeded generation has
# released the card. Launched explicitly rather than via train_queue: the queue is
# stopped, and if restarted it would pick sunny_v2 first (her checkpoints were lost
# to the unnumbered-final prune bug, so she reads as untrained) - a 5.5h run Jeremy
# has not asked for. Marker wait is COUNT-based. ASCII only.
$ErrorActionPreference = "Continue"
# Repo paths, never a session scratchpad. These two used to point into one
# Claude session's temp directory, which meant (a) every script here broke the
# moment that directory was cleaned, and (b) an edit to the repo's
# train_character.ps1 was silently not picked up by the scripts that invoke it.
$SP  = "C:\dev\sourcemode\engine\scripts"
$EV  = "C:\dev\sourcemode\engine\scripts\eval"
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\amanda_train_wait.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
function Count { if (Test-Path "$L\amanda_seeded.log") { @(Select-String -Path "$L\amanda_seeded.log" -Pattern "AMANDASEEDEDDONE").Count } else { 0 } }
Set-Location "C:\dev\sourcemode\engine"

$base = Count
Log "waiting for a NEW AMANDASEEDEDDONE (already present: $base)"
$w = 0
while ((Count) -le $base) { Start-Sleep 60; $w += 60; if ($w -gt 72000) { Log "ABORT: seeded run never finished in 20h"; exit 1 } }
$w = 0
while ($true) {
  $busy = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like 'python*' -and ($_.CommandLine -like '*caption_from_vl*' -or $_.CommandLine -like '*hair_confirm2*' -or $_.CommandLine -like '*caption_images_by_qwen*' -or $_.CommandLine -like '*qwen_image_train_network*' -or
    $_.CommandLine -like '*dense_epoch_eval.py*' -or $_.CommandLine -like '*loragen_local*') }).Count
  if ($busy -eq 0) { break }
  Start-Sleep 60; $w += 60
  if ($w -gt 7200) { Log "card busy 2h after the marker - proceeding"; break }
}
Log "START amanda_v2 training"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SP\train_character.ps1" -Ds amanda_v2 -Char amanda
Log "END amanda_v2 exit=$LASTEXITCODE  AMANDATRAINWAITDONE"
