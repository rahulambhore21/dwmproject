import { describe, expect, it } from "vitest";
import { compact, fixed, monthLabel, p, pct, relativeTime, signedNum, signedPct } from "./format";

describe("format", () => {
  it("formats rates and handles missing values", () => {
    expect(pct(0.0512, 2)).toBe("5.12%");
    expect(pct(null)).toBe("—");
    expect(pct(undefined)).toBe("—");
    expect(pct(Number.NaN)).toBe("—");
  });
  it("signs deltas with a true minus", () => {
    expect(signedPct(4.9)).toBe("+4.9%");
    expect(signedPct(-3.25, 2)).toBe("−3.25%");
    expect(signedPct(0)).toBe("0.0%");
    expect(signedNum(-0.5)).toBe("−0.50");
  });
  it("compacts large numbers", () => {
    expect(compact(14793)).toBe("14.8K");
    expect(compact(null)).toBe("—");
  });
  it("formats p-values without false precision", () => {
    expect(p(0.0004)).toBe("p<0.001");
    expect(p(0.0431)).toBe("p=0.043");
    expect(p(null)).toBe("—");
  });
  it("labels months and relative time", () => {
    expect(monthLabel("2026-03")).toMatch(/Mar/);
    const now = new Date("2026-10-04T12:00:00Z");
    expect(relativeTime("2026-10-04T11:00:00Z", now)).toBe("1 h ago");
    expect(relativeTime("2026-10-01T12:00:00Z", now)).toBe("3 d ago");
    expect(fixed(0.12345, 3)).toBe("0.123");
  });
});
