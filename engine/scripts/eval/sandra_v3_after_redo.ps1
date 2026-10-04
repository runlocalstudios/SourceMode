# Re-render Sandra's whole pack on the ported Codex prompt contract (crop, body turn,
# head turn, expressions) once the three-look redo has finished. Moves the v2 render
# aside, then runs sandra_assets.ps1 -Now (2 shots per look). ASCII only.
$ErrorActionPreference = "Continue"
$E = "C:\dev\sourcemode\engine\scripts\eval"
$L = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\sandra_v3.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
function Count { if (Test-Path "$L\sandra_redo3.log") { @(Select-String -Path "$L\sandra_redo3.log" -Pattern "SANDRAREDO3DONE").Count } else { 0 } }
$base = Count
Log "waiting for a NEW SANDRAREDO3DONE (already present: $base)"
$w = 0
while ((Count) -le $base) { Start-Sleep 30; $w += 30; if ($w -gt 10800) { Log "ABORT: redo never finished in 3h"; exit 1 } }
Set-Location "C:\dev\sourcemode\engine\outputs\game-assets\sandra"
foreach ($d in @("renders", "cutouts", "outfits")) { if (Test-Path $d) { Move-Item $d "${d}_v2" -Force } }
if (Test-Path "review_white.jpg") { Move-Item "review_white.jpg" "review_white_v2.jpg" -Force }
if (Test-Path "mapping.json") { Copy-Item "mapping.json" "mapping_v2.json" -Force }
Log "v2 set aside; starting v3 render"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$E\sandra_assets.ps1" -Now
Log "SANDRAV3DONE"
