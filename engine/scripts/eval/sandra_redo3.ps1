# Re-render work_01, work_03, workout_03 for Sandra (Jeremy, 2026-10-02: full body /
# weird pose / braid-loose hair), after the overnight Amanda jobs release the card.
# New seed so new candidates render; place is re-run and every OTHER look is pinned
# to its previous pick so only these three can change. Not urgent. ASCII only.
param([switch]$Now)
$ErrorActionPreference = "Continue"
$PY  = "C:\dev\sourcemode\engine\.venv\Scripts\python.exe"
$UV  = (Get-Command uv).Source
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\sandra_redo3.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
function Count { if (Test-Path "$L\amanda_codex_confirm.log") { @(Select-String -Path "$L\amanda_codex_confirm.log" -Pattern "AMANDACODEXCONFIRMDONE").Count } else { 0 } }
function Run($label, $exe, $argv, $tag) {
  Log "START $label"
  $p = Start-Process -FilePath $exe -NoNewWindow -Wait -PassThru -ArgumentList $argv -RedirectStandardOutput "$L\$tag.stdout.log" -RedirectStandardError "$L\$tag.stderr.log"
  Log "END $label exit=$($p.ExitCode)"; return $p.ExitCode
}
Set-Location "C:\dev\sourcemode\engine"
$base = Count
if ($Now) { $base = -1; Log "-Now: not waiting" } else { Log "waiting for a NEW AMANDACODEXCONFIRMDONE (already present: $base)" }
$w = 0
while ((Count) -le $base) { Start-Sleep 60; $w += 60; if ($w -gt 86400) { Log "ABORT: 24h"; exit 1 } }
$w = 0
while ($true) {
  $busy = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and ($_.CommandLine -like '*qwen_image_train_network*' -or $_.CommandLine -like '*dense_epoch_eval.py*') }).Count
  if ($busy -eq 0) { break }
  Start-Sleep 60; $w += 60; if ($w -gt 7200) { Log "card busy 2h - proceeding"; break }
}
try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8188/free -ContentType application/json -Body '{"unload_models":true,"free_memory":true}' | Out-Null } catch {}
Start-Sleep 10
$plan = "outputs\game-assets\sandra\plan_28.json"
$rc = Run "sandra redo render" $UV @("run", "sourcemode", "assets", "render", "--plan", $plan, "--out", "outputs\game-assets", "--shots", "3", "--seed", "7400", "--only", "work_01,work_03,workout_03") "sandra_redo_render"
if ($rc -ne 0) { Log "render FAILED"; exit 1 }
Run "sandra redo cutout" $UV @("run", "sourcemode", "assets", "cutout", "outputs\game-assets\sandra\renders", "--out", "outputs\game-assets\sandra\cutouts", "--game") "sandra_redo_cutout" | Out-Null
# pin every other look to its previous pick
$prev = Get-Content "outputs\game-assets\sandra\mapping_v2_before_redo.json" -Raw | ConvertFrom-Json
$pins = @()
foreach ($s in $prev.slots) { if ($s.id -notin @("work_01", "work_03", "workout_03")) { $pins += "$($s.id)=$([IO.Path]::GetFileName($s.from))" } }
Run "sandra redo place" $UV @("run", "sourcemode", "assets", "place", "--plan", $plan, "--cutouts", "outputs\game-assets\sandra\cutouts", "--out", "outputs\game-assets", "--pick", ($pins -join ",")) "sandra_redo_place" | Out-Null
Run "sandra white sheet" $PY @("scripts\eval\white_sheet.py", "sandra") "sandra_redo_white" | Out-Null
Log "SANDRAREDO3DONE - review outputs\game-assets\sandra\review_white.jpg, then copy the three webps to the game repo"
