# Re-evaluate BOTH Amanda LoRAs on the favorable scene set, which should have been
# used in the first place (Jeremy shelved the bare sweep on 2026-09-28; the
# microphone / drum-kit scenes produce junk that says nothing about the LoRA).
# Runs after Sandra's three-look redo releases the card. Never kills anything.
$ErrorActionPreference = "Continue"
# Repo paths, never a session scratchpad. These two used to point into one
# Claude session's temp directory, which meant (a) every script here broke the
# moment that directory was cleaned, and (b) an edit to the repo's
# train_character.ps1 was silently not picked up by the scripts that invoke it.
$SP  = "C:\dev\sourcemode\engine\scripts"
$EV  = "C:\dev\sourcemode\engine\scripts\eval"
$PY  = "C:\dev\sourcemode\engine\.venv\Scripts\python.exe"
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\amanda_fav_reeval.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
function Free { try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8188/free -ContentType application/json -Body '{"unload_models":true,"free_memory":true}' | Out-Null } catch {}; Start-Sleep 10 }
Set-Location "C:\dev\sourcemode\engine"
$w = 0
while ($true) {
  $busy = @(Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'python*' -or $_.Name -like 'sourcemode*') -and ($_.CommandLine -like '*qwen_image_train_network*' -or $_.CommandLine -like '*dense_epoch_eval.py*' -or $_.CommandLine -like '*assets*render*' -or $_.CommandLine -like '*assets*cutout*') }).Count
  if ($busy -eq 0) { break }
  Start-Sleep 60; $w += 60; if ($w -gt 7200) { Log "card busy 2h - proceeding"; break }
}
# Jeremy, 2026-10-02: internal 20-22, Codex 17-19.
foreach ($j in @(@{ Sub = "amanda_internal_v2"; Eps = "20,21,22" }, @{ Sub = "amanda_v2"; Eps = "17,18,19" })) {
  $dir = "outputs\lora-datasets\$($j.Sub)\lora"
  Free
  Log "START $($j.Sub) asset-prompt eval, epochs $($j.Eps) x 10"
  $p = Start-Process -FilePath $PY -NoNewWindow -Wait -PassThru -ArgumentList @(
        "$EV\dense_epoch_eval.py", "amanda", $j.Sub, "24", "1", "24", "amanda", $dir, "10", "--scenes", "asset", "--epochs", $j.Eps) `
      -RedirectStandardOutput "$L\asset_$($j.Sub).stdout.log" -RedirectStandardError "$L\asset_$($j.Sub).stderr.log"
  Log "END $($j.Sub) exit=$($p.ExitCode)"
}
Log "AMANDAFAVREEVALDONE - judge sets dense_amanda_internal_v2_asset and dense_amanda_v2_asset"
