// ToolResult -> what the Detail view shows. In a launcher the result comes
// first: warnings -> answer -> drawings -> tables -> evidence (formulas,
// constants, assumptions) -> notes and references. Pure, so it can be tested.
import type { Artifact, Cell, RunInfo, Table, ToolResult } from "./contract";

export const MAX_TABLE_ROWS = 60;
export const DRAWINGS_PER_ROW = 2;
// Display widths (px) in the result view. Two drawing cards per row line up with
// the highlight cards above them. "Browse Drawings" shows the cards large.
export const DRAWING_WIDTH = 280;
export const HIGHLIGHTS_WIDTH = 2 * DRAWING_WIDTH + 4;

export interface RenderedResult {
  markdown: string;
  metadata: { label: string; value: string }[]; // shown in the side panel
  viewer?: string; // path of the HTML 3D viewer, opened in the browser
  drawings: Artifact[]; // SVG/PNG, for "Browse Drawings"
  files: Artifact[]; // other files (SDF, XYZ, JSON, ...) for "Show in Finder"
}

function cellText(value: Cell): string {
  if (value === null || value === undefined) return "";
  return String(value).replace(/\|/g, "\\|").replace(/\r?\n/g, " ");
}

export function tableMarkdown(table: Table): string {
  const lines: string[] = [];
  if (table.title) lines.push(`### ${table.title}`, "");
  const columns = table.columns.map((c) => cellText(c) || " ");
  lines.push(`| ${columns.join(" | ")} |`, `| ${columns.map(() => "---").join(" | ")} |`);
  for (const row of table.rows.slice(0, MAX_TABLE_ROWS)) {
    lines.push(`| ${row.map(cellText).join(" | ")} |`);
  }
  if (table.rows.length > MAX_TABLE_ROWS) {
    lines.push("", `_${table.rows.length - MAX_TABLE_ROWS} more rows: run \`csk ui\` to see the whole table._`);
  }
  return lines.join("\n");
}

// Clickable grids (e.g. the periodic table) have many narrow columns that a
// markdown table squeezes until symbols break ("H" over "g"). Show them as a
// fixed-width text grid instead.
export function gridMarkdown(table: Table): string {
  const rows = [table.columns, ...table.rows].map((row) => row.map((c) => (c === null ? "" : String(c))));
  const width = Math.max(2, ...rows.flat().map((c) => c.length));
  const out: string[] = [];
  if (table.title) out.push(`### ${table.title}`, "");
  out.push(
    "```",
    ...rows.map((row) =>
      row
        .map((c) => c.padEnd(width))
        .join(" ")
        .trimEnd(),
    ),
    "```",
  );
  return out.join("\n");
}

export function isGrid(table: Table): boolean {
  return Object.keys(table.cells).length > 0;
}

const IMAGE_KINDS = new Set(["svg", "png"]);

// Images made by the extension for this view (lib/cards.ts), all optional.
export interface ViewImages {
  cards?: Record<string, string>; // drawing path -> card image (2D card SVG or 3D GIF), caption inside
  highlights?: string; // highlight cards image; replaces the highlights in the side panel
  spins?: string[]; // rotating 3D cards for results without drawings (xyz)
}

function image(alt: string, path: string, width: number): string {
  // Paths are unique per run (Raycast caches images by path).
  return `![${cellText(alt) || "image"}](${encodeURI(path)}?raycast-width=${width})`;
}

function drawingRows(drawings: Artifact[], cards: Record<string, string>): string[] {
  const md: string[] = [];
  for (let i = 0; i < drawings.length; i += DRAWINGS_PER_ROW) {
    const row = drawings.slice(i, i + DRAWINGS_PER_ROW);
    // Images on one line sit side by side.
    md.push(row.map((a) => image(a.title, cards[a.path] ?? a.path, DRAWING_WIDTH)).join(" "), "");
    // Without a card, the caption goes below, one per line (a separate paragraph
    // each: a plain line break would be joined).
    for (const a of row.filter((d) => !cards[d.path])) {
      const caption = [a.title && `**${a.title}**`, a.note].filter(Boolean).join(" ");
      if (caption) md.push(caption, "");
    }
  }
  return md;
}

export function renderResult(result: ToolResult, run?: RunInfo, images: ViewImages = {}): RenderedResult {
  const md: string[] = [];
  for (const w of result.warnings) md.push(`> ⚠️ ${w}`, "");
  md.push(`# ${result.answer}`, "");
  if (images.highlights) md.push(image("key values", images.highlights, HIGHLIGHTS_WIDTH), "");
  for (const spin of images.spins ?? []) md.push(image("rotating 3D view", spin, DRAWING_WIDTH), "");

  // The result itself: drawings, then tables
  const drawings = result.artifacts.filter((a) => IMAGE_KINDS.has(a.kind));
  md.push(...drawingRows(drawings, images.cards ?? {}));
  for (const t of result.tables) md.push(isGrid(t) ? gridMarkdown(t) : tableMarkdown(t), "");

  // Evidence
  for (const f of result.formulas) md.push(`$$${f.latex}$$`, "");
  if (result.constants.length) {
    md.push("### Constants", "", "| Name | Symbol | Value | Unit | Source |", "| --- | --- | --- | --- | --- |");
    for (const c of result.constants) {
      md.push(`| ${[c.name, c.symbol, c.value, c.unit, c.source].map((v) => cellText(v)).join(" | ")} |`);
    }
    md.push("");
  }
  if (result.assumptions.length) {
    md.push("### Assumptions", "", ...result.assumptions.map((a) => `- ${a}`), "");
  }

  // Small print
  if (result.notes.length) md.push("---", "", ...result.notes.map((n) => `_${n}_`), "");
  if (result.sources.length) md.push("### References", "", ...result.sources.map((s) => `- ${s}`), "");

  const metadata = images.highlights
    ? []
    : result.highlights.map((h) => ({ label: h.label, value: h.note ? `${h.value}  (${h.note})` : h.value }));
  if (run) {
    metadata.push({ label: "Tool", value: `${run.tool_id} · ${run.tool}` });
    metadata.push({ label: "Time", value: `${run.elapsed_s.toFixed(2)} s` });
    metadata.push({ label: "Result", value: run.number === null ? "not kept" : `#${run.number}` });
  }

  return {
    markdown: md.join("\n").trimEnd() + "\n",
    metadata,
    viewer: result.artifacts.find((a) => a.kind === "html")?.path,
    drawings,
    files: result.artifacts.filter((a) => !IMAGE_KINDS.has(a.kind) && a.kind !== "html"),
  };
}
