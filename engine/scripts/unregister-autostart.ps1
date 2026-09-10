# Remove the logon tasks created by register-autostart.ps1. Does not stop running processes.
foreach ($name in "SourceMode ComfyUI", "SourceMode Monitor", "SourceMode Web") {
  if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
    Write-Host "removed  $name"
  }
}
