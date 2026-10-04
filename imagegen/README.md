# imagegen

Local tool for generating consistent character photographs through the OpenAI
Images API — the Codex image-generator replacement. Design: `docs/SPEC.md`.

## Setup (once)

1. **API billing.** API usage is billed separately from ChatGPT. At
   https://platform.openai.com → Billing, add a payment method or prepaid credit,
   and set a monthly usage limit you are comfortable with. Nothing in this app can
   enforce that limit; it only estimates.
2. **Key.** Create an API key at https://platform.openai.com/api-keys. Then either
   `copy .env.example .env` and put the key in `.env`, or set `OPENAI_API_KEY` as a
   Windows user environment variable. Do not paste it anywhere else.
3. **Verify the model.** Current docs (2026-10-01) list `gpt-image-2.5-sunburst`
   (default, detail), `gpt-image-2.5-flare` (speed), `gpt-image-2`, `gpt-image-1.5`,
   `gpt-image-1`, `gpt-image-1-mini`. The app records the model you requested and
   whatever the response reports; it never substitutes.

## Launch

- `launch.cmd` — real API. Opens http://127.0.0.1:8790/ (localhost only).
- `launch-mock.cmd` — same UI, no API calls, no key; "generations" are grey labelled
  images. Use it to learn the flow for free.

Tests (no spend): `uv run pytest` inside `imagegen/`.

## First comparison — Cici, four shots

1. Character `cici` is preselected; her three references show as thumbnails
   (`cici_face.jpg`, `cici_portrait1.jpg`, `cici_portrait2.jpg`). Untick any you
   don't want sent.
2. **Import manifest** → **Select pilot shots (1, 24, 45, 58)**. Not the first four:
   these are square-on or slight-angle, hair loose, gaze on the lens — the shots that
   read most like her, so a setting is judged on its best case. Framing still varies
   (head-and-chest, tight head, waist-up). Prompts are the manifest's, byte for byte;
   expand a row to read or edit one (edits go to a working copy, never the original).

   Codex's own first-four stop is unchanged and still shows the four most *different*
   shots — it answers "is the set varying", this answers "is it her".
3. Settings: model, `1024x1536`, quality (start with `high`), `input_fidelity=high`,
   `moderation=auto`. Label the run, e.g. `pilot-high`. Set a spend ceiling.
4. Read the estimate. Until real usage has been observed it is built on ASSUMED
   token counts and says so.
5. **Create run (no spend)** — this only writes the run folder and snapshots the
   references. Then **Generate** and confirm the dialog. The queue sends one request
   at a time; each image is saved to its final filename and committed before the next
   request starts.
6. Results show each API image beside the matching Codex image from
   `outputs/lora-gen-80/cici` (change the comparison in the dropdown). Keep/Reject
   and a note are saved to `review.json` in the run folder. Open either image full
   size by clicking it.
7. Repeat with quality `medium` (or `xhigh`) as a second run with its own label —
   runs never share a folder.

Same prompt, same references, different image: the model is stochastic, so the
comparison is "is she still Cici and is it as good", not "is it the same picture".

After the pilot, the estimate for an 80-shot batch uses the observed token counts;
`data/pricing.json` shows the running means. Enter the amount OpenAI billing shows
via the run's billing field to keep estimate and truth side by side.

## Moderation, measured

`moderation=low` does NOT loosen a `[sexual]` classification. A revealing-outfit
probe (V-neck crop top with a bare midriff, short skirt, 38-year-old subject, real
reference photos attached) was refused identically on `auto` and `low`:
`moderation_blocked` 400, `safety_violations=[sexual]`, 2026-10-04. So treat the
parameter as doing nothing for this class of refusal, and do not plan around it.

Consequence for the pipeline: the API is for the SANITIZED 80-shot training
curriculum - ordinary clothes - which is what it is asked for anyway. Revealing
wardrobe is rendered locally with the character's own LoRA, where no moderation
applies. Note the line already brushes ordinary clothing: Codex refused shot 4's
"terracotta wrap top" for both geena and trina.

## Errors and resume

The queue pauses itself on exhausted quota / insufficient credit, authentication
errors, invalid parameters, and local save failures, and shows the exact code,
message and request id. Temporary rate limits back off (Retry-After honoured, four
tries). A moderation refusal fails that shot only — edit its prompt and Retry; the
app never rewords a prompt for you. If the server stops mid-request the shot comes
back as **uncertain** (it may have been billed) and is only retried by hand.

Restarting the server never regenerates a saved image and never overwrites a file.

## Layout

```
app/        FastAPI server, worker queue, OpenAI client (+ mock), run records
static/     the single-page UI
data/       pricing.json (prices + observed usage), manifests/ (working copies)
outputs/    <character>/<run_id>/ run.json, refs/, images, review.json
tests/      mock-driven verification
```

## Known limitations / next

- One run active at a time; no parallel requests (deliberate for the pilot).
- Token-per-image assumptions for `xhigh`/`max` are guesses until observed.
- No per-character prompt templates yet (planned: feed `characters/appearance.json`).
- Manifest working copy is per character; no multi-manifest management yet.
- Billing truth is entered by hand; there is no billing API read.
