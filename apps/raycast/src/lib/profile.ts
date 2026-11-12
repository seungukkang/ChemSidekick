// The Energy Profile form (ENE-01): its state and how it becomes the tool's input.
// Pure functions, tested without Raycast.

export interface PathRow {
  name: string; // product name, e.g. "B"
  ts: string; // barrier, k, or t½ (as typed)
  product: string; // ΔG or K (as typed)
}

export interface ProfileState {
  mode: "reaction" | "populations";
  unit: string;
  temperature: string; // a preset in K, or "custom"
  customTemperature: string;
  tsValues: string;
  productValues: string;
  molecularity: "unimolecular" | "bimolecular";
  control: "activation" | "diffusion";
  solvent: string;
  viscosity: string;
  partner: string;
  standardState: string;
  paths: PathRow[];
  states: string;
  targetHalfLife: string;
  targetSelectivity: string;
}

export const TEMPERATURE_PRESETS: { value: string; title: string }[] = [
  { value: "195.15", title: "−78 °C (dry ice)" },
  { value: "273.15", title: "0 °C" },
  { value: "298.15", title: "25 °C" },
  { value: "310.15", title: "37 °C" },
  { value: "333.15", title: "60 °C" },
  { value: "353.15", title: "80 °C" },
  { value: "373.15", title: "100 °C" },
];

export const EXAMPLE_STATE: ProfileState = {
  mode: "reaction",
  unit: "kcal/mol",
  temperature: "298.15",
  customTemperature: "",
  tsValues: "barrier",
  productValues: "free energy",
  molecularity: "unimolecular",
  control: "activation",
  solvent: "water",
  viscosity: "",
  partner: "",
  standardState: "1 M",
  paths: [
    { name: "B", ts: "20.0", product: "-3.0" },
    { name: "C", ts: "22.0", product: "-5.0" },
  ],
  states: "conf1  0.0\nconf2  0.5\nconf3  1.0",
  targetHalfLife: "",
  targetSelectivity: "",
};

export const MAX_PATHS = 6;

// What the TS and product fields hold, for their titles and placeholders.
export function tsFieldTitle(s: ProfileState): string {
  if (s.tsValues === "rate constant") return s.molecularity === "bimolecular" ? "k (M⁻¹ s⁻¹)" : "k (s⁻¹)";
  if (s.tsValues === "half-life") return "t½";
  return `ΔG‡ (${s.unit})`;
}

export function productFieldTitle(s: ProfileState): string {
  return s.productValues === "equilibrium constant" ? "K" : `ΔG (${s.unit})`;
}

export function temperatureOf(s: ProfileState): string {
  return s.temperature === "custom" ? s.customTemperature.trim() || "298.15" : s.temperature;
}

// One line per path with at least one value: "name<TAB>ts<TAB>product", "-" for empty.
export function pathsText(paths: PathRow[]): string {
  return paths
    .map((p, i) => ({ ...p, name: p.name.trim() || `P${i + 1}` }))
    .filter((p) => p.ts.trim() || p.product.trim())
    .map((p) =>
      [p.name.replace(/\s+/g, "_"), p.ts.trim().replace(/\s+/g, "") || "-", p.product.trim() || "-"].join("\t"),
    )
    .join("\n");
}

// The tool's input (field names of ProfileInput in tools/energetics/profile.py).
export function profileInput(s: ProfileState): Record<string, unknown> {
  const base = { mode: s.mode, unit: s.unit, temperature: temperatureOf(s) };
  if (s.mode === "populations") return { ...base, states: s.states };
  const input: Record<string, unknown> = {
    ...base,
    paths: pathsText(s.paths),
    ts_values: s.tsValues,
    product_values: s.productValues,
    molecularity: s.molecularity,
  };
  if (s.molecularity === "bimolecular") {
    input.control = s.control;
    input.standard_state = s.standardState;
    const partner = Number(s.partner);
    if (s.partner.trim() && Number.isFinite(partner) && partner > 0) input.partner = partner;
    if (s.control === "diffusion") {
      input.solvent = s.solvent;
      const eta = Number(s.viscosity);
      if (s.solvent === "custom" && s.viscosity.trim() && Number.isFinite(eta)) input.viscosity = eta;
    }
  }
  if (s.targetHalfLife.trim()) input.target_half_life = s.targetHalfLife.trim();
  if (s.targetSelectivity.trim()) input.target_selectivity = s.targetSelectivity.trim();
  return input;
}

// Solvent choices from the tool's input schema (enum of `solvent`): ids -> titles.
export function solventChoices(schema: Record<string, unknown>): { value: string; title: string }[] {
  const props = (schema["properties"] ?? {}) as Record<string, { enum?: string[] }>;
  const ids = props["solvent"]?.enum ?? ["water", "custom"];
  return ids.map((id) => ({
    value: id,
    title: id === "custom" ? "Other (type its viscosity)" : id.charAt(0).toUpperCase() + id.slice(1),
  }));
}
