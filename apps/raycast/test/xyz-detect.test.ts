import { describe, expect, it } from "vitest";
import { looksLikeXyz } from "../src/lib/xyz-detect";

const WATER = "3\nwater\nO 0 0 0.1173\nH 0 0.7572 -0.4692\nH 0 -0.7572 -0.4692\n";

describe("looksLikeXyz", () => {
  it("accepts standard XYZ and bare coordinate lines", () => {
    expect(looksLikeXyz(WATER)).toBe(true);
    expect(looksLikeXyz("C 0.000 1.397 0.000\nH 0.000 2.481 0.000")).toBe(true);
  });

  it("accepts atomic numbers, numbered labels, Fortran exponents, extra columns", () => {
    expect(looksLikeXyz("6 0 0 0\n1 0 0 1.09")).toBe(true);
    expect(looksLikeXyz("C1 0 0 0\nH2 0 0 1.09")).toBe(true);
    expect(looksLikeXyz("CL 1.0D-01 0 0\nC 0 0 1.77D+00")).toBe(true);
    expect(looksLikeXyz("O 0 0 0 -0.82\nH 0 0.76 -0.47 0.41")).toBe(true);
  });

  it("rejects other clipboard text", () => {
    expect(looksLikeXyz(undefined)).toBe(false);
    expect(looksLikeXyz("CC(Br)C(Br)C")).toBe(false);
    expect(looksLikeXyz("Meeting at 3 pm\nRoom 2 4 5")).toBe(false); // one matching line only
    expect(looksLikeXyz("O 0 0")).toBe(false);
  });
});
