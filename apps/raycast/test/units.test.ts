import { describe, expect, it } from "vitest";
import type { ErrorResponse, RunResponse } from "../src/lib/contract";
import {
  buildQuery,
  DEFAULT_UNIT,
  defaultUnit,
  findChoice,
  groupKeywords,
  groupSubtitle,
  fullPrecision,
  isNumberOnly,
  rowDetail,
  unitChoices,
  unitResult,
} from "../src/lib/units";
import { fixture } from "./helpers";

const run = (name: string) => JSON.parse(fixture(name)) as RunResponse;

describe("unit choices (dropdown)", () => {
  const groups = unitChoices(run("units-list").result);

  it("every group with its units, ids unique even when a symbol repeats", () => {
    expect(groups.map((g) => g.title)).toContain("Pressure");
    const ids = groups.flatMap((g) => g.units.map((u) => u.id));
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toContain("equivalents:nm");
    expect(ids).toContain("length:nm");
  });

  it("the default unit exists; labels name one meaning", () => {
    expect(findChoice(groups, DEFAULT_UNIT)?.label).toBe("eV");
    expect(findChoice(groups, "equivalents:nm")?.label).toBe("nm (wavelength)");
    expect(findChoice(groups, "energy:Eh")?.aliases).toContain("hartree");
  });

  it("each group has an example", () => {
    for (const g of groups) expect(g.example).not.toBe("");
  });

  it("group rows: common units dimmed beside the name, … when there are more", () => {
    const energy = groups.find((g) => g.id === "energy")!;
    expect(groupSubtitle(energy)).toBe("kcal/mol · kJ/mol · J/mol · eV · meV · Eh …");
    const dipole = groups.find((g) => g.id === "dipole")!;
    expect(groupSubtitle(dipole)).toBe("D · e Å · C m · au");
  });

  it("typing a unit finds its group; a group starts at its first common unit", () => {
    const pressure = groups.find((g) => g.id === "pressure")!;
    expect(groupKeywords(pressure)).toContain("torr");
    expect(defaultUnit(pressure)?.symbol).toBe("Pa");
    expect(defaultUnit(groups.find((g) => g.id === "energy")!)?.symbol).toBe("kcal/mol");
  });
});

describe("buildQuery", () => {
  const eV = { id: "energy:eV", label: "eV", symbol: "eV", aliases: [], more: false };
  it.each(["1", "2.5", "-5", "−5", ".5", "1.2e-3", "1.2×10⁻³", "1.2*10^-3", "2 x 10^9"])(
    "a number (%s) is a value in the chosen unit",
    (text) => {
      expect(isNumberOnly(text)).toBe(true);
      expect(buildQuery(text, eV)).toBe(`${text} eV`);
    },
  );
  it("empty means 1", () => expect(buildQuery("  ", eV)).toBe("1 eV"));
  it("text with a unit is sent as typed", () => {
    expect(isNumberOnly("1 eV to kcal/mol")).toBe(false);
    expect(buildQuery("1 eV to kcal/mol", eV)).toBe("1 eV to kcal/mol");
  });
});

describe("unitResult and rowDetail", () => {
  it("conversion: the result first, then the groups, then RT and kT", () => {
    const r = unitResult(run("units-conversion").result);
    expect(r.sections.map((s) => s.title)).toEqual([
      "Result",
      "Energy",
      "Energy equivalents",
      "RT and kT at 298.15 K (25.00 °C)",
    ]);
    expect(r.sections[0].rows[0]).toMatchObject({ value: "23.0605", full: "23.06054783061903", symbol: "kcal/mol" });
    expect(r.input).toBe("1 eV");
  });

  it("a row's detail: heading, exactness, both unit definitions, constants and sources", () => {
    const r = unitResult(run("units-conversion").result);
    const d = rowDetail(r, r.sections[0].rows[0]);
    expect(d.heading).toBe("1 eV = 23.0605 kcal/mol");
    expect(d.facts).toContainEqual({ title: "Exactness", text: "Exact (defined constants only)" });
    expect(d.definitions.map((x) => x.title)).toEqual(["1 eV", "1 kcal/mol"]);
    expect(d.definitions[1].text).toContain("6.947695457 × 10⁻²¹ J");
    expect(d.constants.map((c) => c.title)).toEqual([
      "elementary charge (e)",
      "Avogadro constant (NA)",
      "thermochemical calorie (cal)",
    ]);
    expect(d.sources).toContain("SI Brochure, 9th ed. (BIPM, 2019)");
  });

  it("a measured constant makes the row approximate", () => {
    const r = unitResult(run("units-overview").result);
    const kcal = r.sections[0].rows.find((x) => x.symbol === "kcal/mol")!;
    const d = rowDetail(r, kcal);
    expect(d.heading).toBe("1 Eh ≈ 627.509 kcal/mol");
    expect(d.facts.find((f) => f.title === "Exactness")?.text).toContain("CODATA 2022");
    expect(d.constants.map((c) => c.title)).toContain("Hartree energy (Eh)");
  });

  it("RT and kT rows explain themselves", () => {
    const r = unitResult(run("units-overview").result);
    const rt = r.sections.at(-1)!.rows[0];
    const d = rowDetail(r, rt);
    expect(d.heading).toBe("RT = 0.592485 kcal/mol");
    expect(d.definitions).toEqual([{ title: "RT", text: "RT = N_A·k_B·T" }]);
    expect(d.facts).toContainEqual({ title: "Temperature", text: "298.15 K (25.00 °C)" });
  });

  it("a wavelength is listed with its energy equivalents only", () => {
    const r = unitResult(run("units-wavelength").result);
    expect(r.sections.map((s) => s.title)).toEqual([
      "Energy equivalents",
      "Energy",
      "RT and kT at 298.15 K (25.00 °C)",
    ]);
    const nm = r.sections[0].rows.find((x) => x.symbol === "nm")!;
    expect(rowDetail(r, nm).definitions[0].text).toContain("hc / λ");
  });

  it("an unknown unit is an input error", () => {
    const r = JSON.parse(fixture("units-error")) as ErrorResponse;
    expect(r.error.type).toBe("input");
    expect(r.error.message).toContain("Unknown unit 'foo'");
  });

  it("full precision keeps every digit", () => {
    expect(fullPrecision(4.359744722206e-18)).toBe("4.359744722206e-18");
  });
});
