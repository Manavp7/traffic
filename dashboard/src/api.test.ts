import { describe, it, expect } from "vitest";
import { congestionColor, formatInr, buildReportCsv } from "./api";

describe("congestionColor", () => {
  it("maps score ranges to colors", () => {
    expect(congestionColor(10)).toBe("#22c55e"); // free
    expect(congestionColor(40)).toBe("#eab308"); // moderate
    expect(congestionColor(60)).toBe("#f97316"); // heavy
    expect(congestionColor(90)).toBe("#ef4444"); // severe
  });
});

describe("formatInr", () => {
  it("formats lakh and crore", () => {
    expect(formatInr(2.5e7)).toContain("cr");
    expect(formatInr(3e5)).toContain("L");
    expect(formatInr(5000)).toContain("₹");
  });
});

describe("buildReportCsv", () => {
  it("includes economics, segments and recommendations", () => {
    const csv = buildReportCsv(
      { cost_human: "₹1.34 cr", delay_veh_h: 1000, fuel_litres: 900, co2_kg: 2000 },
      [{ scope_id: "S66", delay_veh_h: 500, cost_inr: 12345 }],
      [{ action_type: "divert", target: "S66", expected_effect: "divert via D", rationale: "queue" }]
    );
    expect(csv).toContain("Economic Impact");
    expect(csv).toContain("S66");
    expect(csv).toContain("divert");
    expect(csv).toContain("Recommendations");
  });
});
