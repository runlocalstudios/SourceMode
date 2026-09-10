"use client";

import { useEffect, useState } from "react";
import type { EngineStatus, HistoryPoint } from "../../lib/engine";
import { fmtDuration, fmtGb, ringOffset, sampleAge, sparklinePoints } from "../../lib/monitor-format";

const STATUS_POLL_MS = 2000;
const HISTORY_POLL_MS = 10000;

type StatusResponse = { reachable: boolean; status: EngineStatus | null };
type HistoryResponse = { reachable: boolean; points: HistoryPoint[] };

const ACCENT = "#2f6fed";
const MUTED = "#6b7280";
const CARD: React.CSSProperties = {
  background: "#fff",
  border: "1px solid #e5e7eb",
  borderRadius: 14,
  padding: "16px 18px",
};

export default function MonitorClient() {
  const [resp, setResp] = useState<StatusResponse | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let alive = true;
    const pollStatus = async () => {
      try {
        const r = await fetch("/api/engine/status", { cache: "no-store" });
        const j = (await r.json()) as StatusResponse;
        if (alive) setResp(j);
      } catch {
        if (alive) setResp({ reachable: false, status: null });
      }
      if (alive) setNow(Date.now());
    };
    const pollHistory = async () => {
      try {
        const r = await fetch("/api/engine/history", { cache: "no-store" });
        const j = (await r.json()) as HistoryResponse;
        if (alive) setHistory(j.points ?? []);
      } catch {
        /* keep the last series */
      }
    };
    pollStatus();
    pollHistory();
    const a = setInterval(pollStatus, STATUS_POLL_MS);
    const b = setInterval(pollHistory, HISTORY_POLL_MS);
    return () => {
      alive = false;
      clearInterval(a);
      clearInterval(b);
    };
  }, []);

  const status = resp?.status ?? null;
  const reachable = resp?.reachable ?? false;
  const age = sampleAge(status?.sampled_at ?? null, now);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", maxWidth: 480, margin: "0 auto", padding: "20px 16px 40px", color: "#111" }}>
      <header style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 16 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22 }}>GPU box</h1>
          <div style={{ color: MUTED, fontSize: 13 }}>{status?.gpu?.name ?? "SourceMode engine"}</div>
        </div>
        <Pill
          tone={!reachable ? "bad" : age.stale ? "warn" : "ok"}
          text={resp == null ? "connecting" : !reachable ? "engine unreachable" : age.text}
        />
      </header>

      {resp && !reachable && (
        <section style={{ ...CARD, borderColor: "#fecaca", background: "#fff5f5" }}>
          <strong>The engine monitor isn&apos;t answering.</strong>
          <p style={{ margin: "6px 0 0", color: MUTED, fontSize: 14 }}>
            On the GPU box run <code>uv run sourcemode monitor serve</code> (or check the
            &ldquo;SourceMode Monitor&rdquo; scheduled task). Nothing here is known until it does.
          </p>
        </section>
      )}

      {status && (
        <>
          <JobCard status={status} nowMs={now} />
          <section style={{ ...CARD, marginTop: 12, display: "grid", gridTemplateColumns: "148px 1fr", gap: 16, alignItems: "center" }}>
            <Ring value={status.gpu?.util_pct ?? null} unknown={status.gpu == null} />
            <div>
              <Vram used={status.gpu?.mem_used_mb ?? null} total={status.gpu?.mem_total_mb ?? null} unknown={status.gpu == null} />
              <div style={{ marginTop: 12, color: MUTED, fontSize: 13, display: "flex", gap: 14, flexWrap: "wrap" }}>
                <span>{status.gpu?.temp_c != null ? `${status.gpu.temp_c}°C` : "temp —"}</span>
                <span>
                  {status.gpu?.power_w != null
                    ? `${Math.round(status.gpu.power_w)} W${status.gpu.power_limit_w ? ` / ${Math.round(status.gpu.power_limit_w)}` : ""}`
                    : "power —"}
                </span>
              </div>
            </div>
          </section>
          <Sparkline points={history} />
          <ComfyLine status={status} />
        </>
      )}
    </main>
  );
}

function Pill({ tone, text }: { tone: "ok" | "warn" | "bad"; text: string }) {
  const colors = { ok: ["#dcfce7", "#166534"], warn: ["#fef3c7", "#92400e"], bad: ["#fee2e2", "#991b1b"] }[tone];
  return (
    <span style={{ background: colors[0], color: colors[1], borderRadius: 999, padding: "3px 10px", fontSize: 12, fontWeight: 600 }}>
      <span style={{ display: "inline-block", width: 7, height: 7, borderRadius: 999, background: colors[1], marginRight: 6, verticalAlign: 1 }} />
      {text}
    </span>
  );
}

function JobCard({ status, nowMs }: { status: EngineStatus; nowMs: number }) {
  const job = status.job;
  const prog = status.training?.progress ?? null;
  const tone = job.kind === "unknown" ? "#b91c1c" : job.kind === "idle" ? MUTED : ACCENT;
  return (
    <section style={{ ...CARD, borderLeft: `5px solid ${tone}` }}>
      <div style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.6, color: MUTED }}>Now</div>
      <div style={{ fontSize: 20, fontWeight: 700, marginTop: 2 }}>{job.title}</div>
      {job.detail && <div style={{ color: MUTED, marginTop: 2 }}>{job.detail}</div>}

      {job.progress != null && (
        <>
          <div style={{ marginTop: 12, height: 10, borderRadius: 999, background: "#eef2f7", overflow: "hidden" }}>
            <div style={{ width: `${Math.round(job.progress * 100)}%`, height: "100%", background: ACCENT, transition: "width .6s" }} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: 14 }}>
            <span>
              <strong>{fmtDuration(job.eta_s)}</strong> <span style={{ color: MUTED }}>left</span>
            </span>
            <span style={{ color: MUTED }}>
              {job.step != null && job.total != null ? `${job.step.toLocaleString()} / ${job.total.toLocaleString()} steps` : `${Math.round(job.progress * 100)}%`}
            </span>
          </div>
          {prog && (
            <div style={{ color: MUTED, fontSize: 13, marginTop: 4 }}>
              {prog.s_per_it != null && `${prog.s_per_it.toFixed(2)} s/step`}
              {prog.loss != null && ` · loss ${prog.loss.toFixed(4)}`}
              {prog.elapsed_s != null && ` · ${fmtDuration(prog.elapsed_s)} elapsed`}
            </div>
          )}
        </>
      )}

      {job.kind === "idle" && status.training?.progress && !status.training.active && (
        <div style={{ color: MUTED, fontSize: 13, marginTop: 8 }}>
          Last training: {status.training.character ?? "LoRA"} · {status.training.progress.step}/{status.training.progress.total} steps
          {status.training.log_mtime != null && ` · finished ${fmtDuration(nowMs / 1000 - status.training.log_mtime)} ago`}
        </div>
      )}
    </section>
  );
}

function Ring({ value, unknown }: { value: number | null; unknown: boolean }) {
  const r = 54;
  const c = 2 * Math.PI * r;
  const frac = value == null ? null : value / 100;
  const label = unknown ? "?" : value == null ? "—" : `${Math.round(value)}%`;
  const caption = unknown ? "unreadable" : value == null ? "no data" : value > 20 ? "busy" : "idle";
  return (
    <div style={{ textAlign: "center" }}>
      <svg width={132} height={132} viewBox="0 0 132 132" role="img" aria-label={`GPU utilisation ${label}`}>
        <circle cx={66} cy={66} r={r} fill="none" stroke="#eef2f7" strokeWidth={11} />
        <circle
          cx={66}
          cy={66}
          r={r}
          fill="none"
          stroke={unknown ? "#b91c1c" : ACCENT}
          strokeWidth={11}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={ringOffset(unknown ? 1 : frac, c)}
          transform="rotate(-90 66 66)"
          style={{ transition: "stroke-dashoffset .6s" }}
        />
        <text x={66} y={62} textAnchor="middle" fontSize={26} fontWeight={700} fill="#111">
          {label}
        </text>
        <text x={66} y={84} textAnchor="middle" fontSize={12} fill={MUTED}>
          {caption}
        </text>
      </svg>
    </div>
  );
}

function Vram({ used, total, unknown }: { used: number | null; total: number | null; unknown: boolean }) {
  const frac = used != null && total ? used / total : 0;
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14 }}>
        <span style={{ fontWeight: 600 }}>VRAM</span>
        <span style={{ color: MUTED }}>{unknown ? "unreadable" : `${fmtGb(used)} / ${fmtGb(total)} GB`}</span>
      </div>
      <div style={{ marginTop: 6, height: 10, borderRadius: 999, background: "#eef2f7", overflow: "hidden" }}>
        <div style={{ width: `${Math.round(frac * 100)}%`, height: "100%", background: frac > 0.92 ? "#dc2626" : ACCENT, transition: "width .6s" }} />
      </div>
    </div>
  );
}

function Sparkline({ points }: { points: HistoryPoint[] }) {
  const w = 440;
  const h = 48;
  const path = sparklinePoints(points.map((p) => p.util), w, h);
  const minutes = points.length > 1 ? Math.round((points[points.length - 1].t - points[0].t) / 60) : 0;
  return (
    <section style={{ ...CARD, marginTop: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: MUTED, marginBottom: 6 }}>
        <span>Utilisation</span>
        <span>{minutes > 0 ? `last ${minutes} min` : "collecting…"}</span>
      </div>
      <svg width="100%" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: "block", height: 48 }}>
        <line x1={0} y1={h} x2={w} y2={h} stroke="#eef2f7" />
        {path && <polyline points={path} fill="none" stroke={ACCENT} strokeWidth={2} vectorEffect="non-scaling-stroke" />}
      </svg>
    </section>
  );
}

function ComfyLine({ status }: { status: EngineStatus }) {
  const c = status.comfyui;
  const text = !c
    ? "ComfyUI: unknown"
    : !c.reachable
      ? "ComfyUI: not running"
      : c.running === 0 && c.pending === 0
        ? "ComfyUI: up, queue empty"
        : `ComfyUI: ${c.running} rendering${c.pending ? `, ${c.pending} queued` : ""}${c.labels[0] ? ` — ${c.labels[0]}` : ""}`;
  return <p style={{ color: MUTED, fontSize: 13, marginTop: 12, textAlign: "center" }}>{text}</p>;
}
