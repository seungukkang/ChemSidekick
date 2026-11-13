// The Energy Profile view (ENE-01): its state, the rows typed in the search bar,
// and how the state becomes the tool's input. Pure functions, tested without Raycast.
import type { ToolResult } from "./contract";

export interface PathRow {
  name: string; // product name, e.g. "B"
  ts: string; // barrier, k, or t½ (as typed)
  product: string; // ΔG or K (as typed)
}

export interface StateRow {
  name: string; // e.g. "conf1"
  energy: string;
  degeneracy: string; // empty: 1
}

export type Mode = "reaction" | "populations";

export interface ProfileState {
  mode: Mode;
  unit: string;
  temperature: string; // as typed: a number in K, or with a unit (40 C)
  tsValues: string;
  productValues: string;
  molecularity: "unimolecular" | "bimolecular";
  control: "activation" | "diffusion";
  solvent: string;
  viscosity: string;
  partner: string;
  standardState: string;
  paths: PathRow[];
  states: StateRow[];
  targetHalfLife: string;
  targetSelectivity: string;
}

export const UNITS: { value: string; title: string }[] = [
  { value: "kcal/mol", title: "kcal/mol" },
  { value: "kJ/mol", title: "kJ/mol" },
  { value: "eV", title: "eV" },
  { value: "Eh", title: "Hartree (absolute energies)" }, // populations only
];

export const EXAMPLE_STATE: ProfileState = {
  mode: "reaction",
  unit: "kcal/mol",
  temperature: "298.15",
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
  states: [
    { name: "conf1", energy: "0.0", degeneracy: "" },
    { name: "conf2", energy: "0.5", degeneracy: "" },
    { name: "conf3", energy: "1.0", degeneracy: "" },
  ],
  targetHalfLife: "",
  targetSelectivity: "",
};

export const MAX_PATHS = 6;
export const MAX_STATES = 50;

export function unitChoices(mode: Mode): { value: string; title: string }[] {
  return mode === "populations" ? UNITS : UNITS.filter((u) => u.value !== "Eh");
}

// Short labels of what the TS and product values are.
export function tsLabel(s: ProfileState): string {
  if (s.tsValues === "rate constant") return s.molecularity === "bimolecular" ? "k (M⁻¹ s⁻¹)" : "k (s⁻¹)";
  if (s.tsValues === "half-life") return "t½";
  return `ΔG‡ (${s.unit})`;
}

export function productLabel(s: ProfileState): string {
  return s.productValues === "equilibrium constant" ? "K" : `ΔG (${s.unit})`;
}

export function temperatureOf(s: ProfileState): string {
  return s.temperature.trim() || "298.15";
}

// "298.15" -> "298.15 K" (a bare number is in kelvin); "40 C" stays as typed.
export function temperatureTitle(s: ProfileState): string {
  const t = temperatureOf(s);
  return /^[-+]?\d*\.?\d+$/.test(t) ? `${t} K` : t;
}

// A row in the list: "ΔG‡ 20.0  →  ΔG −3.0".
export function pathSubtitle(s: ProfileState, row: PathRow): string {
  const ts = s.tsValues === "rate constant" ? "k" : s.tsValues === "half-life" ? "t½" : "ΔG‡";
  const product = s.productValues === "equilibrium constant" ? "K" : "ΔG";
  return `${ts} ${row.ts.trim() || "?"}   →   ${product} ${row.product.trim() || "?"}`;
}

const SUPERSCRIPT: Record<string, string> = {
  "-": "⁻",
  "0": "⁰",
  "1": "¹",
  "2": "²",
  "3": "³",
  "4": "⁴",
  "5": "⁵",
  "6": "⁶",
  "7": "⁷",
  "8": "⁸",
  "9": "⁹",
};

// Exactly 3 significant figures, trailing zeros kept ('0.500', '12.3', '-2.50');
// scientific notation below 10⁻³ or from 10³ (same as format_sig in core/units.py).
export function formatSig(x: number, digits = 3): string {
  if (x === 0) return "0";
  if (!Number.isFinite(x)) return String(x);
  const [mantissa, exp] = x.toExponential(digits - 1).split("e");
  const exponent = Number(exp);
  if (exponent >= -3 && exponent < 3) return x.toFixed(Math.max(digits - 1 - exponent, 0));
  return `${mantissa} × 10${String(exponent).replace(/[-0-9]/g, (c) => SUPERSCRIPT[c])}`;
}

// A state in the list: "E 0.500 kcal/mol", and g when not 1. Relative energies are
// shown to 3 significant figures; absolute Hartree energies exactly as typed (their
// differences sit in the 4th-6th decimal).
export function stateSubtitle(row: StateRow, unit: string): string {
  const g = row.degeneracy.trim();
  const energy = row.energy.trim().replace("−", "-");
  const value = Number(energy);
  const shown = unit !== "Eh" && energy && Number.isFinite(value) ? formatSig(value) : energy;
  const e = energy ? `E ${shown} ${unit}` : "E ?";
  return `${e}${g && g !== "1" ? `   ·   g = ${g}` : ""}`;
}

// The options under "More options" that differ from the defaults, for its subtitle.
export function optionsSummary(s: ProfileState): string {
  if (s.mode === "populations") return "populations";
  const parts: string[] = [];
  if (s.tsValues !== "barrier") parts.push(`TS as ${s.tsValues}`);
  if (s.productValues !== "free energy") parts.push("products as K");
  if (s.molecularity === "bimolecular") {
    parts.push("bimolecular");
    if (s.control === "diffusion") parts.push(`diffusion (${s.solvent === "custom" ? "custom" : s.solvent})`);
    if (s.standardState === "1 atm") parts.push("1 atm");
  }
  if (s.targetHalfLife.trim()) parts.push(`t½ ${s.targetHalfLife.trim()}`);
  if (s.targetSelectivity.trim()) parts.push(s.targetSelectivity.trim());
  return parts.join(" · ");
}

// --- Rows typed in the search bar -------------------------------------------

const VALUE = /^([-+−]?(\d|\.\d)|-$)/; // a number, a time like 30min, or "-" for unknown

function tokens(part: string): string[] {
  return part
    .trim()
    .split(/[\s,]+/)
    .filter(Boolean);
}

// "D 21 -4" (name, TS, product), "21 -4", "D 21", "D - -4"; several separated by ";".
export function parsePaths(text: string): PathRow[] | null {
  const parts = text.split(/[;\n]/).filter((p) => p.trim());
  if (!parts.length) return null;
  const rows: PathRow[] = [];
  for (const part of parts) {
    const t = tokens(part);
    const name = t.length && !VALUE.test(t[0]) ? t.shift()! : "";
    if (!t.length || t.length > 2 || !t.every((x) => VALUE.test(x))) return null;
    const [ts = "-", product = "-"] = t;
    if (ts === "-" && product === "-") return null;
    rows.push({ name, ts: ts === "-" ? "" : ts, product: product === "-" ? "" : product.replace("−", "-") });
  }
  return rows;
}

// "conf4 1.2" (name, energy), "conf4 1.2 2" (with degeneracy); several separated by ";".
export function parseStates(text: string): StateRow[] | null {
  const parts = text.split(/[;\n]/).filter((p) => p.trim());
  if (!parts.length) return null;
  const rows: StateRow[] = [];
  for (const part of parts) {
    const t = tokens(part);
    const name = t.length && !VALUE.test(t[0]) ? t.shift()! : "";
    if (!t.length || t.length > 2 || !t.every((x) => VALUE.test(x) && x !== "-")) return null;
    rows.push({ name, energy: t[0].replace("−", "-"), degeneracy: t[1] ?? "" });
  }
  return rows;
}

// The state with the typed rows added (names default to the next free P3, conf4, ...).
export function withTyped(s: ProfileState, text: string): ProfileState | null {
  if (s.mode === "reaction") {
    const rows = parsePaths(text);
    if (!rows || s.paths.length + rows.length > MAX_PATHS) return null;
    const named = rows.map((r, i) => ({ ...r, name: r.name || `P${s.paths.length + i + 1}` }));
    return { ...s, paths: [...s.paths, ...named] };
  }
  const rows = parseStates(text);
  if (!rows || s.states.length + rows.length > MAX_STATES) return null;
  const named = rows.map((r, i) => ({ ...r, name: r.name || `s${s.states.length + i + 1}` }));
  return { ...s, states: [...s.states, ...named] };
}

// --- Tool input ----------------------------------------------------------------

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

export function statesText(states: StateRow[]): string {
  return states
    .map((r, i) => ({ ...r, name: r.name.trim() || `s${i + 1}` }))
    .filter((r) => r.energy.trim())
    .map((r) => {
      const name = r.name.replace(/\s+/g, "_");
      const g = r.degeneracy.trim();
      return [name, r.energy.trim(), ...(g ? [g] : [])].join("\t");
    })
    .join("\n");
}

// The tool's input (field names of ProfileInput in tools/energetics/profile.py).
export function profileInput(s: ProfileState): Record<string, unknown> {
  const unit = s.mode === "reaction" && s.unit === "Eh" ? "kcal/mol" : s.unit;
  const base = { mode: s.mode, unit, temperature: temperatureOf(s) };
  if (s.mode === "populations") return { ...base, states: statesText(s.states) };
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

// --- The live panel on the right -------------------------------------------------

// The drawing, then the answer one part per line (it is joined by " · ").
interface StateShare {
  label: string;
  energy: number; // relative, in the result's display unit
  percent: number;
  percent_text: string;
  in_top_95: boolean;
}

// A share for the folded line: one decimal, or "< 0.1" when it would read 0.0.
function shareText(percent: number): string {
  return percent < 0.05 ? "< 0.1" : percent.toFixed(1);
}

// Populations: the states that make up 95 %, most populated first, as a small
// table (State | ΔG | Ratio (%), only the ratio in bold); a rule; then how many states that is, with the rest
// folded into the same line. Undefined for a reaction result.
export function populationLines(result: ToolResult): string | undefined {
  const data = result.data as { mode?: string; unit?: string; states?: StateShare[]; top_95_count?: number };
  if (data.mode !== "populations" || !data.states?.length) return undefined;
  const states = [...data.states].sort((a, b) => b.percent - a.percent);
  const top = states.filter((s) => s.in_top_95);
  const rest = states.filter((s) => !s.in_top_95);
  const md = [
    `| State | ΔG (${data.unit ?? ""}) | Ratio (%) |`,
    "|:--|--:|--:|",
    ...top.map((s) => `| ${s.label} | ${s.energy.toFixed(2)} | **${s.percent_text}** |`),
  ];
  if (states.length > 1) {
    let summary = `${top.length} of ${states.length} states cover 95 %`;
    if (rest.length === 1) summary += ` · ${rest[0].label} ${shareText(rest[0].percent)} %`;
    if (rest.length > 1) {
      const total = rest.reduce((sum, s) => sum + s.percent, 0);
      summary += ` · ${rest.length} more, ${shareText(total)} % in total`;
    }
    md.push("", "---", "", summary);
  }
  return md.join("\n");
}

export function panelMarkdown(result: ToolResult, width: number): string {
  const md: string[] = [];
  for (const a of result.artifacts.filter((x) => x.kind === "svg" || x.kind === "png")) {
    md.push(`![${a.title || "profile"}](${encodeURI(a.path)}?raycast-width=${width})`, "");
  }
  for (const w of result.warnings) md.push(`> ⚠️ ${w}`, "");
  const populations = populationLines(result);
  if (populations) return [...md, populations].join("\n").trimEnd();
  md.push(
    result.answer
      .split(" · ")
      .map((line) => `**${line}**`)
      .join("  \n"),
    "",
  );
  // The key values (t½ per path, ...) as text, one per line, so the drawing keeps the room.
  const values = result.highlights.map((h) => `${h.label}: **${h.value}**${h.note ? ` · ${h.note}` : ""}`);
  if (values.length) md.push(values.join("  \n"));
  return md.join("\n").trimEnd();
}
