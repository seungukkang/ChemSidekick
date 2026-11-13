// The Units view (REF-02): pure functions, tested against real csk responses.
//
// The search bar holds the value, a dropdown holds the unit; every unit of the
// same group is listed with its converted value, and the selected row shows its
// evidence (definitions, constants, sources) in the detail panel.
import type { ToolResult } from "./contract";

// ---------------------------------------------------------------------------
// Unit choices (the dropdown), from the tool's unit list (`csk run units {}`)
// ---------------------------------------------------------------------------

export interface UnitChoice {
  id: string; // "group:symbol", unique (nm is both a wavelength and a length)
  label: string; // shown, and sent to csk: it names exactly one unit (e.g. "nm (wavelength)")
  symbol: string;
  aliases: string[]; // extra search keywords in the dropdown
  more: boolean; // a less common unit
}

export interface UnitChoiceGroup {
  id: string;
  title: string;
  example: string;
  units: UnitChoice[];
}

interface ListedUnit {
  symbol: string;
  label: string;
  group: string;
  aliases: string[];
  more: boolean;
}

interface ListedGroup {
  id: string;
  title: string;
  example: string;
  units: ListedUnit[];
}

export const DEFAULT_UNIT = "energy:eV";

export function unitChoices(result: ToolResult): UnitChoiceGroup[] {
  const groups = (result.data["groups"] as ListedGroup[] | undefined) ?? [];
  return groups.map((g) => ({
    id: g.id,
    title: g.title,
    example: g.example,
    units: g.units.map((u) => ({
      id: `${u.group}:${u.symbol}`,
      label: u.label,
      symbol: u.symbol,
      aliases: u.aliases,
      more: u.more,
    })),
  }));
}

export function findChoice(groups: UnitChoiceGroup[], id: string): UnitChoice | undefined {
  for (const g of groups) {
    const u = g.units.find((x) => x.id === id);
    if (u) return u;
  }
  return undefined;
}

// The common units of a group, shown dimmed beside its name: "kcal/mol · kJ/mol · eV …".
export function groupSubtitle(group: UnitChoiceGroup, max = 6): string {
  const common = group.units.filter((u) => !u.more).map((u) => u.symbol);
  const shown = common.slice(0, max).join(" · ");
  return common.length > max || group.units.some((u) => u.more) ? `${shown} …` : shown;
}

// Search keywords of a group: every unit symbol and alias, so "torr" finds Pressure.
export function groupKeywords(group: UnitChoiceGroup): string[] {
  return [group.id, ...group.units.flatMap((u) => [u.symbol, u.label, ...u.aliases])];
}

// The unit a group starts with: its first common unit.
export function defaultUnit(group: UnitChoiceGroup): UnitChoice | undefined {
  return group.units.find((u) => !u.more) ?? group.units[0];
}

// A number as csk reads it: 1, -5, .5, 1.2e-3, 1.2×10⁻³, 1.2*10^-3, 2 x 10^9.
const NUMBER_ONLY =
  /^\s*[-+−]?(\d+(\.\d*)?|\.\d+)(\s*[eE]\s*[-+]?\d+|\s*[×xX*]\s*10\s*(\^|\*\*)?\s*[-+⁻⁺]?[\d⁰¹²³⁴⁵⁶⁷⁸⁹]+)?\s*$/;

export function isNumberOnly(text: string): boolean {
  return NUMBER_ONLY.test(text);
}

// What to ask csk: the typed value in the chosen unit. Text that is not just a
// number (e.g. "1 eV to kcal/mol") is sent as typed.
export function buildQuery(text: string, unit: UnitChoice | undefined): string | undefined {
  const t = text.trim();
  if (t && !isNumberOnly(t)) return t;
  if (!unit) return undefined;
  return `${t || "1"} ${unit.label}`;
}

// ---------------------------------------------------------------------------
// Results
// ---------------------------------------------------------------------------

export interface ConstantInfo {
  symbol: string;
  name: string;
  text: string;
  unit: string;
  exact: boolean;
  source: string;
}

export interface UnitRow {
  key: string;
  value: string; // 6 significant figures (e.g. "627.509")
  full: string; // full precision, for "Copy Full Precision"
  unit: string; // shown unit (e.g. "nm (wavelength)")
  symbol: string; // plain unit symbol, for "Copy with Unit"
  exact: boolean;
  definition: string; // how this unit relates to the base unit
  constants: string[]; // constant symbols used
}

export interface UnitSection {
  title: string;
  rows: UnitRow[];
}

export interface UnitResult {
  answer: string;
  input: string; // e.g. "1 eV"
  inputDefinition: string;
  inputConstants: string[];
  temperature: number; // K, for RT and kT
  sections: UnitSection[];
  constants: Record<string, ConstantInfo>;
  warnings: string[];
}

interface Described {
  symbol: string;
  label: string;
  group_title: string;
  exact: boolean;
  definition: string;
  constants: string[];
}

interface Conversion extends Described {
  value: number;
  text: string;
}

interface Thermal {
  quantity: string;
  value: number;
  text: string;
  unit: string;
  definition: string;
  constants: string[];
}

interface Query {
  value: number;
  unit: Described;
  temperature_K: number;
}

// Full precision as JavaScript prints it: the shortest text that reads back to the same number.
export function fullPrecision(value: number): string {
  return String(value);
}

export function unitResult(result: ToolResult): UnitResult {
  const query = result.data["query"] as Query;
  const sections: UnitSection[] = [];
  const target = result.data["result"] as { unit: Described } | undefined;
  const conversions = (result.data["conversions"] as Conversion[] | undefined) ?? [];
  const toRow = (c: Conversion): UnitRow => ({
    key: `${c.group_title}:${c.symbol}`,
    value: c.text,
    full: fullPrecision(c.value),
    unit: c.label,
    symbol: c.symbol,
    exact: c.exact,
    definition: c.definition,
    constants: c.constants,
  });
  if (target) {
    const hit = conversions.find((c) => c.symbol === target.unit.symbol && c.label === target.unit.label);
    if (hit) sections.push({ title: "Result", rows: [{ ...toRow(hit), key: "result" }] });
  }
  for (const c of conversions) {
    let section = sections.find((s) => s.title === c.group_title);
    if (!section) {
      section = { title: c.group_title, rows: [] };
      sections.push(section);
    }
    section.rows.push(toRow(c));
  }
  const thermal = (result.data["thermal"] as Thermal[] | undefined) ?? [];
  if (thermal.length) {
    sections.push({
      title: `RT and kT at ${formatKelvin(query.temperature_K)}`,
      rows: thermal.map((t) => ({
        key: `thermal:${t.quantity}:${t.unit}`,
        value: t.text,
        full: fullPrecision(t.value),
        unit: `${t.unit} (${t.quantity})`,
        symbol: t.unit,
        exact: true,
        definition: t.definition,
        constants: t.constants,
      })),
    });
  }
  return {
    answer: result.answer,
    input: `${formatInput(query.value)} ${query.unit.symbol}`,
    inputDefinition: query.unit.definition,
    inputConstants: query.unit.constants,
    temperature: query.temperature_K,
    sections,
    constants: (result.data["constants"] as Record<string, ConstantInfo> | undefined) ?? {},
    warnings: result.warnings,
  };
}

function formatInput(value: number): string {
  return Number.isInteger(value) || Math.abs(value) >= 1e-3 ? String(Number(value.toPrecision(10))) : String(value);
}

export function formatKelvin(k: number): string {
  return `${Number(k.toFixed(2))} K (${(k - 273.15).toFixed(2)} °C)`;
}

// ---------------------------------------------------------------------------
// The detail panel of one row
// ---------------------------------------------------------------------------

export interface DetailLine {
  title: string;
  text: string;
}

export interface RowDetail {
  heading: string; // markdown heading, e.g. "1 eV = 23.0605 kcal/mol"
  facts: DetailLine[]; // full precision, exactness
  definitions: DetailLine[]; // how each unit relates to the base unit
  constants: DetailLine[]; // constants used, with value
  sources: string[]; // one line per document
}

export function rowDetail(r: UnitResult, row: UnitRow): RowDetail {
  const thermal = row.key.startsWith("thermal:");
  const quantity = row.unit.endsWith("(RT)") ? "RT" : "kT";
  const heading = thermal
    ? `${quantity} = ${row.value} ${row.symbol}`
    : `${r.input} ${row.exact ? "=" : "≈"} ${row.value} ${row.symbol}`;
  const facts: DetailLine[] = [{ title: "Full precision", text: row.full }];
  if (thermal) facts.push({ title: "Temperature", text: formatKelvin(r.temperature) });
  facts.push({
    title: "Exactness",
    text: row.exact ? "Exact (defined constants only)" : "≈ (uses a measured constant, CODATA 2022)",
  });
  const definitions: DetailLine[] = thermal
    ? [{ title: quantity, text: row.definition }]
    : [
        { title: r.input.replace(/^\S+ /, "1 "), text: r.inputDefinition },
        { title: `1 ${row.symbol}`, text: row.definition },
      ];
  const keys = [...new Set([...(thermal ? [] : r.inputConstants), ...row.constants])];
  const order = Object.keys(r.constants);
  keys.sort((a, b) => order.indexOf(a) - order.indexOf(b));
  const constants = keys
    .map((k) => r.constants[k])
    .filter((c): c is ConstantInfo => c !== undefined)
    .map((c) => ({ title: `${c.name} (${c.symbol})`, text: `${c.text} ${c.unit}${c.exact ? " (exact)" : ""}` }));
  const sources = [
    ...new Set(
      keys
        .map((k) => r.constants[k])
        .filter((c): c is ConstantInfo => c !== undefined)
        .map((c) => c.source.split(":")[0]),
    ),
  ];
  return { heading, facts, definitions: dedupe(definitions), constants, sources };
}

function dedupe(lines: DetailLine[]): DetailLine[] {
  return lines.filter((l, i) => lines.findIndex((x) => x.text === l.text) === i);
}
