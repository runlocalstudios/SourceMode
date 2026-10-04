# Train the four approved sets back to back, in the order Jeremy set on 2026-10-03:
# vivienne then zara. Marisol and cici are HELD at his request (2026-10-03 13:50) -
# he needs the card for ollama to test the game chat tomorrow. Each run is 24 epochs
# plus the asset-prompt eval of epochs 16-24, so a judge set lands after each one
# rather than all at the end. Starts when Amanda's v4 pack releases the card.
# Never kills anything; a failed run does not stop the queue. ASCII only.
$ErrorActionPreference = "Continue"
# Repo paths, never a session scratchpad. These two used to point into one
# Claude session's temp directory, which meant (a) every script here broke the
# moment that directory was cleaned, and (b) an edit to the repo's
# train_character.ps1 was silently not picked up by the scripts that invoke it.
$SP  = "C:\dev\sourcemode\engine\scripts"
$EV  = "C:\dev\sourcemode\engine\scripts\eval"
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\train_queue_4.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
function Count { if (Test-Path "$L\amanda_assets.log") { @(Select-String -Path "$L\amanda_assets.log" -Pattern "AMANDAASSETSDONE").Count } else { 0 } }
Set-Location "C:\dev\sourcemode\engine"

$base = Count
Log "waiting for a NEW AMANDAASSETSDONE (already present: $base), 4h cap"
$w = 0
while ((Count) -le $base) { Start-Sleep 60; $w += 60; if ($w -ge 14400) { Log "4h passed - proceeding"; break } }

foreach ($char in @("vivienne", "zara")) {
  $w = 0
  while ($true) {
    $busy = @(Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'python*' -or $_.Name -like 'sourcemode*') -and
      ($_.CommandLine -like '*qwen_image_train_network*' -or $_.CommandLine -like '*dense_epoch_eval.py*' -or
       $_.CommandLine -like '*assets*render*' -or $_.CommandLine -like '*assets*cutout*' -or
       $_.CommandLine -like '*caption_from_vl*' -or $_.CommandLine -like '*hair_recheck*' -or
       $_.CommandLine -like '*loragen_local*') }).Count
    if ($busy -eq 0) { break }
    Start-Sleep 60; $w += 60; if ($w -gt 14400) { Log "card busy 4h - proceeding"; break }
  }
  # The gaze fix edited captions, which revokes approval by design. Wait for Jeremy
  # to re-approve rather than failing the slot and moving on (2026-10-03).
  $w = 0
  while ($true) {
    & uv run sourcemode train approved "${char}_v2" *> $null
    if ($LASTEXITCODE -eq 0) { break }
    if ($w -eq 0) { Log "waiting for $char to be re-approved (captions changed)" }
    Start-Sleep 60; $w += 60
    if ($w -gt 43200) { Log "SKIP $char - not re-approved in 12h"; break }
  }
  & uv run sourcemode train approved "${char}_v2" *> $null
  if ($LASTEXITCODE -ne 0) { Log "SKIP $char - unapproved"; continue }
  try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8188/free -ContentType application/json -Body '{"unload_models":true,"free_memory":true}' | Out-Null } catch {}
  Start-Sleep 10
  Log "START $char"
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SP\train_character.ps1" -Ds "${char}_v2" -Char $char
  Log "END $char exit=$LASTEXITCODE"
}
Log "TRAINQUEUE4DONE - vivienne, zara (marisol and cici held)"


