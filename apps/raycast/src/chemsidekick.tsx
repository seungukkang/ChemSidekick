// The generic command: every registered tool, from `csk list --json`. New tools
// appear here without changing the extension: the form is generated from the
// tool's input schema and the result view is shared by all tools.
import { Action, ActionPanel, Icon, List } from "@raycast/api";
import { usePromise } from "@raycast/utils";
import { ErrorView } from "./components/ErrorView";
import { ResultView } from "./components/ResultView";
import { ToolForm } from "./components/ToolForm";
import { ProfileCommand } from "./components/ProfileView";
import { UnitsView } from "./components/UnitsView";
import { getTransport } from "./connection";
import type { ToolInfo, ToolListResponse } from "./lib/contract";
import { formSpec } from "./lib/form";
import type { RunOptions } from "./lib/transport";

// A start view (e.g. the periodic table) runs with default input and is not kept.
const START_VIEW: RunOptions = { record: false };
const NO_INPUT = {};

// Tools with a screen made for them: opened directly instead of the generated form.
const DEDICATED_VIEWS: Record<string, () => React.ReactNode> = {
  units: () => <UnitsView />,
  profile: () => <ProfileCommand />,
};

async function loadTools(): Promise<ToolListResponse> {
  const response = await getTransport().listTools();
  if (!response.ok) throw response.error; // ErrorInfo: shown by ErrorView
  return response;
}

function ToolItem({ tool }: { tool: ToolInfo }) {
  const unsupported = formSpec(tool.input_schema).unsupported;
  const supported = tool.available && unsupported.length === 0;
  const accessories: List.Item.Accessory[] = [{ text: tool.resources }, { tag: tool.id }];
  if (!tool.available) accessories.unshift({ icon: Icon.Warning, tooltip: tool.unavailable_reason });
  if (unsupported.length) {
    accessories.unshift({ icon: Icon.Info, tooltip: `Not in Raycast yet (input: ${unsupported.join(", ")})` });
  }
  return (
    <List.Item
      title={tool.title}
      subtitle={tool.summary}
      icon={tool.available ? Icon.Box : Icon.Warning}
      keywords={[tool.name, tool.id, ...tool.keywords]}
      accessories={accessories}
      actions={
        <ActionPanel>
          {supported && DEDICATED_VIEWS[tool.name] && (
            <Action.Push title={`Open ${tool.title}`} icon={Icon.ArrowRight} target={DEDICATED_VIEWS[tool.name]()} />
          )}
          {supported && !DEDICATED_VIEWS[tool.name] && tool.start_view && (
            <Action.Push
              title={`Show ${tool.start_view}`}
              icon={Icon.Eye}
              target={<ResultView tool={tool} input={NO_INPUT} options={START_VIEW} />}
            />
          )}
          {supported && !DEDICATED_VIEWS[tool.name] && (
            <Action.Push title="Open Form" icon={Icon.Pencil} target={<ToolForm tool={tool} />} />
          )}
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
