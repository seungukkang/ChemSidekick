// ToolResult -> what the Detail view shows, in the same order as the CLI and
// Streamlit: answer -> evidence (formulas, constants, assumptions) -> details
// (drawings, tables, files) -> notes and sources. Pure, so it can be tested.
import type { Artifact, Cell, RunInfo, Table, ToolResult } from "./contract";

export const MAX_TABLE_ROWS = 60;

export interface RenderedResult {
  markdown: string;
  metadata: { label: string; value: string }[]; // shown in the side panel
  viewer?: string; // path of the HTML 3D viewer, opened in the browser
  files: Artifact[]; // other files (SDF, XYZ, JSON, ...) for "Show in Finder"
}

function cellText(value: Cell): string {
  if (value === null || value === undefined) return "";
  return String(value).replace(/\|/g, "\\|").replace(/\r?\n/g, " ");
}

export function tableMarkdown(table: Table): string {
  const lines: string[] = [];
  if (table.title) lines.push(`### ${table.title}`, "");
  // Clickable grids (e.g. the periodic table) show the cell text only.
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

const IMAGE_KINDS = new Set(["svg", "png"]);

export function renderResult(result: ToolResult, run?: RunInfo): RenderedResult {
  const md: string[] = [];
  for (const w of result.warnings) md.push(`> ⚠️ ${w}`, "");
  md.push(`# ${result.answer}`, "");

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

  // Details: drawings, then tables
  const images = result.artifacts.filter((a) => IMAGE_KINDS.has(a.kind));
  for (const a of images) {
    // Paths are unique per run (Raycast caches images by path).
    md.push(`![${cellText(a.title) || "drawing"}](${encodeURI(a.path)})`, "");
    const caption = [a.title && `**${a.title}**`, a.note].filter(Boolean).join(" · ");
    if (caption) md.push(caption, "");
  }
  for (const t of result.tables) md.push(tableMarkdown(t), "");

  // Small print
  if (result.notes.length) md.push("---", "", ...result.notes.map((n) => `_${n}_`), "");
  if (result.sources.length) md.push("### References", "", ...result.sources.map((s) => `- ${s}`), "");

  const metadata = result.highlights.map((h) => ({
    label: h.label,
    value: h.note ? `${h.value}  (${h.note})` : h.value,
  }));
  if (run) {
    metadata.push({ label: "Tool", value: `${run.tool_id} · ${run.tool}` });
    metadata.push({ label: "Time", value: `${run.elapsed_s.toFixed(2)} s` });
    metadata.push({ label: "Result", value: run.number === null ? "not kept" : `#${run.number}` });
  }

  return {
    markdown: md.join("\n").trimEnd() + "\n",
    metadata,
    viewer: result.artifacts.find((a) => a.kind === "html")?.path,
    files: result.artifacts.filter((a) => !IMAGE_KINDS.has(a.kind) && a.kind !== "html"),
  };
}
