# Two jobs Jeremy approved, in sequence so they never contend for the card.
#
#  1. Maddie ep22 vs ep23 at n=20. Her ep23 read 80% at n=10 - the exact number
#     Bianca's ep12 showed before collapsing to 55% under confirmation. Scenes 0-9
#     already exist for both arms and are reused; only 10-19 render. This gates
#     pruning her.
#  2. Extend Bianca's lr-2e-4 run 8 epochs past 24. She hit 80% at ep24, which is
#     the LAST epoch that exists - the Sunny pattern, where a rate still rising at
#     the edge meant undertrained rather than peaked. Warm start from her final
#     weights at the same lr; epochs renumber from 1, so the eval gets -EvalOffset 24.
#
# PowerShell, not nohup'd bash: every bash waiter launched from the agent tool has
# died silently within hours. ASCII only.
$ErrorActionPreference = "Continue"
$SP  = "C:\Users\jerem\AppData\Local\Temp\claude\C--dev-sourcemode\913e6b47-2e1a-4e0e-af1d-c0c28a922563\scratchpad"
$PY  = "C:\dev\sourcemode\engine\.venv\Scripts\python.exe"
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\tonight_two.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
function Free { try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8188/free -ContentType application/json -Body '{"unload_models":true,"free_memory":true}' | Out-Null } catch {}; Start-Sleep 10 }
Set-Location "C:\dev\sourcemode\engine"

Free
Log "1/2 START maddie ep22 vs ep23 at n=20 (standard scenes, as she was judged)"
$a = Start-Process -FilePath $PY -NoNewWindow -Wait -PassThru -ArgumentList @(
      "$SP\dense_epoch_eval.py", "maddie", "maddie_v2", "24", "22", "23", "maddie",
      "outputs\lora-datasets\maddie_v2\lora", "20", "--epochs", "22,23") `
    -RedirectStandardOutput "$L\confirm_maddie.stdout.log" `
    -RedirectStandardError  "$L\confirm_maddie.stderr.log"
Log "1/2 END exit=$($a.ExitCode)"

Free
Log "2/2 START bianca lr2 extension, 8 epochs from bianca_lr2.safetensors"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SP\train_character.ps1" `
    -Ds bianca_v2 -Char bianca -OutName bianca_lr2b -Lr 2e-4 -Epochs 8 `
    -Resume "C:\dev\sourcemode\engine\outputs\lora-datasets\bianca_v2\lora_bianca_lr2\bianca_lr2.safetensors" `
    -EvalStart 1 -EvalEnd 8 -EvalOffset 24 -EvalScenes favorable
Log "2/2 END exit=$LASTEXITCODE  TONIGHTTWODONE"
