# Gather -> caption -> preview for one character, at the back of the queue.
#
#   powershell -File character_chain.ps1 -Char bianca -WaitLog trina_chain.log -WaitPattern TRINADONE
#
# New policy (Jeremy, 2026-09-22): a Lora-Gen set never goes to the judging tab -
# it goes straight to captioning, and culling happens on the Training sets page.
#
# Two waits, because a Lora-Gen run is still writing while this is queued:
#   1. the previous character's completion marker
#   2. the character's image count stable for STABLE_MIN minutes, so a run that is
#      still producing shots is not gathered half-finished. Geena's run record
#      claimed "shots 5-80 in progress" with 11 shots on disk; gathering then would
#      have trained her on an eighth of her set.
# ASCII only.
param(
  [Parameter(Mandatory=$true)][string]$Char,
  [string]$WaitLog = "",
  [string]$WaitPattern = "",
  [int]$Cap = 100,
  [int]$StableMin = 12,
  [int]$MinShots = 70,
  # references + Lora-Gen outputs only; the hand-collected base folder is skipped
  [switch]$NoBase,
  # STRICTER than -NoBase: only codex/references and the lora-gen run folder.
  # Jeremy, 2026-10-04 - cat has eleven older run folders carrying her name and
  # -NoBase still gathered 336 images for her against jaina's clean 81.
  [switch]$LoragenOnly,
  [switch]$RecheckAll
)
$ErrorActionPreference = "Continue"
# Repo paths, never a session scratchpad. $SP used to be one Claude session's
# temp directory under AppData\Local\Temp, which put the ENTIRE
# dataset-prep chain - gather, gaze, caption, hair confirm, preview - one
# cleanup away from gone, with nothing in the repo to rebuild it from.
$PREP = "C:\dev\sourcemode\engine\scripts\prep"
$PY  = "C:\dev\sourcemode\engine\.venv\Scripts\python.exe"
$L   = "C:\dev\sourcemode\engine\outputs\logs"
$log = "$L\chain_$Char.log"
function Log($s) { "$(Get-Date -Format s)  $s" | Out-File $log -Append -Encoding utf8 }
function Free { try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8188/free -ContentType application/json -Body '{"unload_models":true,"free_memory":true}' | Out-Null } catch {} ; Start-Sleep 10 }
function Step($label, $argList, $outLog) {
  Log "START $label"
  $p = Start-Process -FilePath $PY -NoNewWindow -Wait -PassThru -ArgumentList $argList `
        -RedirectStandardOutput "$L\$outLog.stdout.log" -RedirectStandardError "$L\$outLog.stderr.log"
  Log "END $label exit=$($p.ExitCode)"
  if ($p.ExitCode -ne 0) { Log "$label FAILED - read $outLog.stdout.log" }
  return $p.ExitCode
}
function CountShots($c) {
  # Look everywhere gather_character.py looks, because this gate decides whether
  # the gather ever runs. It used to search ONLY
  # codex\outputs\lora-gen-80 - the Codex Lora-Gen skill's folder - so when
  # Tess's 80 shots were produced by the local imagegen tool into
  # codex\outputs\tess_imagegen, this counted 0 and waited four hours for
  # images that were already on disk. The gather would have found them
  # immediately; only the gate was blind, and the gate is what blocks.
  #
  # Three layouts, all real:
  #   outputs\<anything-with-the-name>\*.png   per-run folder (tess_imagegen)
  #   outputs\lora-gen-80\<char>_shot_*.png    loose  (keiko, trina)
  #   outputs\lora-gen-80\<char>\*.png        nested (ash, hannah)
  $roots = @("C:\Epic Games\Files\cnc info\codex\outputs",
             "C:\Epic Games\Files\cnc info\codex\output")
  $bad = @("wrong", "bad", "reject", "discard", "dupe", "archive", "superseded")
  $n = 0
  foreach ($R in $roots) {
    if (-not (Test-Path $R)) { continue }
    foreach ($sub in @(Get-ChildItem -Path $R -Directory -ErrorAction SilentlyContinue)) {
      $low = $sub.Name.ToLower()
      if ($bad | Where-Object { $low.Contains($_) }) { continue }
      if ($low.Contains($c)) {
        # a whole run folder for this character
        $n += @(Get-ChildItem -Path $sub.FullName -File -Recurse -ErrorAction SilentlyContinue |
                Where-Object { $_.Extension -in '.png', '.jpg' }).Count
        continue
      }
      # a shared run folder: loose files, or a subfolder named for her
      $n += @(Get-ChildItem -Path $sub.FullName -Filter ($c + "_shot_*.png") -File -ErrorAction SilentlyContinue).Count
      $nested = Join-Path $sub.FullName $c
      if (Test-Path $nested) {
        $n += @(Get-ChildItem -Path $nested -File -Recurse -ErrorAction SilentlyContinue |
                Where-Object { $_.Extension -in '.png', '.jpg' }).Count
      }
    }
  }
  return $n
}
function CountImages($c) {
  $B = "C:\Epic Games\Files\cnc info"
  $n = 0
  foreach ($root in @("$B\$c", "$B\codex\output", "$B\codex\outputs")) {
    if (Test-Path $root) {
      $n += @(Get-ChildItem -Path $root -Recurse -File -Include *.png,*.jpg,*.jpeg,*.webp -ErrorAction SilentlyContinue |
              Where-Object { $_.FullName -like "*$c*" -and $_.FullName -notlike "*wrong*" }).Count
    }
  }
  return $n
}
Set-Location "C:\dev\sourcemode\engine"

if ($WaitLog -and $WaitPattern) {
  Log "waiting for $WaitPattern in $WaitLog"
  $w = 0
  while (-not ((Test-Path "$L\$WaitLog") -and (Select-String -Path "$L\$WaitLog" -Pattern $WaitPattern -Quiet))) {
    Start-Sleep 120; $w += 120
    if ($w -gt 172800) { Log "ABORT: $WaitPattern never appeared"; exit 1 }
  }
  Log "$WaitPattern seen"
}

# A stalled run looks exactly like a finished one: Geena's sat at 11 of 80 shots
# with a run record still claiming "shots 5-80 in progress". Stability alone would
# have gathered an eighth of her set and captioned it. Require the shot count to
# actually REACH a full set as well as stop moving.
Log "waiting for $Char to reach $MinShots Lora-Gen shots and hold steady $StableMin minutes"
$last = -1; $held = 0; $waited = 0
while ($true) {
  $shots = CountShots $Char
  if ($shots -ne $last) { Log "  $shots shots"; $last = $shots; $held = 0 } else { $held += 2 }
  if ($shots -ge $MinShots -and $held -ge $StableMin) { break }
  if ($held -ge 60 -and $shots -lt $MinShots) {
    Log "  STALLED: $shots shots, unchanged for an hour, short of $MinShots - still waiting, restart the Lora-Gen run or lower -MinShots"
    $held = 0
  }
  Start-Sleep 120; $waited += 2
  if ($waited -gt 4320) { Log "ABORT: $Char never reached $MinShots shots in 3 days"; exit 1 }
}
$total = CountImages $Char
Log "$Char ready: $last Lora-Gen shots, $total images across all sources"

Free
$gatherArgs = @("$PREP\gather_character.py", $Char, "--cap", "$Cap", "--apply")
if ($NoBase) { $gatherArgs += "--no-base" }
if ($LoragenOnly) { $gatherArgs += "--loragen-only" }
$rc = Step "$Char gather" $gatherArgs "gather_$Char"
if ($rc -ne 0) { Log "ABORT: nothing staged for $Char"; exit 1 }
# CPU (MediaPipe). Writes gaze_mp.json, without which caption_from_vl.py
# drops the gaze clause and the mouth-open override with only a NOTE.
Step "$Char gaze" @("$PREP\gaze_mp.py", $Char) "gaze_mp_$Char" | Out-Null

# gather and gaze are CPU and can run beside anything. The Qwen2.5-VL passes
# below cannot: ComfyUI holds ~29 GB resident and a training run wants the rest,
# so captioning beside one has forced a run to be stopped mid-flight before.
# Wait for the card, capped at 12 hours so a stuck job cannot strand a set.
Log "waiting for an idle GPU before the VL passes"
$w = 0
while ($true) {
  $busy = @(Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -like 'python*' -or $_.Name -like 'sourcemode*') -and ($_.CommandLine -like '*qwen_image_train_network*' -or
    $_.CommandLine -like '*dense_epoch_eval.py*' -or $_.CommandLine -like '*cache_latents*' -or
    $_.CommandLine -like '*cache_text_encoder*' -or $_.CommandLine -like '*assets*render*' -or
    $_.CommandLine -like '*loragen_local*' -or $_.CommandLine -like '*amanda_shoots*') }).Count
  if ($busy -eq 0) { break }
  Start-Sleep 120; $w += 120
  if ($w -gt 43200) { Log "GPU busy 12h - captioning anyway"; break }
}
Free
$rc = Step "$Char captions"     @("$PREP\caption_from_vl.py", $Char)          "captions_$Char"    
# A marker on an empty result is what let a failed caption step reach
# the Training sets tab and release the next chain.
if ($rc -ne 0) { Log "ABORT: captions failed, not writing the DONE marker"; exit 1 }
Step "$Char hair confirm" @("$PREP\hair_confirm2.py", $Char, "--apply") "hair_confirm_$Char" | Out-Null
# Plan captions say what was ASKED. On a character whose hair cannot hold a braid
# or a long ponytail the generator substituted something else, and only asking
# the image catches it - rivera 2026-10-05, marisol 2026-10-03. Run for everyone:
# on long hair it confirms the braids, on short hair it corrects them.
# -RecheckAll re-asks EVERY image, not only the length-dependent clauses. Casey,
# 2026-10-08: the plan asked loose / half-up / clip and ~75 of 80 came back as a
# ponytail, so the plan's "worn loose" would have been written on ponytails.
$recheckArgs = @("C:\dev\sourcemode\engine\scripts\eval\hair_recheck.py", $Char, "--apply")
if ($RecheckAll) { $recheckArgs += "--all" }
Step "$Char hair recheck" $recheckArgs "hair_recheck_$Char" | Out-Null
$rc = Step "$Char re-assemble"  @("$PREP\caption_from_vl.py", $Char)          "captions_${Char}2" 
# A marker on an empty result is what let a failed caption step reach
# the Training sets tab and release the next chain.
if ($rc -ne 0) { Log "ABORT: re-assemble failed, not writing the DONE marker"; exit 1 }
Step "$Char preview"      @("$PREP\build_previews.py", $Char)           "preview_$Char"      | Out-Null
Log "$($Char.ToUpper())DONE - on the Training sets tab for review"
