# Confirm the Codex Amanda LoRA's top two epochs at n=20 once the internal set's
# training + eval release the card. Jeremy's n=10 sweep (2026-10-01): ep17 8/10,
# ep19 7/10, ep23 6/10, the rest 3-4 - a noisy curve, and n=10 winners have been
# wrong 4/4 times. Scenes 0-9 are reused, 10-19 render: 20 frames, ~25 min.
# COUNT-based marker wait; never kills anything. ASCII only.
$ErrorActionPreference = "Continue"
# Repo paths, never a session scratchpad. These two used to point into one
# Claude session's temp directory, which meant (a) every script here broke the
# moment that directory was cleaned, and (b) an edit to the repo's
# train_character.ps1 was silently not picked up by the scripts that invoke it.
$SP  = "C:\dev\sourcemode\engine\scripts"
$EV  = "C:\dev\sourcemode\engine\scripts\eval"
$PY  = "C:\dev\sourcemode\engine\.venv\Scripts\python.exe"
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\amanda_codex_confirm.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
function Count { if (Test-Path "$L\amanda_internal_v2.log") { @(Select-String -Path "$L\amanda_internal_v2.log" -Pattern "AMANDA_INTERNAL_V2TRAINDONE").Count } else { 0 } }
Set-Location "C:\dev\sourcemode\engine"
$base = Count
Log "waiting for a NEW AMANDA_INTERNAL_V2TRAINDONE (already present: $base)"
$w = 0
while ((Count) -le $base) { Start-Sleep 60; $w += 60; if ($w -gt 64800) { Log "ABORT: internal training never finished in 18h"; exit 1 } }
$w = 0
while ($true) {
  $busy = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like 'python*' -and ($_.CommandLine -like '*qwen_image_train_network*' -or $_.CommandLine -like '*dense_epoch_eval.py*') }).Count
  if ($busy -eq 0) { break }
  Start-Sleep 60; $w += 60
  if ($w -gt 7200) { Log "card busy 2h after the marker - proceeding"; break }
}
try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8188/free -ContentType application/json -Body '{"unload_models":true,"free_memory":true}' | Out-Null } catch {}
Start-Sleep 10
$dir = "outputs\lora-datasets\amanda_v2\lora"
Log "START amanda_v2 confirm ep17,19 at n=20"
$p = Start-Process -FilePath $PY -NoNewWindow -Wait -PassThru -ArgumentList @(
      "$EV\dense_epoch_eval.py", "amanda", "amanda_v2", "24", "1", "24", "amanda", $dir, "20", "--epochs", "17,19") `
    -RedirectStandardOutput "$L\amanda_codex_confirm.stdout.log" -RedirectStandardError "$L\amanda_codex_confirm.stderr.log"
Log "END exit=$($p.ExitCode)  AMANDACODEXCONFIRMDONE"
