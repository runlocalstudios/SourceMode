"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type Candidate = {
  file: string;
  png: string;
  webp: string | null;
  source: string | null;
  score: number | null;
  flags: string[];
  partial: number | null;
  coverage: number | null;
};
type Slot = {
  id: string;
  category: string;
  look: number;
  outfit: string;
  hair: string;
  pose: string;
  filename: string | null;
  candidates: Candidate[];
  picked: string | null;
  auto: boolean;
};
type Data = {
  character: string;
  plan: string | null;
  slots: Slot[];
  unassigned: Candidate[];
  unassigned_picked: string[];
  placed: string[];
};
type Mapping = { slots: { id: string; file: string; from: string }[]; missing: string[]; sheet?: string };

const ACCENT = "#2f6fed";
const MUTED = "#6b7280";
const CHECKER =
  "linear-gradient(45deg,#d9d9d9 25%,transparent 25%),linear-gradient(-45deg,#d9d9d9 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#d9d9d9 75%),linear-gradient(-45deg,transparent 75%,#d9d9d9 75%)";

const api = (path: string) => `/api/engine/assets${path}`;
const img = (p: string, w = 240) => api(`/file?p=${encodeURIComponent(p)}&w=${w}`);

export default function ReviewClient({ character }: { character: string }) {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picks, setPicks] = useState<Record<string, string>>({});
  const [loose, setLoose] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<"save" | "place" | null>(null);
  const [mapping, setMapping] = useState<Mapping | null>(null);
  const [zoom, setZoom] = useState<Candidate | null>(null);
  const [refresh, setRefresh] = useState(0);
  const reload = () => setRefresh((k) => k + 1);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await fetch(api(`/${encodeURIComponent(character)}`), { cache: "no-store" });
        if (!r.ok) throw new Error(r.status === 503 ? "engine unreachable" : `${r.status}`);
        const d = (await r.json()) as Data;
        if (!alive) return;
        setData(d);
        const p: Record<string, string> = {};
        for (const s of d.slots) if (s.picked) p[s.id] = s.picked;
        setPicks(p);
        setLoose(new Set(d.unassigned_picked));
        setError(null);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "failed");
      }
    })();
    return () => {
      alive = false;
    };
  }, [character, refresh]);

  useEffect(() => {
    if (!zoom) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setZoom(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [zoom]);

  const body = useMemo(() => ({ picks: { ...picks, _unassigned: Array.from(loose) } }), [picks, loose]);
  const chosen = data ? data.slots.filter((s) => picks[s.id]).length : 0;
  const dirty = data ? data.slots.some((s) => (s.picked ?? "") !== (picks[s.id] ?? "") || s.auto) : false;

  const save = async () => {
    setBusy("save");
    try {
      const r = await fetch(api(`/${encodeURIComponent(character)}/picks`), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error(`save failed (${r.status})`);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "save failed");
    } finally {
      setBusy(null);
    }
  };

  const placeAll = async () => {
    if (!window.confirm(`Write ${chosen} looks to the staging outfits folder for ${character}?`)) return;
    setBusy("place");
    try {
      await fetch(api(`/${encodeURIComponent(character)}/picks`), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const r = await fetch(api(`/${encodeURIComponent(character)}/place`), { method: "POST" });
      if (!r.ok) throw new Error(r.status === 409 ? "no plan for this character" : `place failed (${r.status})`);
      setMapping((await r.json()) as Mapping);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "place failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", maxWidth: 1400, margin: "0 auto", padding: "16px 16px 96px", color: "#111" }}>
      <header style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
        <Link href="/assets" style={{ color: MUTED, fontSize: 14 }}>
          ← all characters
        </Link>
        <h1 style={{ margin: 0, fontSize: 22 }}>{character}</h1>
        {data && (
          <span style={{ color: MUTED, fontSize: 14 }}>
            {data.slots.length} looks · {data.slots.reduce((n, s) => n + s.candidates.length, 0)} candidates
            {data.plan ? ` · ${data.plan}` : " · no plan (slots from folders)"}
            {data.placed.length > 0 && ` · ${data.placed.length} placed`}
          </span>
        )}
      </header>
      <p style={{ color: MUTED, fontSize: 14, marginTop: 6 }}>
        Click the cutout that should ship for each look. The top-ranked one is pre-selected (best identity score, unflagged first). Click a
        thumbnail&apos;s magnifier to see it full size.
      </p>

      {error && (
        <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 10, padding: "10px 14px", margin: "10px 0" }}>
          <strong>{error}</strong>
          {error === "engine unreachable" && (
            <span style={{ color: MUTED }}> — start <code>sourcemode monitor serve</code> on the GPU box.</span>
          )}
        </div>
      )}

      {data && data.slots.length === 0 && data.unassigned.length === 0 && (
        <p>No cutouts under the staging folder for {character} yet.</p>
      )}

      {data?.slots.map((s) => (
        <section key={s.id} style={{ marginTop: 22 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
            <h2 style={{ margin: 0, fontSize: 17 }}>
              {s.id}
              <span style={{ color: MUTED, fontWeight: 400 }}> → {s.filename ?? `${s.id}_${s.pose}.webp`}</span>
            </h2>
            {(s.outfit || s.hair) && (
              <span style={{ color: MUTED, fontSize: 13 }}>
                {s.outfit}
                {s.hair && ` · ${s.hair}`}
              </span>
            )}
            {s.candidates.length === 0 && <span style={{ color: "#b91c1c", fontSize: 13 }}>no candidates</span>}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: 10, marginTop: 10 }}>
            {s.candidates.map((c) => (
              <Card
                key={c.file}
                c={c}
                selected={picks[s.id] === c.file}
                onSelect={() => setPicks((p) => ({ ...p, [s.id]: c.file }))}
                onZoom={() => setZoom(c)}
              />
            ))}
          </div>
        </section>
      ))}

      {data && data.unassigned.length > 0 && (
        <section style={{ marginTop: 26 }}>
          <h2 style={{ margin: 0, fontSize: 17 }}>
            Unassigned <span style={{ color: MUTED, fontWeight: 400 }}>— cutouts without a look slot; tick to keep for later</span>
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: 10, marginTop: 10 }}>
            {data.unassigned.map((c) => (
              <Card
                key={c.png}
                c={c}
                selected={loose.has(c.png)}
                multi
                onSelect={() =>
                  setLoose((prev) => {
                    const n = new Set(prev);
                    if (n.has(c.png)) n.delete(c.png);
                    else n.add(c.png);
                    return n;
                  })
                }
                onZoom={() => setZoom(c)}
              />
            ))}
          </div>
        </section>
      )}

      {mapping && (
        <section style={{ marginTop: 22, background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 10, padding: "10px 14px" }}>
          <strong>Placed {mapping.slots.length} files</strong>
          {mapping.missing.length > 0 && <span style={{ color: "#92400e" }}> · missing: {mapping.missing.join(", ")}</span>}
          {mapping.sheet && (
            <>
              {" "}
              ·{" "}
              <a href={img(mapping.sheet, 480)} target="_blank" rel="noreferrer">
                mapping sheet
              </a>
            </>
          )}
          <div style={{ color: MUTED, fontSize: 13, marginTop: 4 }}>Copy the staged outfits/ folder into the game repo yourself.</div>
        </section>
      )}

      {data && (data.slots.length > 0 || data.unassigned.length > 0) && (
        <footer
          style={{
            position: "fixed",
            left: 0,
            right: 0,
            bottom: 0,
            background: "#fff",
            borderTop: "1px solid #e5e7eb",
            padding: "10px 16px",
            display: "flex",
            gap: 12,
            alignItems: "center",
            justifyContent: "center",
            flexWrap: "wrap",
          }}
        >
          <span style={{ color: MUTED, fontSize: 14 }}>
            {chosen} of {data.slots.length} looks chosen{loose.size > 0 && ` · ${loose.size} kept`}
            {dirty && " · unsaved"}
          </span>
          <button onClick={save} disabled={busy !== null} style={btn(false)}>
            {busy === "save" ? "Saving…" : "Save picks"}
          </button>
          <button onClick={placeAll} disabled={busy !== null || !data.plan || chosen === 0} style={btn(true)} title={!data.plan ? "Needs a plan*.json" : ""}>
            {busy === "place" ? "Placing…" : `Place ${chosen} looks`}
          </button>
        </footer>
      )}

      {zoom && (
        <div onClick={() => setZoom(null)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.75)", display: "grid", placeItems: "center", zIndex: 50 }}>
          <div style={{ background: "#fff", backgroundImage: CHECKER, backgroundSize: "24px 24px", backgroundPosition: "0 0,0 12px,12px -12px,-12px 0", padding: 8, borderRadius: 8, maxHeight: "92vh" }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={api(`/file?p=${encodeURIComponent(zoom.png)}`)} alt={zoom.file} style={{ maxHeight: "88vh", maxWidth: "92vw", display: "block" }} />
          </div>
        </div>
      )}
    </main>
  );
}

function btn(primary: boolean): React.CSSProperties {
  return {
    padding: "8px 16px",
    borderRadius: 8,
    border: primary ? "none" : "1px solid #d1d5db",
    background: primary ? ACCENT : "#fff",
    color: primary ? "#fff" : "#111",
    fontWeight: 600,
    cursor: "pointer",
  };
}

function Card({ c, selected, multi, onSelect, onZoom }: { c: Candidate; selected: boolean; multi?: boolean; onSelect: () => void; onZoom: () => void }) {
  return (
    <div
      onClick={onSelect}
      role={multi ? "checkbox" : "radio"}
      aria-checked={selected}
      tabIndex={0}
      onKeyDown={(e) => (e.key === " " || e.key === "Enter") && (e.preventDefault(), onSelect())}
      style={{
        border: `3px solid ${selected ? ACCENT : "#e5e7eb"}`,
        borderRadius: 10,
        overflow: "hidden",
        cursor: "pointer",
        background: "#fff",
        boxShadow: selected ? `0 0 0 3px ${ACCENT}33` : "none",
      }}
    >
      <div style={{ position: "relative", backgroundImage: CHECKER, backgroundSize: "20px 20px", backgroundPosition: "0 0,0 10px,10px -10px,-10px 0", backgroundColor: "#f5f5f5", aspectRatio: "2 / 3" }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={img(c.png, 240)} alt={c.file} loading="lazy" style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }} />
        {selected && (
          <span style={{ position: "absolute", top: 6, left: 6, background: ACCENT, color: "#fff", borderRadius: 999, fontSize: 12, padding: "2px 8px", fontWeight: 700 }}>
            {multi ? "keep" : "ships"}
          </span>
        )}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onZoom();
          }}
          title="Full size"
          style={{ position: "absolute", top: 6, right: 6, border: "none", background: "rgba(255,255,255,.9)", borderRadius: 6, padding: "2px 7px", cursor: "pointer" }}
        >
          🔍
        </button>
      </div>
      <div style={{ padding: "6px 8px", fontSize: 12, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
        <span style={{ color: MUTED, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.file.replace(/\.png$/, "")}</span>
        <span style={{ display: "flex", gap: 4, flexShrink: 0 }}>
          {c.score != null && <b title="identity vs closeup reference">{c.score.toFixed(3)}</b>}
          {c.flags.map((f) => (
            <span key={f} style={{ background: "#fef3c7", color: "#92400e", borderRadius: 999, padding: "0 6px", fontWeight: 600 }} title={flagHelp(f)}>
              {f}
            </span>
          ))}
        </span>
      </div>
    </div>
  );
}

function flagHelp(f: string) {
  return (
    {
      hollow: "Matte is soft/see-through — clothing too close to the background colour",
      clipped: "Figure touches the left, right or top edge",
      islands: "More than one disconnected region — a stray piece or a split matte",
      tiny: "Almost nothing detected",
      empty: "No foreground at all",
    } as Record<string, string>
  )[f] ?? f;
}
