// The generic command: every registered tool, from `csk list --json`.
// M2: list and error screens. M3 adds the generated input form and result view.
import { Action, ActionPanel, Icon, List } from "@raycast/api";
import { usePromise } from "@raycast/utils";
import { ErrorView } from "./components/ErrorView";
import { getTransport } from "./connection";
import type { ToolInfo, ToolListResponse } from "./lib/contract";

async function loadTools(): Promise<ToolListResponse> {
  const response = await getTransport().listTools();
  if (!response.ok) throw response.error; // ErrorInfo: shown by ErrorView
  return response;
}

function ToolItem({ tool }: { tool: ToolInfo }) {
  const accessories: List.Item.Accessory[] = [{ text: tool.resources }, { tag: tool.id }];
  if (!tool.available) accessories.unshift({ icon: Icon.Warning, tooltip: tool.unavailable_reason });
  return (
    <List.Item
      title={tool.title}
      subtitle={tool.summary}
      icon={tool.available ? Icon.Box : Icon.Warning}
      keywords={[tool.name, tool.id, ...tool.keywords]}
      accessories={accessories}
      actions={
        <ActionPanel>
          <Action.CopyToClipboard title="Copy Csk Command" content={`csk ${tool.name}`} />
        </ActionPanel>
      }
    />
  );
}

export default function Command() {
  const { data, isLoading, error, revalidate } = usePromise(loadTools, [], {
    failureToastOptions: { title: "ChemSidekick" },
  });
  if (error) return <ErrorView error={error} onRetry={revalidate} />;
  return (
    <List isLoading={isLoading} navigationTitle={data ? `ChemSidekick · csk ${data.csk_version}` : "ChemSidekick"}>
      {data?.categories.map((category) => {
        const tools = data.tools.filter((t) => t.category === category.name);
        if (!tools.length) return null;
        return (
          <List.Section key={category.name} title={category.title}>
            {tools.map((tool) => (
              <ToolItem key={tool.id} tool={tool} />
            ))}
          </List.Section>
        );
      })}
    </List>
  );
}
