/**
 * Server-side client for the local engine monitor (`sourcemode monitor serve`).
 *
 * The browser never talks to the engine directly: route handlers under
 * /api/engine proxy to it. Locally that is 127.0.0.1:8787; on Vercel there is
 * no engine, and every call resolves to "unreachable" — a state the UI renders,
 * not an error.
 */

const DEFAULT_ENGINE_URL = "http://127.0.0.1:8787";

export function engineUrl(): string {
  return process.env.ENGINE_URL || DEFAULT_ENGINE_URL;
}

export async function fetchEngine<T>(path: string, timeoutMs = 3000): Promise<T | null> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(engineUrl() + path, { signal: ctrl.signal, cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

// Shapes produced by engine/sourcemode/monitor/sampler.py.
export type GpuSample = {
  name: string;
  util_pct: number | null;
  mem_used_mb: number | null;
  mem_total_mb: number | null;
  temp_c: number | null;
  power_w: number | null;
  power_limit_w: number | null;
};

export type TrainingProgress = {
  step: number;
  total: number;
  elapsed_s: number | null;
  eta_s: number | null;
  s_per_it: number | null;
  loss: number | null;
};

export type TrainingState = {
  active: boolean;
  process: boolean | null;
  log: string | null;
  character: string | null;
  progress: TrainingProgress | null;
  epoch: number | null;
  epochs: number | null;
  log_mtime: number | null;
};

export type ComfyState = {
  reachable: boolean;
  running: number;
  pending: number;
  labels: (string | null)[];
};

export type Job = {
  kind: "training" | "rendering" | "busy" | "idle" | "unknown";
  title: string;
  detail: string | null;
  progress: number | null;
  eta_s: number | null;
  step?: number | null;
  total?: number | null;
};

export type EngineStatus = {
  sampled_at: number | null;
  uptime_s?: number;
  gpu: GpuSample | null;
  training: TrainingState | null;
  comfyui: ComfyState | null;
  job: Job;
};

export type HistoryPoint = { t: number; util: number | null; mem: number | null };
