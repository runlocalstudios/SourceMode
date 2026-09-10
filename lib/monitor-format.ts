/** Pure formatting for the monitor page — kept out of the component so it can be tested. */

/** 13537 -> "3h 46m"; 754 -> "12m 34s"; 45 -> "45s"; null -> "—". */
export function fmtDuration(s: number | null | undefined): string {
  if (s == null || !Number.isFinite(s) || s < 0) return "—";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`;
  if (m > 0) return `${m}m ${String(sec).padStart(2, "0")}s`;
  return `${sec}s`;
}

/** Megabytes -> gigabytes with one decimal, as text. */
export function fmtGb(mb: number | null | undefined): string {
  if (mb == null || !Number.isFinite(mb)) return "—";
  return (mb / 1024).toFixed(1);
}

/** Fraction of the ring to leave *uncovered*, for stroke-dashoffset. Clamped. */
export function ringOffset(fraction: number | null | undefined, circumference: number): number {
  const f = fraction == null || !Number.isFinite(fraction) ? 0 : Math.min(1, Math.max(0, fraction));
  return circumference * (1 - f);
}

/** How old a sample is, in words, and whether it should count as stale (> 15 s). */
export function sampleAge(sampledAt: number | null | undefined, nowMs: number): { text: string; stale: boolean } {
  if (sampledAt == null) return { text: "no sample yet", stale: true };
  const age = Math.max(0, nowMs / 1000 - sampledAt);
  const stale = age > 15;
  if (age < 5) return { text: "live", stale };
  return { text: `${Math.round(age)}s ago`, stale };
}

/** Points for an SVG polyline from a series of 0–100 values, oldest first. */
export function sparklinePoints(values: (number | null)[], width: number, height: number): string {
  const n = values.length;
  if (n === 0) return "";
  const step = n > 1 ? width / (n - 1) : 0;
  return values
    .map((v, i) => {
      if (v == null || !Number.isFinite(v)) return null;
      const y = height - (Math.min(100, Math.max(0, v)) / 100) * height;
      return `${(i * step).toFixed(1)},${y.toFixed(1)}`;
    })
    .filter((p): p is string => p !== null)
    .join(" ");
}
