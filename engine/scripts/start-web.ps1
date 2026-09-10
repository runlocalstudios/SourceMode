# Start the control panel locally on :3000 (the Vercel deploy can't see the GPU).
# Dev server for now; swap for `npm run build; npm start` once the pages settle.
$ErrorActionPreference = "Continue"
$log = "C:\dev\sourcemode\engine\outputs\logs"
New-Item -ItemType Directory -Force -Path $log | Out-Null
Set-Location "C:\dev\sourcemode"
& npm run dev *>> "$log\web.log"
