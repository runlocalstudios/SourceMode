# Start ComfyUI headless (no --auto-launch: it would open a browser tab at every logon).
# Logs to engine/outputs/logs/comfyui.log. Used by register-autostart.ps1.
$ErrorActionPreference = "Continue"
$log = "C:\dev\sourcemode\engine\outputs\logs"
New-Item -ItemType Directory -Force -Path $log | Out-Null
Set-Location "C:\ComfyUI"
& "C:\ComfyUI\venv311\Scripts\python.exe" main.py *>> "$log\comfyui.log"
