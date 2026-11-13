import { describe, expect, it } from "vitest";
import type { RunResponse, ToolListResponse } from "../src/lib/contract";
import {
  EXAMPLE_STATE,
  formatSig,
  MAX_PATHS,
  optionsSummary,
  panelMarkdown,
  parsePaths,
  parseStates,
  pathsText,
  pathSubtitle,
  productLabel,
  profileInput,
  type ProfileState,
  solventChoices,
  statesText,
  stateSubtitle,
  temperatureOf,
  temperatureTitle,
  tsLabel,
  withTyped,
} from "../src/lib/profile";
import { renderResult } from "../src/lib/render";
import { fixture } from "./helpers";

const state = (patch: Partial<ProfileState> = {}): ProfileState => ({ ...EXAMPLE_STATE, ...patch });

describe("profile form -> tool input", () => {
  it("the example draws two paths", () => {
    expect(profileInput(state())).toEqual({
      mode: "reaction",
      unit: "kcal/mol",
      temperature: "298.15",
      paths: "B\t20.0\t-3.0\nC\t22.0\t-5.0",
      ts_values: "barrier",
      product_values: "free energy",
      molecularity: "unimolecular",
    });
  });

  it("empty values become '-', empty rows are left out, names default to P1, P2", () => {
    expect(
      pathsText([
        { name: "", ts: "20", product: "" },
        { name: "C", ts: "", product: "" },
        { name: "two words", ts: " 1 h ", product: "-2" },
      ]),
    ).toBe("P1\t20\t-\ntwo_words\t1h\t-2");
  });

  it("bimolecular options appear only when they apply", () => {
    const uni = profileInput(state({ control: "diffusion", partner: "0.1" }));
    expect(uni).not.toHaveProperty("control");
    const bi = profileInput(
      state({
        molecularity: "bimolecular",
        control: "diffusion",
        solvent: "custom",
        viscosity: "0.34",
        partner: "0.1",
      }),
    );
    expect(bi).toMatchObject({
      control: "diffusion",
      solvent: "custom",
      viscosity: 0.34,
      partner: 0.1,
      standard_state: "1 M",
    });
  });

  it("temperature: as typed, a bare number in K", () => {
    expect(temperatureOf(state({ temperature: "195.15" }))).toBe("195.15");
    expect(temperatureOf(state({ temperature: "40 C" }))).toBe("40 C");
    expect(temperatureOf(state({ temperature: " " }))).toBe("298.15");
    expect(temperatureTitle(state({ temperature: "350" }))).toBe("350 K");
    expect(temperatureTitle(state({ temperature: "-78 °C" }))).toBe("-78 °C");
  });

  it("populations send only the states", () => {
    expect(profileInput(state({ mode: "populations", unit: "Eh" }))).toEqual({
      mode: "populations",
      unit: "Eh",
      temperature: "298.15",
      states: "conf1\t0.0\nconf2\t0.5\nconf3\t1.0",
    });
  });

  it("hartree is for populations only", () => {
    expect(profileInput(state({ unit: "Eh" })).unit).toBe("kcal/mol");
  });

  it("states: empty energies are left out, degeneracy only when given", () => {
    expect(
      statesText([
        { name: "a", energy: "0", degeneracy: "" },
        { name: "", energy: "", degeneracy: "" },
        { name: "", energy: "1.2", degeneracy: "2" },
      ]),
    ).toBe("a\t0\ns3\t1.2\t2");
  });

  it("targets are sent when filled in", () => {
    const input = profileInput(state({ targetHalfLife: "1h", targetSelectivity: "90% ee" }));
    expect(input).toMatchObject({ target_half_life: "1h", target_selectivity: "90% ee" });
  });

  it("labels follow what the values are", () => {
    expect(tsLabel(state())).toBe("ΔG‡ (kcal/mol)");
    expect(tsLabel(state({ tsValues: "rate constant", molecularity: "bimolecular" }))).toBe("k (M⁻¹ s⁻¹)");
    expect(productLabel(state({ productValues: "equilibrium constant" }))).toBe("K");
    expect(pathSubtitle(state(), { name: "B", ts: "20.0", product: "" })).toBe("ΔG‡ 20.0   →   ΔG ?");
  });

  it("a state shows its energy to 3 significant figures with the unit, and g when not 1", () => {
    expect(stateSubtitle({ name: "a", energy: "0.5", degeneracy: "" }, "kcal/mol")).toBe("E 0.500 kcal/mol");
    expect(stateSubtitle({ name: "a", energy: "1.2", degeneracy: "2" }, "kJ/mol")).toBe("E 1.20 kJ/mol   ·   g = 2");
    expect(stateSubtitle({ name: "a", energy: "12.345", degeneracy: "" }, "eV")).toBe("E 12.3 eV");
    expect(stateSubtitle({ name: "a", energy: "0", degeneracy: "" }, "kcal/mol")).toBe("E 0 kcal/mol");
    expect(stateSubtitle({ name: "a", energy: "", degeneracy: "" }, "eV")).toBe("E ?");
    // absolute Hartree energies stay as typed (differences sit in the 4th-6th decimal)
    expect(stateSubtitle({ name: "a", energy: "-234.123456", degeneracy: "" }, "Eh")).toBe("E -234.123456 Eh");
  });

  it("only the display is rounded: the tool gets the energies as typed", () => {
    const states = [
      { name: "a", energy: "0.12345", degeneracy: "" },
      { name: "b", energy: "12.345", degeneracy: "" },
    ];
    expect(stateSubtitle(states[1], "kcal/mol")).toBe("E 12.3 kcal/mol");
    expect(profileInput(state({ mode: "populations", states })).states).toBe("a\t0.12345\nb\t12.345");
  });

  it("3 significant figures, as in the Python results", () => {
    const cases: [number, string][] = [
      [51, "51.0"],
      [0.013588, "0.0136"],
      [158.1, "158"],
      [999.6, "1.00 × 10³"],
      [4.647e-4, "4.65 × 10⁻⁴"],
      [-2.5, "-2.50"],
    ];
    for (const [x, text] of cases) expect(formatSig(x)).toBe(text);
  });

  it("the More options subtitle lists only what differs from the defaults", () => {
    expect(optionsSummary(state())).toBe("");
    expect(
      optionsSummary(
        state({ molecularity: "bimolecular", control: "diffusion", solvent: "toluene", targetHalfLife: "1h" }),
      ),
    ).toBe("bimolecular · diffusion (toluene) · t½ 1h");
  });

  it("solvent choices come from the tool's input schema", () => {
    const list = JSON.parse(fixture("list")) as ToolListResponse;
    const tool = list.tools.find((t) => t.name === "profile")!;
    const choices = solventChoices(tool.input_schema);
    expect(choices.map((c) => c.value)).toEqual(["water", "methanol", "toluene", "benzene", "custom"]);
    expect(choices.at(-1)?.title).toBe("Other (type its viscosity)");
  });
});

describe("rows typed in the search bar", () => {
  it("name, TS, product; or without a name; '-' for unknown", () => {
    expect(parsePaths("D 21 -4")).toEqual([{ name: "D", ts: "21", product: "-4" }]);
    expect(parsePaths("21, -4")).toEqual([{ name: "", ts: "21", product: "-4" }]);
    expect(parsePaths("D - -4")).toEqual([{ name: "D", ts: "", product: "-4" }]);
    expect(parsePaths("E 30min")).toEqual([{ name: "E", ts: "30min", product: "" }]);
    expect(parsePaths("D 21 -4; E 23 -1")).toHaveLength(2);
  });

  it("text that is not a path is not read", () => {
    for (const t of ["D", "D x y", "D 1 2 3", "D - -", ""]) expect(parsePaths(t)).toBeNull();
  });

  it("states: name, energy, optional degeneracy", () => {
    expect(parseStates("conf4 1.2")).toEqual([{ name: "conf4", energy: "1.2", degeneracy: "" }]);
    expect(parseStates("conf4 1.2 2")).toEqual([{ name: "conf4", energy: "1.2", degeneracy: "2" }]);
    expect(parseStates("conf4")).toBeNull();
  });

  it("typed rows are added after the others, unnamed ones numbered", () => {
    const s = withTyped(state(), "21 -4")!;
    expect(s.paths.at(-1)).toEqual({ name: "P3", ts: "21", product: "-4" });
    const full = state({ paths: Array.from({ length: MAX_PATHS }, () => ({ name: "X", ts: "20", product: "" })) });
    expect(withTyped(full, "D 21 -4")).toBeNull();
    expect(withTyped(state({ mode: "populations" }), "conf4 1.2")!.states).toHaveLength(4);
  });
});

describe("populations in the panel", () => {
  const result = (states: object[], top: number) => {
    const r = JSON.parse(fixture("profile-two-paths")) as RunResponse;
    return {
      ...r.result,
      answer: "conf1 55.6 % · 4 of 5 states cover 95 %",
      data: { mode: "populations", unit: "kcal/mol", states, top_95_count: top },
    };
  };
  const share = (label: string, energy: number, percent: number, in_top_95: boolean) => ({
    label,
    energy,
    percent,
    percent_text: percent.toFixed(1),
    in_top_95,
  });

  it("the 95 % states as a table, most populated first; the rest folded under the rule", () => {
    const r = result(
      [
        share("conf2", 0.35, 30.8, true),
        share("conf3", 10.9, 1.15e-8, false),
        share("conf1", 0, 55.6, true),
        share("conf5", 1.06, 6.2, true),
        share("conf4", 0.97, 7.3, true),
      ],
      4,
    );
    const md = panelMarkdown(r, 460);
    expect(md.slice(md.indexOf("| State"))).toBe(
      [
        "| State | ΔG (kcal/mol) | Ratio (%) |",
        "|:--|--:|--:|",
        "| conf1 | 0.00 | **55.6** |",
        "| conf2 | 0.35 | **30.8** |",
        "| conf4 | 0.97 | **7.3** |",
        "| conf5 | 1.06 | **6.2** |",
        "",
        "---",
        "",
        "4 of 5 states cover 95 % · conf3 < 0.1 %",
      ].join("\n"),
    );
  });

  it("many states outside 95 % become one line", () => {
    const states = [share("a", 0, 96, true), ...Array.from({ length: 38 }, (_, i) => share(`c${i}`, 2, 4 / 38, false))];
    expect(panelMarkdown(result(states, 1), 460)).toMatch(/1 of 39 states cover 95 % · 38 more, 4\.0 % in total$/);
  });

  it("one state: no rule, no count", () => {
    expect(panelMarkdown(result([share("only", 0, 100, true)], 1), 460)).toMatch(
      /\| only \| 0\.00 \| \*\*100\.0\*\* \|$/,
    );
  });
});

describe("profile result", () => {
  it("the panel: the drawing, then the answer one part per line", () => {
    const r = JSON.parse(fixture("profile-two-paths")) as RunResponse;
    const md = panelMarkdown(r.result, 460);
    expect(md.startsWith("![")).toBe(true);
    expect(md).toContain("profile.svg?raycast-width=460");
    expect(md).toContain("**Kinetic B : C = 96.7 : 3.3**  \n**Equilibrium B : C = 3.3 : 96.7**");
    expect(md).toContain("t½ via B: **51.0 s** · k = 0.0136 s⁻¹");
  });

  it("formulas drawn in the profile are not repeated as raw LaTeX", () => {
    const r = JSON.parse(fixture("profile-two-paths")) as RunResponse;
    expect(r.result.formulas.every((f) => f.in_drawing)).toBe(true);
    expect(renderResult(r.result, r.run, { drawingWidth: 640 }).markdown).not.toContain("$$");
  });

  it("one wide drawing right under the answer", () => {
    const r = JSON.parse(fixture("profile-two-paths")) as RunResponse;
    const md = renderResult(r.result, r.run, { drawingWidth: 640 }).markdown;
    expect(md.startsWith("# Kinetic B : C = 96.7 : 3.3")).toBe(true);
    expect(md).toContain("profile.svg?raycast-width=640");
    expect(md.indexOf("profile.svg")).toBeLessThan(md.indexOf("| Path |"));
  });
});
