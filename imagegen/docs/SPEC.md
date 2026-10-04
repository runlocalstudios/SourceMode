# imagegen — design specification

Local, single-user tool for generating consistent character photographs through the
OpenAI Images API, as a replacement for Codex's built-in image generator. Runs on
Jeremy's Windows machine (remote use is via Claude Code remote control or SSH, not a
deployment). Maintained by Claude Code.

## Goal of the first version

Answer two empirical questions before anything is polished:

1. Do API images preserve identity and match the quality of the existing Codex images?
   Jeremy judges this by eye, side by side. The app never scores likeness.
2. What does an 80-shot batch actually cost, including reference-image input?

## User workflow

1. Pick a character. References are discovered in
   `C:\Epic Games\Files\cnc info\codex\references` by the rule *full name before the
   first underscore, case-insensitive* (`priya_` never matches `priyanka_`). Thumbnails
   are shown and the selection can be changed.
2. Import the fixed 80-shot manifest (`~/.codex/skills/lora-gen-80/references/codex_manifest_80_main_v4.json`).
   The original is read-only; edits go to a per-character **working copy**
   (`data/manifests/<char>.json`). Prompts are preserved byte-for-byte unless edited.
3. Select shots (the pilot button selects 1, 24, 45 and 58), model, size, quality, `input_fidelity`,
   `moderation`, and a run label. Output lands in `outputs/<char>/<run_id>/`.
4. Review the cost estimate and its assumptions, then click **Generate**. Nothing is
   billed until that click.
5. Watch the queue (one request outstanding), pause/resume, read actionable errors.
6. Review results beside the references or the matching Codex image; Keep / Reject /
   notes are saved to the run record.

## Architecture

- **Backend:** Python 3.11, FastAPI + uvicorn, bound to `127.0.0.1:8790`. Chosen to
  match the engine (`sourcemode`): same language, same `uv` tooling, same style of
  small local HTTP pages (judge, dataset preview). The OpenAI key stays in the backend.
- **Frontend:** one static HTML page with vanilla JS. No build step.
- **Worker:** a background thread owned by the server process; one outstanding API
  request at a time; state transitions are persisted before the next request starts.
- **API client:** `openai` SDK, Images **edit** endpoint (`client.images.edit`) with
  the reference images attached — per the current docs this is the endpoint for
  "generate a new image using visual references". A mock client with the same
  interface drives the tests and the non-billable dry run.
- **Storage:** JSON records on disk, one directory per run, written atomically
  (write tmp → rename). SQLite is not needed for one user and tens of runs, and JSON
  keeps the run folder self-describing and copyable. Layout:

```
imagegen/
  data/manifests/<char>.json          working copy (prompts, edits, hair notes)
  data/pricing.json                   token prices + per-image token assumptions, with source + date
  outputs/<char>/<run_id>/
    run.json                          settings, references snapshot, shot states, usage, errors
    refs/                             copies of the exact reference files submitted
    <char>_shot_NNN.png               final filenames, written straight from the response
    review.json                       keep / reject / notes
```

## Data model (run.json)

```
run_id, character, created, label, settings{model, size, quality, input_fidelity, moderation, output_format}
references[{name, sha256, path}]   # snapshot — what was actually submitted
spend_ceiling_usd, estimate{per_image_usd, assumptions}
shots[{id, filename, prompt, state, attempts[{started, finished, request_id, model_returned,
        usage{input_tokens, output_tokens, text_tokens, image_tokens}, cost_usd|null,
        error{kind, code, message, retry_after}}]}]
totals{spent_estimate_usd, unknown_cost_attempts}
```

Shot states: `pending → running → saved | failed | blocked | uncertain`.
- `saved`: image written to its final filename and the record committed.
- `failed`: a definite API error (moderation, invalid params) — editable prompt, manual retry.
- `blocked`: queue paused on an account-wide condition (quota, credit, auth).
- `uncertain`: the request was sent but no outcome was recorded (timeout, crash). Never
  retried automatically; the UI asks first because a retry may pay twice.

## Cost model

Per request = text input tokens × text price + reference image tokens × image-input
price + output image tokens × image-output price. Prices are per-token from the
pricing page (verified 2026-10-01, `pricing.json` records the date and URL). Output
tokens per image depend on quality and size and are **not published as a table**;
`pricing.json` carries assumptions seeded from published per-image estimates and the
app replaces them with the mean of observed usage as paid results come in. Every
estimate shows its assumptions and which numbers are observed vs assumed.

Three figures are always kept apart: API-reported token usage, locally estimated
dollars, and what OpenAI billing shows (entered by hand if wanted). A failed request
with no usage is recorded as *unknown*, never zero.

**Spending ceiling:** before each request the worker checks
`spent_estimate + reserve(per_image_estimate) <= ceiling`; otherwise it pauses. The
ceiling is advisory — usage is only known after a request — and the UI says so.

## Failure handling

Errors are classified from the SDK exception type + status + error code:

| kind | examples | action |
|---|---|---|
| rate_limit | 429 `rate_limit_exceeded` | wait `Retry-After` or bounded backoff (max 4 tries) |
| quota | 429 `insufficient_quota`, billing hard limit | **pause queue**, keep code/message/request id |
| auth | 401 / 403 | pause queue |
| config | 400 invalid model/param | pause queue (every shot would fail) |
| moderation | 400 `moderation_blocked` / `content_policy_violation` | mark shot failed, prompt editable, no auto-rewording |
| transient | 5xx, connection, timeout | bounded backoff; after retries → `uncertain` if it was sent |
| local_io | cannot write file | pause queue |

Each request is bound to its shot and final filename **before** it is sent; the
response image is written to that filename, then the record is committed, then the
next shot starts. Filenames never come from timestamps or directory order. On startup
the server reconciles `run.json` against files on disk and never regenerates a
`saved` shot.

## Security

`OPENAI_API_KEY` is read from the environment or `imagegen/.env` (gitignored). It never
reaches the browser, logs, run records or image metadata. The server binds to
localhost only.

## Implementation phases

1. **Prototype (this build):** everything above with a mock client, tests, launcher.
2. **Pilot:** Cici's four pilot shots at one quality, then the same four at another; Jeremy
   judges beside the Codex images; observed usage replaces the token assumptions.
3. **Production:** full 80-shot runs, per-character prompt templates fed from
   `characters/appearance.json`, batch pricing if latency allows, polish.

## Verification (no spend)

Tests with the mock client cover: manifest import preserves prompts exactly; shot →
filename mapping; resume skips saved shots; quota pauses the queue; transient errors
are bounded; usage and unknown costs are logged; existing files are never overwritten.
