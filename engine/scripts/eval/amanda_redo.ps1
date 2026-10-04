# Re-render the Amanda looks Jeremy named (2026-10-02 evening) once Daisy's
# extension releases the card: casual_01 (hole / second navel), casual_05 (sweater
# artifact), fancy_dining_gallery_03 (hair -> messy bun), fancy_town_01 (hands across
# the belly), fancy_town_03 (bra under the mesh). New seed so new candidates render,
# plate is magenta, key is auto, every other look pinned to its current pick.
# Never kills anything. ASCII only.
param([string]$Only = "casual_01,casual_05,fancy_dining_gallery_03,fancy_town_01,fancy_town_03", [int]$Seed = 7500)
$ErrorActionPreference = "Continue"
$PY  = "C:\dev\sourcemode\engine\.venv\Scripts\python.exe"
$UV  = (Get-Command uv).Source
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\amanda_redo.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
function Run($label, $exe, $argv, $tag) {
  Log "START $label"
  $p = Start-Process -FilePath $exe -NoNewWindow -Wait -PassThru -ArgumentList $argv -RedirectStandardOutput "$L\$tag.stdout.log" -RedirectStandardError "$L\$tag.stderr.log"
  Log "END $label exit=$($p.ExitCode)"; return $p.ExitCode
}
Set-Location "C:\dev\sourcemode\engine"
$w = 0
while ($true) {
  $busy = @(Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'python*' -or $_.Name -like 'sourcemode*') -and
    ($_.CommandLine -like '*qwen_image_train_network*' -or $_.CommandLine -like '*dense_epoch_eval.py*' -or $_.CommandLine -like '*caption_from_vl*' -or
     $_.CommandLine -like '*hair_confirm2*' -or $_.CommandLine -like '*assets*render*' -or $_.CommandLine -like '*loragen_local*') }).Count
  if ($busy -eq 0) { break }
  Start-Sleep 60; $w += 60; if ($w -gt 21600) { Log "card busy 6h - proceeding"; break }
}
try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8188/free -ContentType application/json -Body '{"unload_models":true,"free_memory":true}' | Out-Null } catch {}
Start-Sleep 10
$plan = "outputs\game-assets\amanda\plan_28.json"
Copy-Item "outputs\game-assets\amanda\mapping.json" "outputs\game-assets\amanda\mapping_before_redo.json" -Force
# the old candidates of the redone looks go, so only the new prompt competes
$looks = $Only.Split(",")
foreach ($lk in $looks) { foreach ($d in @("renders", "cutouts")) { $p = "outputs\game-assets\amanda\$d\${lk}_standing"; if (Test-Path $p) { Remove-Item $p -Recurse -Force } } }
# a fresh plate in the backdrop colour the prompt asks for
if (Test-Path "outputs\game-assets\amanda\renders\_plate.png") { Remove-Item "outputs\game-assets\amanda\renders\_plate.png" -Force }
$rc = Run "amanda redo render ($Only)" $UV @("run", "sourcemode", "assets", "render", "--plan", $plan, "--out", "outputs\game-assets", "--shots", "3", "--seed", "$Seed", "--only", $Only) "amanda_redo_render"
if ($rc -ne 0) { Log "render FAILED"; exit 1 }
Run "amanda redo cutout" $UV @("run", "sourcemode", "assets", "cutout", "outputs\game-assets\amanda\renders", "--out", "outputs\game-assets\amanda\cutouts", "--game", "--chroma", "auto") "amanda_redo_cutout" | Out-Null
$prev = Get-Content "outputs\game-assets\amanda\mapping_before_redo.json" -Raw | ConvertFrom-Json
$pins = @()
foreach ($s in $prev.slots) { if ($s.id -notin $looks) { $pins += "$($s.id)=$([IO.Path]::GetFileName($s.from))" } }
Run "amanda redo place" $UV @("run", "sourcemode", "assets", "place", "--plan", $plan, "--cutouts", "outputs\game-assets\amanda\cutouts", "--out", "outputs\game-assets", "--pick", ($pins -join ",")) "amanda_redo_place" | Out-Null
Run "amanda white sheet" $PY @("scripts\eval\white_sheet.py", "amanda") "amanda_redo_white" | Out-Null
Log "AMANDAREDODONE - $Only"
