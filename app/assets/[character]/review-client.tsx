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
type Size = "comfortable" | "large";
/** Which group and which candidate the full-screen viewer is on. group -1 = unassigned. */
type Viewer = { group: number; index: number };

const ACCENT = "#2f6fed";
const MUTED = "#6b7280";
const CHECKER =
  "linear-gradient(45deg,#d9d9d9 25%,transparent 25%),linear-gradient(-45deg,#d9d9d9 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#d9d9d9 75%),linear-gradient(-45deg,transparent 75%,#d9d9d9 75%)";
// Review is about judging quality on a real screen: "comfortable" is ~5 across a
// 1440px window at 480px source thumbnails; "large" is ~3 across at 720px.
const SIZES: Record<Size, { thumb: number; min: number }> = { comfortable: { thumb: 480, min: 300 }, large: { thumb: 720, min: 440 } };

const api = (path: string) => `/api/engine/assets${path}`;
const img = (p: string, w?: number) => api(`/file?p=${encodeURIComponent(p)}${w ? `&w=${w}` : ""}`);

export default function ReviewClient({ character }: { character: string }) {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picks, setPicks] = useState<Record<string, string>>({});
  const [loose, setLoose] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<"save" | "place" | null>(null);
  const [mapping, setMapping] = useState<Mapping | null>(null);
  const [viewer, setViewer] = useState<Viewer | null>(null);
  // Lazy initialiser rather than an effect: the toggle only renders once data has
  // loaded (client-side), so a stored "large" can't mismatch the server render.
  const [size, setSize] = useState<Size>(() => {
    try {
      const s = localStorage.getItem("sourcemode.review.size");
      return s === "large" ? "large" : "comfortable";
    } catch {
      return "comfortable";
    }
  });
  const [refresh, setRefresh] = useState(0);
  const reload = () => setRefresh((k) => k + 1);

  const chooseSize = (s: Size) => {
    setSize(s);
    try {
      localStorage.setItem("sourcemode.review.size", s);
    } catch {
      /* no storage */
    }
  };

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

  // Groups the viewer steps through: every slot with candidates, then unassigned.
  const groups = useMemo(() => {
    type Group = { key: string; title: string; cands: Candidate[]; slot: Slot | null };
    if (!data) return [] as Group[];
    const g: Group[] = data.slots.filter((s) => s.candidates.length > 0).map((s) => ({ key: s.id, title: s.id, cands: s.candidates, slot: s }));
    if (data.unassigned.length) g.push({ key: "_unassigned", title: "unassigned", cands: data.unassigned, slot: null });
    return g;
  }, [data]);

  const pickInGroup = (g: (typeof groups)[number], c: Candidate) => {
    if (g.slot) setPicks((p) => ({ ...p, [g.slot!.id]: c.file }));
    else
      setLoose((prev) => {
        const n = new Set(prev);
        if (n.has(c.png)) n.delete(c.png);
        else n.add(c.png);
        return n;
      });
  };
  const isPicked = (g: (typeof groups)[number], c: Candidate) => (g.slot ? picks[g.slot.id] === c.file : loose.has(c.png));

  useEffect(() => {
    if (!viewer) return;
    const onKey = (e: KeyboardEvent) => {
      const g = groups[viewer.group];
      if (!g) return;
      if (e.key === "Escape") setViewer(null);
      else if (e.key === "ArrowRight") setViewer({ group: viewer.group, index: (viewer.index + 1) % g.cands.length });
      else if (e.key === "ArrowLeft") setViewer({ group: viewer.group, index: (viewer.index - 1 + g.cands.length) % g.cands.length });
      else if (e.key === "ArrowDown" && viewer.group + 1 < groups.length) setViewer({ group: viewer.group + 1, index: 0 });
      else if (e.key === "ArrowUp" && viewer.group > 0) setViewer({ group: viewer.group - 1, index: 0 });
      else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        pickInGroup(g, g.cands[viewer.index]);
      } else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewer, groups]);

  const body = useMemo(() => ({ picks: { ...picks, _unassigned: Array.from(loose) } }), [picks, loose]);
  const chosen = data ? data.slots.filter((s) => picks[s.id]).length : 0;
  const dirty = data ? data.slots.some((s) => (s.picked ?? "") !== (picks[s.id] ?? "") || s.auto) : false;

  const postPicks = () =>
    fetch(api(`/${encodeURIComponent(character)}/picks`), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });

  const save = async () => {
    setBusy("save");
    try {
      const r = await postPicks();
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
      await postPicks();
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

  const dims = SIZES[size];
  const grid: React.CSSProperties = { display: "grid", gridTemplateColumns: `repeat(auto-fill, minmax(${dims.min}px, 1fr))`, gap: 12, marginTop: 10 };

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", maxWidth: 1800, margin: "0 auto", padding: "16px 16px 96px", color: "#111" }}>
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
        {data && (
          <span style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center", fontSize: 13, color: MUTED }}>
            size
            {(["comfortable", "large"] as Size[]).map((s) => (
              <button key={s} onClick={() => chooseSize(s)} style={{ ...btn(size === s), padding: "4px 10px", fontSize: 13 }}>
                {s}
              </button>
            ))}
          </span>
        )}
      </header>
      <p style={{ color: MUTED, fontSize: 14, marginTop: 6 }}>
        Click the cutout that should ship for each look; the top-ranked one is pre-selected (unflagged first, then identity score). The 🔍 opens the
        full-resolution viewer: ← → step through a look, ↑ ↓ change look, Enter picks, Esc closes.
      </p>

      {error && (
        <div style={{ background: "#fff5f5", border: "1px solid #fecaca", borderRadius: 10, padding: "10px 14px", margin: "10px 0" }}>
          <strong>{error}</strong>
          {error === "engine unreachable" && (
            <span style={{ color: MUTED }}> — start <code>sourcemode monitor serve</code> on the GPU box.</span>
          )}
        </div>
      )}

      {data && data.slots.length === 0 && data.unassigned.length === 0 && <p>No cutouts under the staging folder for {character} yet.</p>}

      {data?.slots.map((s) => {
        const gi = groups.findIndex((g) => g.key === s.id);
        return (
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
            <div style={grid}>
              {s.candidates.map((c, i) => (
                <Card
                  key={c.file}
                  c={c}
                  thumb={dims.thumb}
                  selected={picks[s.id] === c.file}
                  onSelect={() => setPicks((p) => ({ ...p, [s.id]: c.file }))}
                  onZoom={() => setViewer({ group: gi, index: i })}
                />
              ))}
            </div>
          </section>
        );
      })}

      {data && data.unassigned.length > 0 && (
        <section style={{ marginTop: 26 }}>
          <h2 style={{ margin: 0, fontSize: 17 }}>
            Unassigned <span style={{ color: MUTED, fontWeight: 400 }}>— cutouts without a look slot; tick to keep for later</span>
          </h2>
          <div style={grid}>
            {data.unassigned.map((c, i) => (
              <Card
                key={c.png}
                c={c}
                thumb={dims.thumb}
                selected={loose.has(c.png)}
                multi
                onSelect={() => pickInGroup(groups[groups.length - 1], c)}
                onZoom={() => setViewer({ group: groups.length - 1, index: i })}
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
              <a href={img(mapping.sheet)} target="_blank" rel="noreferrer">
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
            zIndex: 10,
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

      {viewer && groups[viewer.group] && (
        <FullView
          group={groups[viewer.group]}
          index={viewer.index}
          groupPos={`${viewer.group + 1} / ${groups.length}`}
          picked={isPicked(groups[viewer.group], groups[viewer.group].cands[viewer.index])}
          onPick={() => pickInGroup(groups[viewer.group], groups[viewer.group].cands[viewer.index])}
          onStep={(d) => setViewer({ group: viewer.group, index: (viewer.index + d + groups[viewer.group].cands.length) % groups[viewer.group].cands.length })}
          onClose={() => setViewer(null)}
        />
      )}
    </main>
  );
}

function FullView({
  group,
  index,
  groupPos,
  picked,
  onPick,
  onStep,
  onClose,
}: {
  group: { title: string; cands: Candidate[]; slot: Slot | null };
  index: number;
  groupPos: string;
  picked: boolean;
  onPick: () => void;
  onStep: (d: number) => void;
  onClose: () => void;
}) {
  const c = group.cands[index];
  const next = group.cands[(index + 1) % group.cands.length];
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(10,10,12,.9)", zIndex: 50, display: "flex", flexDirection: "column" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ display: "flex", alignItems: "center", gap: 14, padding: "10px 16px", color: "#fff", flexWrap: "wrap" }}>
        <strong style={{ fontSize: 16 }}>{group.title}</strong>
        <span style={{ opacity: 0.75 }}>look {groupPos}</span>
        <span style={{ opacity: 0.75 }}>
          {index + 1} / {group.cands.length} · {c.file.replace(/\.png$/, "")}
        </span>
        {c.score != null && <span title="identity vs closeup reference">score {c.score.toFixed(3)}</span>}
        {c.flags.map((f) => (
          <span key={f} style={{ background: "#fef3c7", color: "#92400e", borderRadius: 999, padding: "1px 8px", fontWeight: 600, fontSize: 12 }}>
            {f}
          </span>
        ))}
        {group.slot?.outfit && <span style={{ opacity: 0.6, fontSize: 13 }}>{group.slot.outfit}</span>}
        <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button onClick={() => onStep(-1)} style={vbtn(false)} title="Previous (←)">
            ←
          </button>
          <button onClick={() => onStep(1)} style={vbtn(false)} title="Next (→)">
            →
          </button>
          <button onClick={onPick} style={vbtn(!picked)} title="Enter">
            {group.slot ? (picked ? "✓ ships" : "Pick this") : picked ? "✓ kept" : "Keep"}
          </button>
          <button onClick={onClose} style={vbtn(false)} title="Esc">
            ✕
          </button>
        </span>
      </div>
      <div onClick={(e) => e.stopPropagation()} style={{ flex: 1, minHeight: 0, display: "grid", placeItems: "center", padding: "0 16px 16px" }}>
        <div style={{ height: "100%", maxWidth: "100%", backgroundImage: CHECKER, backgroundColor: "#fff", backgroundSize: "28px 28px", backgroundPosition: "0 0,0 14px,14px -14px,-14px 0", borderRadius: 8, overflow: "hidden", boxShadow: picked ? `0 0 0 4px ${ACCENT}` : "none" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={img(c.png)} alt={c.file} style={{ height: "100%", width: "auto", maxWidth: "100%", objectFit: "contain", display: "block" }} />
        </div>
      </div>
      {/* warm the cache for the next step */}
      {next && next !== c && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={img(next.png)} alt="" aria-hidden style={{ position: "absolute", width: 1, height: 1, opacity: 0, pointerEvents: "none" }} />
      )}
    </div>
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

function vbtn(primary: boolean): React.CSSProperties {
  return {
    padding: "6px 14px",
    borderRadius: 8,
    border: primary ? "none" : "1px solid rgba(255,255,255,.35)",
    background: primary ? ACCENT : "rgba(255,255,255,.08)",
    color: "#fff",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 14,
  };
}

function Card({ c, thumb, selected, multi, onSelect, onZoom }: { c: Candidate; thumb: number; selected: boolean; multi?: boolean; onSelect: () => void; onZoom: () => void }) {
  return (
    <div
      onClick={onSelect}
      onDoubleClick={onZoom}
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
        <img src={img(c.png, thumb)} alt={c.file} loading="lazy" style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }} />
        {selected && (
          <span style={{ position: "absolute", top: 8, left: 8, background: ACCENT, color: "#fff", borderRadius: 999, fontSize: 12, padding: "2px 8px", fontWeight: 700 }}>
            {multi ? "keep" : "ships"}
          </span>
        )}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onZoom();
          }}
          title="Full size (or double-click)"
          style={{ position: "absolute", top: 8, right: 8, border: "none", background: "rgba(255,255,255,.92)", borderRadius: 6, padding: "3px 8px", cursor: "pointer", fontSize: 14 }}
        >
          🔍
        </button>
      </div>
      <div style={{ padding: "6px 10px", fontSize: 13, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
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
