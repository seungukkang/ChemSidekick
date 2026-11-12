import { Action, ActionPanel, Color, Icon, List } from "@raycast/api";
import { useCachedPromise } from "@raycast/utils";
import { useMemo, useState } from "react";
import { getTransport } from "../connection";
import type { RunResponse, Table, ToolInfo } from "../lib/contract";
import { blockColors } from "../lib/elements";
import { type PickItem, pickItems } from "../lib/pick";
import { PeriodicTableView } from "./PeriodicTableView";
import { ResultView } from "./ResultView";

// A clickable table (e.g. the periodic table) as a searchable list: search by
// the cell text, its small number, or its name (Fe, 26, iron). The selected
// item's key values show beside the list; Enter runs the tool with it (e.g. the
// element card); cmd-T shows the table as a figure with the item outlined.

async function preview(tool: string, field: string, value: string): Promise<RunResponse> {
  const response = await getTransport().run(tool, { [field]: value }, { record: false });
  if (!response.ok) throw new Error(response.error.message);
  return response;
}

function Preview({ tool, field, item, selected }: { tool: string; field: string; item: PickItem; selected: boolean }) {
  const { data, isLoading, error } = useCachedPromise(preview, [tool, field, item.value], { execute: selected });
  const highlights = data?.result.highlights ?? [];
  const heading = [item.value, item.name].filter(Boolean).join(" · ");
  return (
    <List.Item.Detail
      isLoading={isLoading}
      markdown={error ? `# ${heading}\n\n${error.message}` : `# ${heading}`}
      metadata={
        <List.Item.Detail.Metadata>
          {item.top && <List.Item.Detail.Metadata.Label title="Number" text={item.top} />}
          {highlights.map((h) => (
            <List.Item.Detail.Metadata.Label key={h.label} title={h.label} text={h.value} />
          ))}
          {highlights.some((h) => h.note) && <List.Item.Detail.Metadata.Separator />}
          {highlights
            .filter((h) => h.note)
            .map((h) => (
              <List.Item.Detail.Metadata.Label key={`${h.label}-note`} title={`${h.label}: check`} text={h.note} />
            ))}
        </List.Item.Detail.Metadata>
      }
    />
  );
}

function CopyHighlights({ tool, field, value }: { tool: string; field: string; value: string }) {
  const { data } = useCachedPromise(preview, [tool, field, value], { execute: false });
  return (
    <>
      {(data?.result.highlights ?? []).slice(0, 3).map((h) => (
        <Action.CopyToClipboard key={h.label} title={`Copy ${h.label}`} content={h.value} />
      ))}
    </>
  );
}

export function PickList({
  tool,
  table,
  initialSearch = "",
  isLoading = false,
}: {
  tool: ToolInfo;
  table: Table;
  initialSearch?: string;
  isLoading?: boolean;
}) {
  const field = table.action_field ?? "";
  const items = useMemo(() => pickItems(table), [table]);
  const colors = useMemo(() => blockColors(table), [table]);
  const [searchText, setSearchText] = useState(initialSearch);
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <List
      navigationTitle={tool.title}
      isLoading={isLoading}
      isShowingDetail
      filtering
      searchText={searchText}
      onSearchTextChange={setSearchText}
      onSelectionChange={setSelected}
      searchBarPlaceholder={`Search ${table.title || tool.start_view || tool.title} (e.g. Fe, iron, 26)`}
    >
      {items.map((item) => (
        <List.Item
          key={item.value}
          id={item.value}
          title={item.value}
          subtitle={item.name}
          keywords={[item.name, item.top].filter(Boolean)}
          icon={{ source: Icon.CircleFilled, tintColor: colors[item.tag] ?? Color.SecondaryText }}
          accessories={item.top ? [{ text: item.top }] : []}
          detail={<Preview tool={tool.name} field={field} item={item} selected={selected === item.value} />}
          actions={
            <ActionPanel>
              <Action.Push
                title="Open"
                icon={Icon.Document}
                target={<ResultView tool={tool} input={{ [field]: item.value }} />}
              />
              <Action.Push
                title={`Show ${tool.start_view || "Table"}`}
                icon={Icon.AppWindowGrid3x3}
                shortcut={{ modifiers: ["cmd"], key: "t" }}
                target={<PeriodicTableView table={table} selected={item.value} title={tool.start_view || tool.title} />}
              />
              <Action.CopyToClipboard title={`Copy ${item.value}`} content={item.value} />
              <CopyHighlights tool={tool.name} field={field} value={item.value} />
            </ActionPanel>
          }
        />
      ))}
    </List>
  );
}
