# Sandra's 28 game assets, once Amanda's training+eval release the card.
#
# Jeremy, 2026-09-30: "Train Sandra first and generate all the game assets to fill
# in her outfits, then remove the backgrounds... show me the final game assets".
# He judged her sweep: ep21 7/10, ep22 6/10 (n=10) and accepted ep21 outright. Pipeline: plan -> render -> cutout --game -> place
# -> white review sheet. Nothing touches the game repo. Marker wait is COUNT-based.
# Never kills anything on the card. ASCII only.
param([switch]$Now)
$ErrorActionPreference = "Continue"
$SP  = "C:\Users\jerem\AppData\Local\Temp\claude\C--dev-sourcemode\913e6b47-2e1a-4e0e-af1d-c0c28a922563\scratchpad"
$PY  = "C:\dev\sourcemode\engine\.venv\Scripts\python.exe"
$UV  = (Get-Command uv).Source
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\sandra_assets.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
function Count { if (Test-Path "$L\amanda_v2.log") { @(Select-String -Path "$L\amanda_v2.log" -Pattern "AMANDA_V2TRAINDONE").Count } else { 0 } }
function Free { try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8188/free -ContentType application/json -Body '{"unload_models":true,"free_memory":true}' | Out-Null } catch {}; Start-Sleep 10 }
# $args is PowerShell's AUTOMATIC variable - naming a parameter $args leaves it empty
# and Start-Process throws a binding error. Never name a parameter $args.
function Run($label, $exe, $argv, $tag) {
  Log "START $label"
  $p = Start-Process -FilePath $exe -NoNewWindow -Wait -PassThru -ArgumentList $argv `
       -RedirectStandardOutput "$L\$tag.stdout.log" -RedirectStandardError "$L\$tag.stderr.log"
  Log "END $label exit=$($p.ExitCode)"
  return $p.ExitCode
}
Set-Location "C:\dev\sourcemode\engine"

$base = Count
if ($Now) { $base = -1; Log "-Now: not waiting for a marker" } else { Log "waiting for a NEW AMANDA_V2TRAINDONE (already present: $base)" }
$w = 0
while ((Count) -le $base) { Start-Sleep 60; $w += 60; if ($w -gt 64800) { Log "ABORT: amanda never finished in 18h"; exit 1 } }
$w = 0
while ($true) {
  $busy = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like 'python*' -and ($_.CommandLine -like '*qwen_image_train_network*' -or $_.CommandLine -like '*dense_epoch_eval.py*' -or
    $_.CommandLine -like '*caption_from_vl*' -or $_.CommandLine -like '*hair_confirm2*' -or $_.CommandLine -like '*loragen_local*') }).Count
  if ($busy -eq 0) { break }
  Start-Sleep 60; $w += 60
  if ($w -gt 10800) { Log "card busy 3h after the marker - proceeding"; break }
}
Free

# Jeremy, 2026-09-30 20:05: 'Just accept Sandra ep 21 it's fine' - no n=20 confirm.
# 2. the assets on ep21
$plan = "outputs\game-assets\sandra\plan_28.json"
$rc = Run "sandra render 28 looks x 2" $UV @("run", "sourcemode", "assets", "render", "--plan", $plan, "--out", "outputs\game-assets", "--shots", "2") "sandra_render"
if ($rc -ne 0) { Log "render FAILED - stopping before cutout"; exit 1 }
Free
Run "sandra cutout --game" $UV @("run", "sourcemode", "assets", "cutout", "outputs\game-assets\sandra\renders", "--out", "outputs\game-assets\sandra\cutouts", "--game") "sandra_cutout" | Out-Null
Run "sandra place" $UV @("run", "sourcemode", "assets", "place", "--plan", $plan, "--cutouts", "outputs\game-assets\sandra\cutouts", "--out", "outputs\game-assets") "sandra_place" | Out-Null
Run "sandra white sheet" $PY @("scripts\eval\white_sheet.py", "sandra") "sandra_white" | Out-Null
Log "SANDRAASSETSDONE - outputs\game-assets\sandra\review_white.jpg, picks at /assets/sandra"
