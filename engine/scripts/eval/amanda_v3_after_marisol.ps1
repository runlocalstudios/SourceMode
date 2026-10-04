# Amanda's full v3 pack, after Marisol's 3-minute hair recheck has had the card.
# Both were waiting on the same idle signal and would otherwise have raced for it.
# COUNT-based marker wait, then amanda_assets.ps1 does its own idle check. ASCII only.
$ErrorActionPreference = "Continue"
$E   = "C:\dev\sourcemode\engine\scripts\eval"
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\amanda_v3_wait.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
function Count { if (Test-Path "$L\marisol_hair_fix.log") { @(Select-String -Path "$L\marisol_hair_fix.log" -Pattern "MARISOLHAIRFIXDONE").Count } else { 0 } }
$base = Count
Log "waiting for a NEW MARISOLHAIRFIXDONE (already present: $base)"
$w = 0
while ((Count) -le $base) { Start-Sleep 30; $w += 30; if ($w -gt 10800) { Log "3h passed - proceeding anyway"; break } }
Log "starting amanda v3 pack"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$E\amanda_assets.ps1" -Now
Log "END exit=$LASTEXITCODE  AMANDAV3WAITDONE"
