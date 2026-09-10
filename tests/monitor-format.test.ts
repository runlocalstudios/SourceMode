import { describe, expect, it } from "vitest";
import { fmtDuration, fmtGb, ringOffset, sampleAge, sparklinePoints } from "../lib/monitor-format";

describe("fmtDuration", () => {
  it("formats hours, minutes, seconds", () => {
    expect(fmtDuration(13537)).toBe("3h 45m");
    expect(fmtDuration(754)).toBe("12m 34s");
    expect(fmtDuration(45)).toBe("45s");
    expect(fmtDuration(0)).toBe("0s");
  });
  it("renders unknown as a dash, never NaN", () => {
    expect(fmtDuration(null)).toBe("—");
    expect(fmtDuration(undefined)).toBe("—");
    expect(fmtDuration(-5)).toBe("—");
    expect(fmtDuration(Number.NaN)).toBe("—");
  });
});

describe("fmtGb", () => {
  it("converts MB to GB with one decimal", () => {
    expect(fmtGb(23835)).toBe("23.3");
    expect(fmtGb(32607)).toBe("31.8");
    expect(fmtGb(null)).toBe("—");
  });
});

describe("ringOffset", () => {
  it("covers the ring proportionally and clamps", () => {
    expect(ringOffset(0, 100)).toBe(100);
    expect(ringOffset(1, 100)).toBe(0);
    expect(ringOffset(0.25, 100)).toBe(75);
    expect(ringOffset(1.7, 100)).toBe(0);
    expect(ringOffset(null, 100)).toBe(100);
  });
});

describe("sampleAge", () => {
  const now = 1_789_044_277_000;
  it("is live when fresh and stale after 15 s", () => {
    expect(sampleAge(now / 1000 - 2, now)).toEqual({ text: "live", stale: false });
    expect(sampleAge(now / 1000 - 9, now)).toEqual({ text: "9s ago", stale: false });
    expect(sampleAge(now / 1000 - 40, now)).toEqual({ text: "40s ago", stale: true });
    expect(sampleAge(null, now)).toEqual({ text: "no sample yet", stale: true });
  });
});

describe("sparklinePoints", () => {
  it("maps values to x,y pairs and skips gaps", () => {
    expect(sparklinePoints([0, 100], 100, 40)).toBe("0.0,40.0 100.0,0.0");
    expect(sparklinePoints([50, null, 50], 100, 40)).toBe("0.0,20.0 100.0,20.0");
    expect(sparklinePoints([], 100, 40)).toBe("");
    expect(sparklinePoints([100], 100, 40)).toBe("0.0,0.0");
  });
});
