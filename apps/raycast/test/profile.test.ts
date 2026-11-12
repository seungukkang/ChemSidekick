import { describe, expect, it } from "vitest";
import type { RunResponse, ToolListResponse } from "../src/lib/contract";
import {
  EXAMPLE_STATE,
  pathsText,
  productFieldTitle,
  profileInput,
  type ProfileState,
  solventChoices,
  temperatureOf,
  tsFieldTitle,
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

  it("temperature: a preset, or the typed one", () => {
    expect(temperatureOf(state({ temperature: "195.15" }))).toBe("195.15");
    expect(temperatureOf(state({ temperature: "custom", customTemperature: "40 C" }))).toBe("40 C");
    expect(temperatureOf(state({ temperature: "custom", customTemperature: " " }))).toBe("298.15");
  });

  it("populations send only the states", () => {
    expect(profileInput(state({ mode: "populations", unit: "Eh" }))).toEqual({
      mode: "populations",
      unit: "Eh",
      temperature: "298.15",
      states: EXAMPLE_STATE.states,
    });
  });

  it("targets are sent when filled in", () => {
    const input = profileInput(state({ targetHalfLife: "1h", targetSelectivity: "90% ee" }));
    expect(input).toMatchObject({ target_half_life: "1h", target_selectivity: "90% ee" });
  });

  it("field titles follow what the values are", () => {
    expect(tsFieldTitle(state())).toBe("ΔG‡ (kcal/mol)");
    expect(tsFieldTitle(state({ tsValues: "rate constant", molecularity: "bimolecular" }))).toBe("k (M⁻¹ s⁻¹)");
    expect(productFieldTitle(state({ productValues: "equilibrium constant" }))).toBe("K");
  });

  it("solvent choices come from the tool's input schema", () => {
    const list = JSON.parse(fixture("list")) as ToolListResponse;
    const tool = list.tools.find((t) => t.name === "profile")!;
    const choices = solventChoices(tool.input_schema);
    expect(choices.map((c) => c.value)).toEqual(["water", "methanol", "toluene", "benzene", "custom"]);
    expect(choices.at(-1)?.title).toBe("Other (type its viscosity)");
  });
});

describe("profile result", () => {
  it("one wide drawing right under the answer", () => {
    const r = JSON.parse(fixture("profile-two-paths")) as RunResponse;
    const md = renderResult(r.result, r.run, { drawingWidth: 640 }).markdown;
    expect(md.startsWith("# Kinetic B : C = 96.7 : 3.3")).toBe(true);
    expect(md).toContain("profile.svg?raycast-width=640");
    expect(md.indexOf("profile.svg")).toBeLessThan(md.indexOf("| Path |"));
  });
});
