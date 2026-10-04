# Train one approved set, then sweep its epochs so the result is judgeable.
#   powershell -File train_character.ps1 -Ds mira_v2 -Char mira
# Recipe is Sunny's, which is the one that has been working: Qwen-Image-2512
# original, rank 32 / alpha 16, lr 1e-4, discrete_flow_shift 2.2, blocks_to_swap 4,
# 24 epochs with every epoch saved. REFUSES TO START unless the preview is still
# approved as it stands. ASCII only.
param(
  [Parameter(Mandatory=$true)][string]$Ds,
  [Parameter(Mandatory=$true)][string]$Char,
  [int]$Epochs = 24,
  # An experiment trains the SAME dataset under a different name so its checkpoints
  # never mix with the production run's and approval still keys on $Ds.
  [string]$OutName = "",
  [string]$Lr = "1e-4",
  [int]$EvalStart = 0,
  [int]$EvalEnd = 0,
  # 'favorable' selects the shipped-photo scene set instead of the bare sweep.
  [string]$EvalScenes = "asset",
  # Only with this does a run overwrite checkpoints that already exist.
  [switch]$Force,
  # Warm start from an existing checkpoint. NOT a bit-exact resume - musubi
  # needs an optimizer state that --save_state was never asked to write - but
  # lr is constant so nothing else restarts and the Adam moments rebuild in a
  # few dozen steps. A continued run RESTARTS its epoch numbering at 1, so
  # pass -EvalOffset so the arms read as real epochs.
  [string]$Resume = "",
  [int]$EvalOffset = 0
)
if (-not $OutName) { $OutName = $Ds }
# A production run keeps writing to <dataset>\lora; only a named experiment
# gets its own folder, so every queued run is unaffected.
$LoraSub = if ($OutName -eq $Ds) { "lora" } else { "lora_$OutName" }
$ErrorActionPreference = "Continue"
# Repo paths, never a session scratchpad. These two used to point into one
# Claude session's temp directory, which meant (a) every script here broke the
# moment that directory was cleaned, and (b) an edit to the repo's
# train_character.ps1 was silently not picked up by the scripts that invoke it.
$SP  = "C:\dev\sourcemode\engine\scripts"
$EV  = "C:\dev\sourcemode\engine\scripts\eval"
$PY  = "C:\dev\sourcemode\engine\.venv\Scripts\python.exe"
$M   = "C:\dev\e2egen\vendor\musubi-tuner"
# $DsDir, NOT $DS: PowerShell variable names are case-INSENSITIVE, so $DS IS
# the $Ds parameter. Assigning the path to it overwrote the dataset name, so
# the log path became "...\logs\C:\dev\...\mira_v2.log" - unsupported, and
# every Log call threw silently - and 'train approved' was handed a full path
# and aborted. mira_v2 failed in five seconds, three times, logging nothing.
$DsDir = "C:\dev\sourcemode\engine\outputs\lora-datasets\$Ds"
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\$($OutName).log"
$env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
Set-Location "C:\dev\sourcemode\engine"

# Refuse to train into a directory that already holds checkpoints. Two train_queue
# instances were running at once on 2026-09-29; the second re-picked maddie_v2 half
# an hour after she finished and began overwriting her judged epochs - ep1-3 were
# gone before it was caught, and ep23 (80%, n=10) was hours from being destroyed.
# A finished run is data, not a scratch directory.
$existing = @(Get-ChildItem "$DsDir\$LoraSub\*.safetensors" -ErrorAction SilentlyContinue).Count
if ($existing -gt 0 -and -not $Force) {
  Log "ABORT: $DsDir\$LoraSub already holds $existing checkpoints - pass -Force to overwrite"
  exit 1
}

# Refuse to start while another training already holds the card. 2026-10-03: a queue
# script checked for a live run, FOUND vivienne, waited - and then proceeded anyway on
# a 4-hour timeout ("card busy 4h - proceeding", 19:44). zara launched on top of her,
# the box fell to 0.2 GB free of 63, and the GPU sat at 100% util drawing 104W, which
# is thrashing, not training. A guard that gives up is not a guard: this one has no
# timeout and no override. A caller may WAIT for the card; it may not overrule.
# Matches the train process itself, so it cannot match this script's own command line.
$running = @(Get-CimInstance Win32_Process | Where-Object {
  $_.ProcessId -ne $PID -and $_.CommandLine -like '*qwen_image_train_network*' })
if ($running.Count -gt 0) {
  $pids = ($running | ForEach-Object { $_.ProcessId }) -join ", "
  Log "ABORT: a training is already running (PID $pids) - never two on one card"
  exit 1
}

Log "checking approval for $Ds"
& "C:\dev\sourcemode\engine\.venv\Scripts\sourcemode.exe" train approved $Ds --quiet
if ($LASTEXITCODE -ne 0) { Log "ABORT: $Ds is not approved as it stands (exit $LASTEXITCODE)"; exit 1 }
$free = (Get-PSDrive C).Free / 1GB
if ($free -lt 45) { Log "ABORT: $([math]::Round($free,1)) GB free, 24 checkpoints need about 30 GB"; exit 1 }

Log "unloading ComfyUI"
try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8188/free -ContentType application/json -Body '{"unload_models":true,"free_memory":true}' | Out-Null } catch {}
Start-Sleep 10

Log "caching latents + text encoder"
& "$M\.venv\Scripts\python.exe" "$M\src\musubi_tuner\qwen_image_cache_latents.py" --dataset_config "$DsDir\dataset_qwen_t2i.toml" --vae "C:\ComfyUI\models\vae\qwen_image_vae.safetensors" --model_version original 2>&1 | Select-Object -Last 1 | Out-File $log -Append -Encoding utf8
& "$M\.venv\Scripts\python.exe" "$M\src\musubi_tuner\qwen_image_cache_text_encoder_outputs.py" --dataset_config "$DsDir\dataset_qwen_t2i.toml" --text_encoder "C:\ComfyUI\models\text_encoders\qwen_2.5_vl_7b.safetensors" --batch_size 1 --model_version original 2>&1 | Select-Object -Last 1 | Out-File $log -Append -Encoding utf8

Log "START train $OutName (rank 32, lr $Lr, $Epochs epochs, every epoch saved)"
$targs = @("launch", "--num_cpu_threads_per_process", "1", "--mixed_precision", "bf16",
  "$M\src\musubi_tuner\qwen_image_train_network.py",
  "--dit", "C:\ComfyUI\models\diffusion_models\qwen_image_2512_bf16.safetensors",
  "--vae", "C:\ComfyUI\models\vae\qwen_image_vae.safetensors",
  "--text_encoder", "C:\ComfyUI\models\text_encoders\qwen_2.5_vl_7b.safetensors",
  "--model_version", "original", "--dataset_config", "$DsDir\dataset_qwen_t2i.toml",
  "--sdpa", "--mixed_precision", "bf16", "--fp8_base", "--fp8_scaled",
  "--optimizer_type", "adamw8bit", "--learning_rate", "$Lr",
  "--gradient_checkpointing", "--max_data_loader_n_workers", "2", "--persistent_data_loader_workers",
  "--network_module", "networks.lora_qwen_image", "--network_dim", "32", "--network_alpha", "16",
  "--timestep_sampling", "shift", "--weighting_scheme", "none", "--discrete_flow_shift", "2.2",
  "--max_train_epochs", "$Epochs", "--save_every_n_epochs", "1", "--seed", "42", "--blocks_to_swap", "4",
  "--output_dir", "$DsDir\$LoraSub", "--output_name", "$OutName")
if ($Resume) {
  if (-not (Test-Path $Resume)) { Log "ABORT: -Resume $Resume does not exist"; exit 1 }
  $targs += @("--network_weights", $Resume)
  Log "warm start from $Resume"
}
$p = Start-Process -FilePath "$M\.venv\Scripts\accelerate.exe" -ArgumentList $targs -NoNewWindow -Wait -PassThru `
       -RedirectStandardOutput "C:\dev\sourcemode\engine\outputs\training\$($Ds).log" `
       -RedirectStandardError  "C:\dev\sourcemode\engine\outputs\training\$($Ds).log.err"
Log "END train $OutName exit $($p.ExitCode)"

if (Test-Path "$DsDir\$LoraSub\$($OutName).safetensors") {
  for ($i = 0; $i -lt 60; $i++) {
    try { Invoke-RestMethod -Uri http://127.0.0.1:8188/system_stats -TimeoutSec 5 | Out-Null; break } catch { Start-Sleep 20 }
  }
  Start-Sleep 15
  # 14-22 left the last two epochs of every run unmeasured. Sunny read 40% at
  # 22 and 60% at both 23 and 24; the ceiling was the sweep, not the LoRA.
  # Start at 16, not 14: Jeremy, 2026-09-23 - no character's best epoch has ever
  # landed below 16 (maya 16, jojo 16, priya 16; everything else 21-26), so the
  # first two arms were 20 renders a character spent confirming a known floor.
  Log "START $Char eval, epochs $(if ($EvalStart) { $EvalStart } else { 16 })-$(if ($EvalEnd) { $EvalEnd } else { $Epochs }) x 10 scenes$(if ($EvalScenes) { ' (' + $EvalScenes + ')' })"
  # Build the argument array FIRST. `-ArgumentList @(...) + $(...)` inline does not
  # bind - Start-Process ran with no usable arguments, returned an EMPTY exit code
  # and wrote zero-byte logs, and the failure was silent.
  $evArgs = @("$EV\dense_epoch_eval.py", $Char, $OutName, "$Epochs",
              "$(if ($EvalStart) { $EvalStart } else { 16 })",
              "$(if ($EvalEnd) { $EvalEnd } else { $Epochs })", $Char,
              "outputs\lora-datasets\$Ds\$LoraSub", "10")
  if ($EvalOffset) { $evArgs += @("$EvalOffset") }   # argv[9] = epoch offset
  if ($EvalScenes) { $evArgs += @("--scenes", $EvalScenes) }
  $ev = Start-Process -FilePath $PY -NoNewWindow -Wait -PassThru -ArgumentList $evArgs `
    -RedirectStandardOutput "$L\eval_$($OutName).stdout.log" -RedirectStandardError "$L\eval_$($OutName).stderr.log"
  Log "END $Char eval exit=$($ev.ExitCode)"
  if ($ev.ExitCode -ne 0) { Log "EVAL FAILED - no judge set; read eval_$($Ds).stdout.log" }
} else { Log "no final checkpoint; skipping eval" }
Log "$($OutName.ToUpper())TRAINDONE"
