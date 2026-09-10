# Register the three SourceMode services to start at logon and survive reboots
# (a Windows Update reboot silently killed a 5-hour run on 2026-09-09).
# Run once from an elevated or normal PowerShell:  .\register-autostart.ps1
# Undo with unregister-autostart.ps1. Tasks appear in Task Scheduler under the
# "SourceMode" prefix; start one by hand with  Start-ScheduledTask "SourceMode Monitor".
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

$tasks = @(
  @{ Name = "SourceMode ComfyUI"; Script = "start-comfyui.ps1" },
  @{ Name = "SourceMode Monitor"; Script = "start-monitor.ps1" },
  @{ Name = "SourceMode Web";     Script = "start-web.ps1" }
)

$settings = New-ScheduledTaskSettingsSet `
  -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
  -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT20S"   # let the GPU driver and network settle first

foreach ($t in $tasks) {
  $script = Join-Path $here $t.Script
  $action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
  Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
  Write-Host "registered  $($t.Name)  ->  $script"
}
Write-Host "`nAlso stop the box from sleeping (render box):  powercfg /change standby-timeout-ac 0"
