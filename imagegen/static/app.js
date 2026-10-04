// imagegen UI. Plain fetch + DOM; state is whatever the server says.
const $ = (id) => document.getElementById(id);
const api = async (path, opts = {}) => {
  const r = await fetch(path, { headers: { "content-type": "application/json" }, ...opts });
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch {} throw new Error(m); }
  return r.json();
};
const post = (path, body) => api(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const img = (p) => `/api/file?p=${encodeURIComponent(p)}`;

// The pilot is a fixed set of shots, not the first four. 1 is slight-angle; 24, 45 and
// 58 are square-on or slight with the hair loose and the gaze on the lens, so they are
// the shots that read most like her and make the best test of a setting.
const PILOT_IDS = ["shot_001", "shot_024", "shot_045", "shot_058"];
const pilotShots = () => {
  const by = new Map(manifest.shots.map((s) => [s.id, s]));
  const hit = PILOT_IDS.map((i) => by.get(i)).filter(Boolean);
  return hit.length === PILOT_IDS.length ? hit : manifest.shots.slice(0, 4);
};

let status = null, character = null, refsInfo = null, manifest = null, selected = new Set(), run = null, review = {};
let poll = null;

// The 2.5 models reject input_fidelity rather than ignoring it, so the control is
// forced to "none" and locked for them - a stale "high" fails the whole request.
function syncFidelity() {
  const blocked = (status.no_input_fidelity || []).includes($("model").value);
  if (blocked) $("fidelity").value = "none";
  $("fidelity").disabled = blocked;
  $("fidelity").title = blocked ? `${$("model").value} does not accept input_fidelity` : "";
}

async function init() {
  status = await api("/api/status");
  for (const [id, list, def] of [["model", status.models, status.defaults.model], ["size", status.sizes, status.defaults.size],
      ["quality", status.qualities, status.defaults.quality], ["fidelity", status.input_fidelity, status.defaults.input_fidelity],
      ["moderation", status.moderation, status.defaults.moderation]]) {
    $(id).innerHTML = list.map(v => `<option ${v === def ? "selected" : ""}>${v}</option>`).join("");
    $(id).onchange = id === "model" ? () => { syncFidelity(); estimate(); } : estimate;
  }
  syncFidelity();
  renderStatus();
  const c = await api("/api/characters");
  // No default character. Picking one is the first explicit act: a default meant
  // the app opened already pointed at somebody, and a run could be created against
  // whoever happened to be preselected. Jeremy, 2026-10-04.
  $("char").innerHTML = '<option value="">- choose a character -</option>'
    + c.characters.map(n => `<option>${n}</option>`).join("");
  if (!c.characters.length) $("refs-missing").textContent = `no references found in ${c.dir}`;
  $("char").onchange = loadCharacter;
  $("reload").onclick = loadCharacter;
  $("import").onclick = async () => { if (!character) return; manifest = await post(`/api/manifest/${character}/import`); renderShots(); };
  $("pilot").onclick = () => { if (!manifest) return; selected = new Set(pilotShots().map(s => s.id)); renderShots(); };
  $("all").onclick = () => { if (!manifest) return; selected = new Set(manifest.shots.map(s => s.id)); renderShots(); };
  // The rest of the set, for when the pilot shots are already generated and judged.
  $("rest").onclick = () => {
    if (!manifest) return;
    const pilot = new Set(pilotShots().map(s => s.id));
    selected = new Set(manifest.shots.filter(s => !pilot.has(s.id)).map(s => s.id));
    renderShots();
  };
  $("none").onclick = () => { selected = new Set(); renderShots(); };
  $("create").onclick = createRun;
  $("generate").onclick = generate;
  $("pause").onclick = () => post(`/api/runs/${run.character}/${run.run_id}/pause`).then(refreshRun);
  $("resume").onclick = () => post(`/api/runs/${run.character}/${run.run_id}/resume`).then(refreshRun);
  await loadCharacter();   // renders the empty state
  loadRuns(); loadCosts();
}

function renderStatus() {
  const pill = (id, ok, text) => { const e = $(id); e.textContent = text; e.className = "pill " + (ok ? "ok" : "bad"); };
  pill("st-mode", !status.mock, status.mock ? "MOCK mode – no API calls" : "live API");
  pill("st-key", status.key_present || status.mock, status.key_present ? "key loaded" : "OPENAI_API_KEY missing");
  pill("st-refs", status.references_dir_exists, status.references_dir_exists ? "references ok" : "references dir missing");
  pill("st-manifest", status.manifest_exists, status.manifest_exists ? "manifest ok" : "manifest missing");
  const a = $("st-active"); a.textContent = status.active ? `running ${status.active_run}` : "idle"; a.className = "pill " + (status.active ? "warn" : "");
}

async function loadCharacter() {
  character = $("char").value; selected = new Set(); run = null; $("run-panel").hidden = true;
  if (!character) {
    manifest = null; refsInfo = null;
    $("refs").innerHTML = "";
    $("refs-missing").textContent = "";
    $("sel-count").textContent = "";
    $("shots").innerHTML = `<p class="muted">Choose a character above to load her references and the shot manifest.</p>`;
    $("create").disabled = true;
    estimate();
    return;
  }
  refsInfo = await api(`/api/references/${character}`);
  $("refs").innerHTML = refsInfo.references.map(r => `<label title="${r.name}"><input type="checkbox" checked data-name="${r.name}"><img src="${img(r.path)}">${r.name}</label>`).join("");
  $("refs-missing").textContent = refsInfo.references.length ? "" : `no files named ${character}_* in the references folder`;
  $("refs").querySelectorAll("input").forEach(i => i.onchange = estimate);
  try { manifest = await api(`/api/manifest/${character}`); } catch { manifest = null; }
  renderShots();
}

function chosenRefs() { return [...$("refs").querySelectorAll("input:checked")].map(i => i.dataset.name); }
function settings() { return { model: $("model").value, size: $("size").value, quality: $("quality").value, input_fidelity: $("fidelity").value, moderation: $("moderation").value, output_format: "png" }; }

function renderShots() {
  if (!manifest) { $("shots").innerHTML = `<p class="muted">Manifest not imported for ${character}. Click Import manifest (the original is never modified).</p>`; $("create").disabled = true; return; }
  $("sel-count").textContent = `${selected.size} of ${manifest.shots.length} selected`;
  $("shots").innerHTML = `<table><tr><th></th><th>id</th><th>filename</th><th>hair</th><th>prompt</th></tr>` + manifest.shots.map(s => `
    <tr class="${selected.has(s.id) ? "sel" : ""}">
      <td><input type="checkbox" data-id="${s.id}" ${selected.has(s.id) ? "checked" : ""}></td>
      <td class="mono">${s.id}${s.edited ? ' <span class="pill warn">edited</span>' : ""}</td>
      <td class="mono">${s.filename}</td><td>${s.hair_needs_length || ""}</td>
      <td><details><summary>${s.prompt.slice(0, 90)}…</summary><textarea data-edit="${s.id}">${s.prompt.replace(/</g, "&lt;")}</textarea>
        <div class="row"><button data-save="${s.id}">Save prompt to working copy</button>${s.edited ? `<span class="muted">original kept in the working copy</span>` : ""}</div></details></td>
    </tr>`).join("") + `</table>`;
  $("shots").querySelectorAll("input[type=checkbox]").forEach(i => i.onchange = () => { i.checked ? selected.add(i.dataset.id) : selected.delete(i.dataset.id); renderShots(); });
  $("shots").querySelectorAll("button[data-save]").forEach(b => b.onclick = async () => {
    const id = b.dataset.save; const prompt = $("shots").querySelector(`textarea[data-edit="${id}"]`).value;
    manifest = await post(`/api/manifest/${character}/prompt`, { shot_id: id, prompt }); renderShots();
  });
  $("create").disabled = selected.size === 0;
  estimate();
}

async function estimate() {
  if (!manifest || !selected.size) { $("est").innerHTML = `<span class="muted">select shots to see an estimate</span>`; return; }
  const s = settings();
  const e = await post("/api/estimate", { model: s.model, size: s.size, quality: s.quality, n_refs: chosenRefs().length, n_shots: selected.size });
  if (e.per_image_usd == null) { $("est").innerHTML = `<b>no estimate</b><small>${e.assumptions.join("; ")}</small>`; return; }
  $("est").innerHTML = `<b>≈ $${e.per_image_usd} per image · $${e.run_usd} for ${e.n_shots} · ≈ $${e.batch80_usd} for 80</b>
    <small>${e.observed ? "from observed usage" : "ASSUMED token counts – not yet observed"}</small>
    ${e.assumptions.map(a => `<small>· ${a}</small>`).join("")}
    <small>estimate only: usage is reported after each request; OpenAI billing is the truth.</small>`;
}

async function createRun() {
  const body = { character, label: $("label").value || "run", shot_ids: [...selected], reference_names: chosenRefs(), settings: settings(),
    spend_ceiling_usd: parseFloat($("ceiling").value) || null };
  try { run = await post("/api/runs", body); } catch (e) { alert(e.message); return; }
  showRun(); loadRuns();
}

async function generate() {
  const n = run.shots.filter(s => s.state === "pending").length;
  const per = run.estimate.per_image_usd;
  if (!confirm(`Send ${n} request(s) to OpenAI with ${run.references.length} reference image(s) each?\n\nmodel ${run.settings.model}, ${run.settings.size}, quality ${run.settings.quality}\nestimate ≈ $${per} per image, ≈ $${(per * n).toFixed(2)} total (assumed until observed)\nceiling $${run.spend_ceiling_usd ?? "none"}`)) return;
  try { await post(`/api/runs/${run.character}/${run.run_id}/generate`); } catch (e) { alert(e.message); return; }
  startPoll();
}

function showRun() {
  $("run-panel").hidden = false; $("run-id").textContent = run.run_id;
  renderRun(); startPoll();
}
function startPoll() { clearInterval(poll); poll = setInterval(refreshRun, 1500); }
async function refreshRun() {
  if (!run) return;
  run = await api(`/api/runs/${run.character}/${run.run_id}`);
  review = await api(`/api/runs/${run.character}/${run.run_id}/review`);
  status = await api("/api/status"); renderStatus();
  renderRun();
  if (!status.active && run.shots.every(s => s.state !== "running" && s.state !== "pending")) { clearInterval(poll); loadRuns(); loadCosts(); }
}

function renderRun() {
  const t = run.totals, counts = {};
  run.shots.forEach(s => counts[s.state] = (counts[s.state] || 0) + 1);
  $("run-totals").textContent = `${Object.entries(counts).map(([k, v]) => `${v} ${k}`).join(" · ")} · spent ≈ $${t.spent_estimate_usd}${t.unknown_cost_attempts ? ` · ${t.unknown_cost_attempts} attempt(s) with UNKNOWN cost` : ""}`;
  $("run-pause").hidden = !run.paused; $("run-pause").innerHTML = run.paused ? `<b>Paused:</b> ${run.pause_reason}` : "";
  $("generate").disabled = status.active || !run.shots.some(s => s.state === "pending");
  $("log").innerHTML = (status.log || []).map(l => l.replace(/</g, "&lt;")).join("<br>");
  const dir = status.outputs + "\\" + run.character + "\\" + run.run_id;
  const codex = refsInfo?.codex_outputs || [];
  $("results").innerHTML = run.shots.map(s => {
    const last = s.attempts[s.attempts.length - 1] || {};
    const rv = review[s.id] || {};
    const file = `${dir}\\${s.filename}`;
    const cmp = rv.codex_compare || (codex.includes(s.filename) ? s.filename : "");
    const cmpPath = cmp ? `${status.codex_outputs}\\${run.character}\\${cmp}` : null;
    const usage = last.usage ? `in ${last.usage.input_tokens} (img ${last.usage.image_in_tokens}, text ${last.usage.text_tokens}) · out ${last.usage.output_tokens}` : (last.sent ? "usage UNKNOWN" : "");
    return `<div class="card">
      <div class="row"><span class="mono">${s.id}</span> <span class="state ${s.state}">${s.state}</span> <span class="muted">${s.attempts.length} attempt(s)</span></div>
      ${s.state === "saved" ? (cmpPath ? `<div class="pair"><a href="${img(file)}" target="_blank"><img src="${img(file)}" title="API"></a><a href="${img(cmpPath)}" target="_blank"><img src="${img(cmpPath)}" title="Codex"></a></div><div class="muted">left API · right Codex ${cmp}</div>` : `<a href="${img(file)}" target="_blank"><img src="${img(file)}"></a>`) : ""}
      ${last.error ? `<div class="mono" style="color:var(--bad)">${last.error.kind} ${last.error.code || ""} ${last.error.status || ""}: ${(last.error.message || "").replace(/</g, "&lt;")}${last.error.request_id ? ` · req ${last.error.request_id}` : ""}</div>` : ""}
      <div class="muted mono">${usage}${last.cost_usd != null ? ` · ≈ $${last.cost_usd}` : ""}${last.model_returned ? ` · ${last.model_returned}` : ""}</div>
      <div class="row">
        ${["failed", "uncertain", "blocked"].includes(s.state) ? `<button data-retry="${s.id}" class="${s.state === "uncertain" ? "danger" : ""}">${s.state === "uncertain" ? "Retry (may bill twice)" : "Retry"}</button>` : ""}
        ${s.state === "saved" ? `<button data-v="keep" data-id="${s.id}" class="${rv.verdict === "keep" ? "primary" : ""}">Keep</button><button data-v="reject" data-id="${s.id}" class="${rv.verdict === "reject" ? "danger" : ""}">Reject</button>
          <select data-cmp="${s.id}"><option value="">compare: Codex…</option>${codex.map(n => `<option ${n === cmp ? "selected" : ""}>${n}</option>`).join("")}</select>` : ""}
      </div>
      ${s.state === "saved" ? `<input type="text" placeholder="note" data-note="${s.id}" value="${(rv.note || "").replace(/"/g, "&quot;")}" style="width:100%">` : ""}
    </div>`;
  }).join("");
  $("results").querySelectorAll("button[data-retry]").forEach(b => b.onclick = async () => {
    const s = run.shots.find(x => x.id === b.dataset.retry);
    if (s.state === "uncertain" && !confirm("This request may already have been billed. Retry and possibly pay twice?")) return;
    await post(`/api/runs/${run.character}/${run.run_id}/retry/${s.id}`); startPoll();
  });
  $("results").querySelectorAll("button[data-v]").forEach(b => b.onclick = () => post(`/api/runs/${run.character}/${run.run_id}/review`, { shot_id: b.dataset.id, verdict: b.dataset.v }).then(refreshRun));
  $("results").querySelectorAll("select[data-cmp]").forEach(e => e.onchange = () => post(`/api/runs/${run.character}/${run.run_id}/review`, { shot_id: e.dataset.cmp, codex_compare: e.value }).then(refreshRun));
  $("results").querySelectorAll("input[data-note]").forEach(e => e.onchange = () => post(`/api/runs/${run.character}/${run.run_id}/review`, { shot_id: e.dataset.note, note: e.value }));
}

async function loadRuns() {
  const r = await api("/api/runs");
  $("runs").innerHTML = r.runs.length ? r.runs.map(x => `<div class="row"><a href="#" data-open="${x.character}/${x.run_id}" class="mono">${x.run_id}</a><span class="muted">${x.character} · ${x.settings.model} ${x.settings.quality} · ${Object.entries(x.counts).map(([k, v]) => `${v} ${k}`).join(", ")} · ≈ $${x.totals.spent_estimate_usd}${x.paused ? " · PAUSED" : ""}</span></div>`).join("") : `<span class="muted">none yet</span>`;
  $("runs").querySelectorAll("a[data-open]").forEach(a => a.onclick = async (ev) => {
    ev.preventDefault(); const [c, id] = a.dataset.open.split("/");
    if (c !== character) { $("char").value = c; await loadCharacter(); }
    run = await api(`/api/runs/${c}/${id}`); showRun();
  });
}
async function loadCosts() {
  const c = await api("/api/costs");
  $("costs").textContent = `${c.saved} images saved · ≈ $${c.spent_estimate_usd} estimated · ${c.unknown_cost_attempts} attempt(s) with unknown cost`;
}

init().catch(e => { document.body.insertAdjacentHTML("afterbegin", `<div style="background:#5a1e1e;padding:8px 16px">${e.message}</div>`); });
