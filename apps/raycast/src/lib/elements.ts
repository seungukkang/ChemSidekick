// The element tool's periodic-table result -> a searchable element list and a
// periodic table drawing. The drawing is a figure, not a layout trick: a
// transparent background and colors for Raycast's light or dark appearance, so
// it sits on the page like native content. Pure, so it can be tested.
import type { Table } from "./contract";

export type Appearance = "light" | "dark";

// Block colors, the same as the web UI (src/chemsidekick/ui/render.py TAG_COLORS,
// in the order of Table.tags: s, p, d, f).
const TAG_COLORS = ["#f43f5e", "#f59e0b", "#3b82f6", "#10b981", "#8b5cf6", "#f97316"];

export interface ElementEntry {
  symbol: string;
  z: number;
  name: string;
  block: string; // "s", "p", "d", "f"
  weight: string; // as shown on the tile, e.g. "55.845" or "[98]"
  period: number;
  group: number | null; // null for the f-block rows (Ln, An)
}

export function blockColors(table: Table): Record<string, string> {
  return Object.fromEntries(Object.keys(table.tags).map((tag, i) => [tag, TAG_COLORS[i % TAG_COLORS.length]]));
}

const F_ROW_PERIOD: Record<string, number> = { Ln: 6, An: 7 };

export function elementsFromTable(table: Table): ElementEntry[] {
  const out: ElementEntry[] = [];
  table.rows.forEach((row) => {
    const label = String(row[0] ?? "");
    const period = Number(label) || F_ROW_PERIOD[label] || 0;
    row.forEach((cell, col) => {
      const symbol = typeof cell === "string" ? cell : "";
      const info = table.cells[symbol];
      if (col === 0 || !info) return;
      out.push({
        symbol,
        z: Number(info.top),
        name: info.lines[0] ?? "",
        weight: info.lines[1] ?? "",
        block: info.tag,
        period,
        group: F_ROW_PERIOD[label] ? null : col,
      });
    });
  });
  return out.sort((a, b) => a.z - b.z);
}

// --- Drawing -------------------------------------------------------------------

const PITCH = 34; // px per tile, including the gap
const TILE = 31;
const SECTION_GAP = 6; // extra space before a new block (Table.column_gaps)
const LABEL_W = 22; // period labels on the left
const HEADER_H = 18; // group numbers on top
const F_GAP = 12; // space above the f-block rows
const LEGEND_H = 26;

const THEME: Record<Appearance, { text: string; muted: string; fill: number; selected: string }> = {
  light: { text: "#111827", muted: "#6b7280", fill: 0.1, selected: "#111827" },
  dark: { text: "#f3f4f6", muted: "#9ca3af", fill: 0.18, selected: "#ffffff" },
};

function esc(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function periodicTableSize(table: Table): { width: number; height: number } {
  const columns = table.columns.length - 1;
  const mainRows = table.rows.filter((r) => /^\d+$/.test(String(r[0] ?? ""))).length;
  const fRows = table.rows.filter((r) => F_ROW_PERIOD[String(r[0] ?? "")]).length;
  return {
    width: LABEL_W + columns * PITCH + table.column_gaps.length * SECTION_GAP,
    height: HEADER_H + mainRows * PITCH + (fRows ? F_GAP + fRows * PITCH : 0) + LEGEND_H,
  };
}

// Tiles show only the atomic number and the symbol (003 §10: compact views use
// CellInfo.top and the symbol, not the name and weight lines).
export function periodicTableSvg(table: Table, appearance: Appearance, selected?: string): string {
  const theme = THEME[appearance];
  const colors = blockColors(table);
  const { width, height } = periodicTableSize(table);
  const gapsBefore = (col: number, fRow: boolean) =>
    table.column_gaps.filter((g) => col >= g && !(fRow && g > 3)).length * SECTION_GAP;
  const x = (col: number, fRow: boolean) => LABEL_W + (col - 1) * PITCH + gapsBefore(col, fRow);

  const parts = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`,
  ];
  const font = 'font-family="Helvetica, Arial, sans-serif"';
  // Group numbers
  for (let col = 1; col < table.columns.length; col++) {
    parts.push(
      `<text x="${x(col, false) + TILE / 2}" y="${HEADER_H - 6}" text-anchor="middle" ${font} font-size="9" fill="${theme.muted}">${esc(table.columns[col])}</text>`,
    );
  }
  let y = HEADER_H;
  let fStarted = false;
  for (const row of table.rows) {
    const label = String(row[0] ?? "");
    const fRow = Boolean(F_ROW_PERIOD[label]);
    if (!label) continue; // the spacer row
    if (fRow && !fStarted) {
      y += F_GAP;
      fStarted = true;
    }
    parts.push(
      `<text x="${LABEL_W - 7}" y="${y + TILE / 2 + 3}" text-anchor="end" ${font} font-size="9" fill="${theme.muted}">${esc(label)}</text>`,
    );
    row.forEach((cell, col) => {
      const symbol = typeof cell === "string" ? cell : "";
      const info = table.cells[symbol];
      if (col === 0 || !info) return;
      const color = colors[info.tag] ?? theme.muted;
      const tx = x(col, fRow);
      const isSelected = symbol === selected;
      parts.push(
        `<rect x="${tx + 0.75}" y="${y + 0.75}" width="${TILE - 1.5}" height="${TILE - 1.5}" rx="4" ry="4" fill="${color}" fill-opacity="${theme.fill}" stroke="${isSelected ? theme.selected : color}" stroke-width="${isSelected ? 2.5 : 1.5}"/>`,
        `<text x="${tx + 3}" y="${y + 9}" ${font} font-size="7" fill="${theme.muted}">${esc(info.top)}</text>`,
        `<text x="${tx + TILE / 2}" y="${y + 24}" text-anchor="middle" ${font} font-weight="700" font-size="12" fill="${theme.text}">${esc(symbol)}</text>`,
      );
    });
    y += PITCH;
  }
  // Legend: block colors
  let lx = LABEL_W;
  const ly = height - 9;
  for (const [tag, meaning] of Object.entries(table.tags)) {
    parts.push(
      `<rect x="${lx}" y="${ly - 9}" width="10" height="10" rx="2" ry="2" fill="${colors[tag]}" fill-opacity="${theme.fill}" stroke="${colors[tag]}" stroke-width="1.5"/>`,
      `<text x="${lx + 15}" y="${ly}" ${font} font-size="10" fill="${theme.muted}">${esc(meaning)}</text>`,
    );
    lx += 15 + meaning.length * 6 + 16;
  }
  parts.push("</svg>");
  return parts.join("\n");
}
