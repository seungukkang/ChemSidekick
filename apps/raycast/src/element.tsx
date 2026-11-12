// Element: every element in a searchable list (symbol, name, or atomic number),
// with its key values beside the list, the full card on Enter, and the periodic
// table on cmd-T. The list comes from one `csk element` run (the periodic table),
// cached between launches so it opens instantly.
import { Action, ActionPanel, Color, Icon, type LaunchProps, List } from "@raycast/api";
import { useCachedPromise } from "@raycast/utils";
import { useMemo, useState } from "react";
import { ErrorView } from "./components/ErrorView";
import { PeriodicTableView } from "./components/PeriodicTableView";
import { ResultView } from "./components/ResultView";
import { getTransport } from "./connection";
import type { RunResponse, Table, ToolInfo } from "./lib/contract";
import { blockColors, type ElementEntry, elementsFromTable } from "./lib/elements";

// The element tool (REF-01), as `csk list --json` describes it; enough for ResultView.
const ELEMENT_TOOL: ToolInfo = {
  id: "REF-01",
  name: "element",
  title: "Element",
  summary: "Element properties, electron configuration, isotopes; or the periodic table",
  category: "reference",
  keywords: [],
  resources: "light",
  requires: [],
  available: true,
  unavailable_reason: "",
  icon: "",
  start_view: "Periodic table",
  input_schema: {},
};

async function runElement(input: Record<string, unknown>): Promise<RunResponse> {
  const response = await getTransport().run("element", input, { record: false });
  if (!response.ok) throw response.error; // ErrorInfo: shown by ErrorView
  return response;
}

async function loadTable(): Promise<Table> {
  const table = (await runElement({})).result.tables[0];
  if (!table) throw new Error("csk element returned no periodic table.");
  return table;
}

async function loadCard(symbol: string): Promise<RunResponse> {
  return runElement({ query: symbol });
}

function Preview({ entry, selected }: { entry: ElementEntry; selected: boolean }) {
  const { data, isLoading } = useCachedPromise(loadCard, [entry.symbol], { execute: selected });
  const highlights = data?.result.highlights ?? [];
  return (
    <List.Item.Detail
      isLoading={isLoading}
      markdown={`# ${entry.symbol} · ${entry.name}`}
      metadata={
        <List.Item.Detail.Metadata>
          <List.Item.Detail.Metadata.Label title="Atomic number" text={String(entry.z)} />
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

function CopyValue({ symbol, label, title }: { symbol: string; label: string; title: string }) {
  const { data } = useCachedPromise(loadCard, [symbol], { execute: false });
  const value = data?.result.highlights.find((h) => h.label === label)?.value;
  return value ? <Action.CopyToClipboard title={title} content={value} /> : null;
}

export default function Command(props: LaunchProps<{ arguments: { query?: string } }>) {
  const { data: table, isLoading, error, revalidate } = useCachedPromise(loadTable, [], { keepPreviousData: true });
  const [searchText, setSearchText] = useState(props.arguments.query ?? "");
  const [selected, setSelected] = useState<string | null>(null);
  const elements = useMemo(() => (table ? elementsFromTable(table) : []), [table]);
  const colors = useMemo(() => (table ? blockColors(table) : {}), [table]);

  if (error && !table) return <ErrorView error={error} onRetry={revalidate} />;
  return (
    <List
      isLoading={isLoading}
      isShowingDetail
      filtering
      searchText={searchText}
      onSearchTextChange={setSearchText}
      onSelectionChange={setSelected}
      searchBarPlaceholder="Symbol, name, or atomic number (Fe, iron, 26)"
    >
      {elements.map((e) => (
        <List.Item
          key={e.symbol}
          id={e.symbol}
          title={e.symbol}
          subtitle={e.name}
          keywords={[e.name, String(e.z)]}
          icon={{ source: Icon.CircleFilled, tintColor: colors[e.block] ?? Color.SecondaryText }}
          accessories={[{ text: String(e.z) }]}
          detail={<Preview entry={e} selected={selected === e.symbol} />}
          actions={
            <ActionPanel>
              <Action.Push
                title="Open Card"
                icon={Icon.Document}
                target={<ResultView tool={ELEMENT_TOOL} input={{ query: e.symbol }} />}
              />
              {table && (
                <Action.Push
                  title="Show Periodic Table"
                  icon={Icon.AppWindowGrid3x3}
                  shortcut={{ modifiers: ["cmd"], key: "t" }}
                  target={<PeriodicTableView table={table} selected={e.symbol} />}
                />
              )}
              <Action.CopyToClipboard title="Copy Symbol" content={e.symbol} />
              <CopyValue symbol={e.symbol} label="Standard atomic weight" title="Copy Atomic Weight" />
              <CopyValue symbol={e.symbol} label="Electron configuration" title="Copy Electron Configuration" />
            </ActionPanel>
          }
        />
      ))}
    </List>
  );
}
