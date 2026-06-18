import { describe, it, expect } from "vitest";
import { congestionColor, formatInr } from "./api";

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
