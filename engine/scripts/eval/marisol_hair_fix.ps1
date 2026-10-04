# Re-ask Marisol's braid / pigtail captions against the images, rewrite the hair
# clause and rebuild her preview. Her hair is a short lob, so every long-hair entry
# in the shot plan was silently substituted by the generator and the captions kept
# the plan's word. ~3 min of VL on the card; waits for it to be idle first and never
# kills anything. ASCII only.
$ErrorActionPreference = "Continue"
$PY  = "C:\dev\sourcemode\engine\.venv\Scripts\python.exe"
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\marisol_hair_fix.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
Set-Location "C:\dev\sourcemode\engine"
$w = 0
while ($true) {
  $busy = @(Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'python*' -or $_.Name -like 'sourcemode*') -and
    ($_.CommandLine -like '*qwen_image_train_network*' -or $_.CommandLine -like '*dense_epoch_eval.py*' -or
     $_.CommandLine -like '*assets*render*' -or $_.CommandLine -like '*assets*cutout*' -or
     $_.CommandLine -like '*caption_from_vl*' -or $_.CommandLine -like '*loragen_local*') }).Count
  if ($busy -eq 0) { break }
  Start-Sleep 30; $w += 30; if ($w -gt 21600) { Log "card busy 6h - proceeding"; break }
}
try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8188/free -ContentType application/json -Body '{"unload_models":true,"free_memory":true}' | Out-Null } catch {}
Start-Sleep 5
Log "START marisol hair recheck"
$p = Start-Process -FilePath $PY -NoNewWindow -Wait -PassThru -ArgumentList @("scripts\eval\hair_recheck.py", "marisol", "--apply") `
     -RedirectStandardOutput "$L\marisol_hair_recheck.stdout.log" -RedirectStandardError "$L\marisol_hair_recheck.stderr.log"
Log "END recheck exit=$($p.ExitCode)"
if ($p.ExitCode -ne 0) { Log "recheck FAILED - preview not rebuilt"; exit 1 }
$q = Start-Process -FilePath $PY -NoNewWindow -Wait -PassThru -ArgumentList @("scripts\eval\preview_named.py", "marisol_v2", "marisol") `
     -RedirectStandardOutput "$L\marisol_preview2.stdout.log" -RedirectStandardError "$L\marisol_preview2.stderr.log"
Log "END preview exit=$($q.ExitCode)  MARISOLHAIRFIXDONE - back on the Training sets tab"
