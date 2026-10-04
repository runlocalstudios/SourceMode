# Daisy extension: 8 more epochs warm-started from the ep24 weights, evaluated as
# epochs 25-32 on the asset prompts. Her sweep was still climbing at ep24 (0,0,0,1,3,2,
# 2,3,3 of 10) - the undertrained shape, not a bad character. Jeremy, 2026-10-02:
# "cue that up after the current pack and then the captions" - so it waits for
# Amanda's v2 pack (a NEW AMANDAASSETSDONE) and Marisol's captions (MARISOLDONE),
# then an idle card. Never kills anything. ASCII only.
$ErrorActionPreference = "Continue"
# Repo paths, never a session scratchpad. These two used to point into one
# Claude session's temp directory, which meant (a) every script here broke the
# moment that directory was cleaned, and (b) an edit to the repo's
# train_character.ps1 was silently not picked up by the scripts that invoke it.
$SP  = "C:\dev\sourcemode\engine\scripts"
$EV  = "C:\dev\sourcemode\engine\scripts\eval"
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\daisy_extend.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
function CountA { if (Test-Path "$L\amanda_assets.log") { @(Select-String -Path "$L\amanda_assets.log" -Pattern "AMANDAASSETSDONE").Count } else { 0 } }
function CountM { if (Test-Path "$L\chain_marisol.log") { @(Select-String -Path "$L\chain_marisol.log" -Pattern "MARISOLDONE").Count } else { 0 } }
Set-Location "C:\dev\sourcemode\engine"
$baseA = CountA
Log "waiting for a NEW AMANDAASSETSDONE (already present: $baseA) and MARISOLDONE"
$w = 0
while (((CountA) -le $baseA) -or ((CountM) -lt 1)) { Start-Sleep 60; $w += 60; if ($w -gt 43200) { Log "ABORT: 12h"; exit 1 } }
$w = 0
while ($true) {
  $busy = @(Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'python*' -or $_.Name -like 'sourcemode*') -and
    ($_.CommandLine -like '*qwen_image_train_network*' -or $_.CommandLine -like '*dense_epoch_eval.py*' -or $_.CommandLine -like '*caption_from_vl*' -or
     $_.CommandLine -like '*hair_confirm2*' -or $_.CommandLine -like '*assets*render*' -or $_.CommandLine -like '*assets*cutout*') }).Count
  if ($busy -eq 0) { break }
  Start-Sleep 60; $w += 60; if ($w -gt 7200) { Log "card busy 2h - proceeding"; break }
}
Log "START daisy extension, 8 epochs from daisy_v2.safetensors"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SP\train_character.ps1" `
    -Ds daisy_v2 -Char daisy -OutName daisy_ext -Epochs 8 `
    -Resume "C:\dev\sourcemode\engine\outputs\lora-datasets\daisy_v2\lora\daisy_v2.safetensors" `
    -EvalStart 1 -EvalEnd 8 -EvalOffset 24
Log "END exit=$LASTEXITCODE  DAISYEXTDONE"
