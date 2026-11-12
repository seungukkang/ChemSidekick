// Element: every element in a searchable list (symbol, name, or atomic number),
// with its key values beside the list, the full card on Enter, and the periodic
// table on cmd-T. It is the element tool's periodic table shown as a list
// (PickList), cached between launches so it opens instantly.
import { type LaunchProps, List } from "@raycast/api";
import { useCachedPromise } from "@raycast/utils";
import { ErrorView } from "./components/ErrorView";
import { PickList } from "./components/PickList";
import { getTransport } from "./connection";
import type { Table, ToolInfo } from "./lib/contract";
import { clickableTable } from "./lib/pick";

// The element tool (REF-01), as `csk list --json` describes it; enough for the views.
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

async function loadTable(): Promise<Table> {
  const response = await getTransport().run("element", {}, { record: false });
  if (!response.ok) throw response.error; // ErrorInfo: shown by ErrorView
  const table = clickableTable(response.result);
  if (!table) throw new Error("csk element returned no periodic table.");
  return table;
}

export default function Command(props: LaunchProps<{ arguments: { query?: string } }>) {
  const { data: table, isLoading, error, revalidate } = useCachedPromise(loadTable, [], { keepPreviousData: true });
  if (error && !table) return <ErrorView error={error} onRetry={revalidate} />;
  // First launch only: afterwards the list is cached.
  if (!table) return <List isLoading searchBarPlaceholder="Loading the elements…" />;
  return (
    <PickList tool={ELEMENT_TOOL} table={table} initialSearch={props.arguments.query ?? ""} isLoading={isLoading} />
  );
}
