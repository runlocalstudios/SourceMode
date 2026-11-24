# Register the SourceMode services to start at logon and survive reboots
# (a Windows Update reboot silently killed a 5-hour run on 2026-09-09).
# Run once from an elevated or normal PowerShell:  .\register-autostart.ps1
# Undo with unregister-autostart.ps1. Tasks appear in Task Scheduler under the
# "SourceMode" prefix; start one by hand with  Start-ScheduledTask "SourceMode Monitor".
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

$tasks = @(
  @{ Name = "SourceMode ComfyUI"; Script = "start-comfyui.ps1" },
  @{ Name = "SourceMode Monitor"; Script = "start-monitor.ps1" },
  # The GPU runner: the only thing that starts training, evals or asset renders,
  # one at a time, in the queue's order. Registered here so it comes back after a
  # reboot - a Windows Update restart silently killed a 5-hour run once already.
  @{ Name = "SourceMode GPU Runner"; Script = "start-gpu-runner.ps1" }
)

$settings = New-ScheduledTaskSettingsSet `
  -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
  -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT20S"   # let the GPU driver and network settle first

foreach ($t in $tasks) {
  $script = Join-Path $here $t.Script
  # conhost --headless, not -WindowStyle Hidden: with Windows Terminal as the
  # default terminal, Hidden is ignored and every task left an empty window open
  # that killed its service (and the runner's training child) if closed.
  $action = New-ScheduledTaskAction -Execute "conhost.exe" `
    -Argument "--headless powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$script`""
  Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
  Write-Host "registered  $($t.Name)  ->  $script"
}

# The card's power limit. nvidia-smi's limit goes back to the 575 W default on
# every reboot, and setting it needs admin (Jeremy, 2026-11-24: "the max power
# draw should be 475" - a shoot was drawing 575). So this one task runs as
# SYSTEM at startup, before ComfyUI's logon task, and registering it needs an
# elevated shell; a normal shell registers the three above and says so here.
$powerLimitW = 475
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
  ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($admin) {
  $smi = Join-Path $env:SystemRoot "System32\nvidia-smi.exe"
  Register-ScheduledTask -TaskName "SourceMode GPU Power Limit" -Force `
    -Action (New-ScheduledTaskAction -Execute $smi -Argument "-pl $powerLimitW") `
    -Trigger (New-ScheduledTaskTrigger -AtStartup) `
    -Principal (New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest) `
    -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries) | Out-Null
  Start-ScheduledTask "SourceMode GPU Power Limit"   # and set it now
  Write-Host "registered  SourceMode GPU Power Limit  ->  nvidia-smi -pl $powerLimitW at startup"
} else {
  Write-Host "NOT registered: SourceMode GPU Power Limit ($powerLimitW W) needs an elevated PowerShell - run this script again as admin."
}
Write-Host "`nAlso stop the box from sleeping (render box):  powercfg /change standby-timeout-ac 0"
