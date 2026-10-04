# Train daisy_v2 (approved 2026-10-02) once Cici's caption passes have had the card -
# they take ~20 min and would otherwise wait 5 h behind training. Waits for a NEW
# CICIDONE, or 90 minutes, whichever comes first, then an idle card. ASCII only.
$ErrorActionPreference = "Continue"
# Repo paths, never a session scratchpad. These two used to point into one
# Claude session's temp directory, which meant (a) every script here broke the
# moment that directory was cleaned, and (b) an edit to the repo's
# train_character.ps1 was silently not picked up by the scripts that invoke it.
$SP  = "C:\dev\sourcemode\engine\scripts"
$EV  = "C:\dev\sourcemode\engine\scripts\eval"
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\daisy_train_wait.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
function Count { if (Test-Path "$L\chain_cici.log") { @(Select-String -Path "$L\chain_cici.log" -Pattern "CICIDONE").Count } else { 0 } }
Set-Location "C:\dev\sourcemode\engine"
$base = Count
Log "waiting for a NEW CICIDONE (already present: $base), 90 min cap"
$w = 0
while ((Count) -le $base) { Start-Sleep 60; $w += 60; if ($w -ge 5400) { Log "90 min passed - not waiting for cici any longer"; break } }
$w = 0
while ($true) {
  $busy = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like 'python*' -and ($_.CommandLine -like '*caption_from_vl*' -or $_.CommandLine -like '*hair_confirm2*' -or $_.CommandLine -like '*qwen_image_train_network*' -or $_.CommandLine -like '*dense_epoch_eval.py*' -or $_.CommandLine -like '*loragen_local*') }).Count
  if ($busy -eq 0) { break }
  Start-Sleep 60; $w += 60
  if ($w -gt 7200) { Log "card busy 2h - proceeding"; break }
}
Log "START daisy_v2 training"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SP\train_character.ps1" -Ds daisy_v2 -Char daisy
Log "END daisy_v2 exit=$LASTEXITCODE  DAISYTRAINWAITDONE"
