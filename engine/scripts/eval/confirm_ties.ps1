# Confirm the top two arms of the four unresolved ties at n=20, then they can be
# pruned. 24 checkpoints each, ~100 GB held between them, and none has a chosen
# winner so none is usable.
#
# Jeremy, 2026-09-29: "no LoRA will ever perfectly capture a character, so it gets
# back to what gets close enough and we work from there." Right - and the numbers
# agree: at 10 candidates per shot, a 60% epoch misses a keeper once in 10,000 and a
# 75% epoch once in a million. Epoch choice buys render COST (1.67 vs 1.33 renders
# per keeper), not feasibility. So this is a pick-the-better-of-two exercise, not a
# hunt for a perfect epoch - confirm, choose, prune, move on.
#
# All four were originally judged on the STANDARD scene set, so no --scenes here;
# mixing scene sets would make the numbers incomparable. Scenes 0-9 already exist
# for every arm and are reused - only 10-19 render, 20 new frames per character.
#
# Waits for Bianca's extension to finish first. ASCII only.
$ErrorActionPreference = "Continue"
$SP  = "C:\Users\jerem\AppData\Local\Temp\claude\C--dev-sourcemode\913e6b47-2e1a-4e0e-af1d-c0c28a922563\scratchpad"
$PY  = "C:\dev\sourcemode\engine\.venv\Scripts\python.exe"
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\confirm_ties.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
function Free { try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8188/free -ContentType application/json -Body '{"unload_models":true,"free_memory":true}' | Out-Null } catch {}; Start-Sleep 10 }
Set-Location "C:\dev\sourcemode\engine"

# top two arms from each character's judged n=10 sweep
$jobs = @(
  @{ Char = "bianca"; Sub = "bianca_v2"; Eps = "21,20" },   # 5/10 then 4/10
  @{ Char = "raven";  Sub = "raven_v2";  Eps = "22,21" },   # 7/10 and 7/10 - a real tie
  @{ Char = "sunny";  Sub = "sunny_v2";  Eps = "24,23" },   # 6/10 and 6/10 - a real tie
  @{ Char = "keiko";  Sub = "keiko_v2";  Eps = "22,20" }    # 4/10 then 2/10, weak character
)

Log "waiting for the card"
$w = 0
while ($true) {
  $busy = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like 'python*' -and ($_.CommandLine -like '*qwen_image_train_network*' -or
    $_.CommandLine -like '*dense_epoch_eval.py*') }).Count
  if ($busy -eq 0) { break }
  Start-Sleep 60; $w += 60
  if ($w -gt 28800) { Log "card busy 8h - proceeding anyway"; break }
}

foreach ($j in $jobs) {
  $dir = "outputs\lora-datasets\$($j.Sub)\lora"
  if (-not (Test-Path $dir)) { Log "SKIP $($j.Char): no $dir"; continue }
  $n = @(Get-ChildItem "$dir\*.safetensors" -ErrorAction SilentlyContinue).Count
  if ($n -eq 0) { Log "SKIP $($j.Char): no checkpoints"; continue }
  Free
  Log "START $($j.Char) epochs $($j.Eps) at n=20 ($n checkpoints on disk)"
  $p = Start-Process -FilePath $PY -NoNewWindow -Wait -PassThru -ArgumentList @(
        "$SP\dense_epoch_eval.py", $j.Char, $j.Sub, "24", "1", "24", $j.Char,
        $dir, "20", "--epochs", $j.Eps) `
      -RedirectStandardOutput "$L\confirm_$($j.Sub).stdout.log" `
      -RedirectStandardError  "$L\confirm_$($j.Sub).stderr.log"
  Log "END $($j.Char) exit=$($p.ExitCode)"
}
Log "CONFIRMTIESDONE - four judge sets waiting"
