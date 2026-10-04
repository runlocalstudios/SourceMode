# Confirm Bianca's lr-2e-4 winner at n=20, once Maddie's eval releases the card.
#
# ep12 read 80% and ep24 read 80%, but that is the best of 21 arms at n=10 - the
# same shape as Hannah's 7/7 "tie" that turned out to be 30 points apart at n=20.
# Scenes 1-10 already exist for both arms and are reused; only 11-20 render.
#
# PowerShell, not a nohup'd bash script: every bash waiter launched from the agent
# tool today has died silently within hours, while Start-Process jobs (train_queue,
# character_chain) have run all day. ASCII only.
$ErrorActionPreference = "Continue"
$SP  = "C:\Users\jerem\AppData\Local\Temp\claude\C--dev-sourcemode\913e6b47-2e1a-4e0e-af1d-c0c28a922563\scratchpad"
$PY  = "C:\dev\sourcemode\engine\.venv\Scripts\python.exe"
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\bianca_confirm.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
Set-Location "C:\dev\sourcemode\engine"

Log "waiting for MADDIE_V2TRAINDONE (written after her eval, so the card is free)"
$w = 0
while (-not ((Test-Path "$L\maddie_v2.log") -and
             (Select-String -Path "$L\maddie_v2.log" -Pattern "MADDIE_V2TRAINDONE" -Quiet))) {
  Start-Sleep 60; $w += 60
  if ($w -gt 43200) { Log "ABORT: maddie never finished in 12h"; exit 1 }
}
Log "maddie done"

# The marker can land while something else still holds the card.
$w = 0
while ($true) {
  $busy = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like 'python*' -and ($_.CommandLine -like '*qwen_image_train_network*' -or
    $_.CommandLine -like '*dense_epoch_eval.py*') }).Count
  if ($busy -eq 0) { break }
  Start-Sleep 60; $w += 60
  if ($w -gt 10800) { Log "card busy 3h after the marker - proceeding anyway"; break }
}

try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8188/free -ContentType application/json -Body '{"unload_models":true,"free_memory":true}' | Out-Null } catch {}
Start-Sleep 10

Log "START bianca ep12 vs ep24 at n=20"
$p = Start-Process -FilePath $PY -NoNewWindow -Wait -PassThru -ArgumentList @(
      "$SP\dense_epoch_eval.py", "bianca", "bianca_lr2", "24", "12", "24", "bianca",
      "outputs\lora-datasets\bianca_v2\lora_bianca_lr2", "20",
      "--scenes", "favorable", "--epochs", "12,24") `
    -RedirectStandardOutput "$L\confirm_bianca.stdout.log" `
    -RedirectStandardError  "$L\confirm_bianca.stderr.log"
Log "END exit=$($p.ExitCode)  BIANCACONFIRMDONE"
