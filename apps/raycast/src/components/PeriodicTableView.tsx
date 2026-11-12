import { Action, ActionPanel, Detail, environment } from "@raycast/api";
import { useMemo } from "react";
import type { Table } from "../lib/contract";
import { periodicTableSize, periodicTableSvg } from "../lib/elements";
import { writeImage } from "../lib/images";

// The periodic table as a figure: tiles with the atomic number and the symbol,
// block colors, drawn for Raycast's light or dark appearance. `selected` is
// outlined. Raycast cannot click inside an image: elements are picked in the list.
export function periodicTableMarkdown(table: Table, selected?: string): string {
  const path = writeImage(periodicTableSvg(table, environment.appearance, selected), "periodic-table");
  const { width } = periodicTableSize(table);
  return `![Periodic table](${encodeURI(path)}?raycast-width=${width})`;
}

export function PeriodicTableView({
  table,
  selected,
  title = "Periodic Table",
}: {
  table: Table;
  selected?: string;
  title?: string;
}) {
  const markdown = useMemo(() => periodicTableMarkdown(table, selected), [table, selected]);
  return (
    <Detail
      navigationTitle={title}
      markdown={`${markdown}\n\n_Press Esc to go back to the list and pick another one._`}
      actions={
        <ActionPanel>{selected && <Action.CopyToClipboard title="Copy Symbol" content={selected} />}</ActionPanel>
      }
    />
  );
}
