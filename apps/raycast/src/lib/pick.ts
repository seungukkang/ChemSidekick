// Clickable tables (Table.action_field, e.g. the periodic table): clicking a cell
// runs the same tool again with that cell's text as input. Raycast cannot click
// inside a page, so such a result is shown as a searchable list of its cells.
// Pure, so it can be tested.
import type { Table, ToolResult } from "./contract";

export interface PickItem {
  value: string; // the cell text, e.g. "Fe": the input for the tool
  top: string; // small text above it on a tile, e.g. the atomic number
  name: string; // first line under it, e.g. "Iron"
  extra: string; // second line, e.g. the atomic weight
  tag: string; // group for coloring, e.g. the block "d"
}

export function clickableTable(result: ToolResult): Table | undefined {
  return result.tables.find((t) => t.action_field && t.action_columns.length > 0);
}

export function pickItems(table: Table): PickItem[] {
  const seen = new Set<string>();
  const items: PickItem[] = [];
  for (const row of table.rows) {
    for (const col of table.action_columns) {
      const value = row[col];
      if (typeof value !== "string" || !value || seen.has(value)) continue;
      seen.add(value);
      const info = table.cells[value];
      items.push({
        value,
        top: info?.top ?? "",
        name: info?.lines[0] ?? "",
        extra: info?.lines[1] ?? "",
        tag: info?.tag ?? "",
      });
    }
  }
  // Numbered cells (atomic numbers) are listed in order of their number.
  if (items.length && items.every((i) => /^\d+$/.test(i.top))) items.sort((a, b) => Number(a.top) - Number(b.top));
  return items;
}
