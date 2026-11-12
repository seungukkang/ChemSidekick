import { Action, ActionPanel, Detail, Icon, Keyboard, open, showToast, Toast } from "@raycast/api";
import { usePromise } from "@raycast/utils";
import { dirname } from "node:path";
import { getTransport } from "../connection";
import type { RunResponse, ToolInfo } from "../lib/contract";
import { renderResult } from "../lib/render";
import type { RunOptions } from "../lib/transport";
import { DrawingsGrid } from "./DrawingsGrid";
import { ErrorView } from "./ErrorView";

const NO_OPTIONS: RunOptions = {};

async function runTool(tool: string, input: Record<string, unknown>, options: RunOptions): Promise<RunResponse> {
  const response = await getTransport().run(tool, input, options);
  if (!response.ok) throw response.error; // ErrorInfo: shown by ErrorView
  return response;
}

async function save(number: number) {
  const toast = await showToast({ style: Toast.Style.Animated, title: "Saving…" });
  try {
    const response = await getTransport().save(number);
    if (!response.ok) throw new Error(response.error.message);
    toast.style = Toast.Style.Success;
    toast.title = "Saved";
    toast.message = response.saved_to;
    toast.primaryAction = { title: "Show in Finder", onAction: () => open(response.saved_to) };
  } catch (e) {
    toast.style = Toast.Style.Failure;
    toast.title = "Could not save";
    toast.message = e instanceof Error ? e.message : String(e);
  }
}

// Runs one tool and shows its result. Used by every tool (generic view).
export function ResultView({
  tool,
  input,
  options = NO_OPTIONS,
}: {
  tool: ToolInfo;
  input: Record<string, unknown>;
  options?: RunOptions;
}) {
  const { data, isLoading, error, revalidate } = usePromise(runTool, [tool.name, input, options], {
    failureToastOptions: { title: tool.title },
  });
  if (error) return <ErrorView error={error} onRetry={revalidate} />;
  if (!data) return <Detail isLoading={isLoading} navigationTitle={tool.title} markdown={`Running ${tool.title}…`} />;

  const view = renderResult(data.result, data.run);
  return (
    <Detail
      navigationTitle={tool.title}
      markdown={view.markdown}
      metadata={
        view.metadata.length ? (
          <Detail.Metadata>
            {view.metadata.map((m) => (
              <Detail.Metadata.Label key={m.label} title={m.label} text={m.value} />
            ))}
          </Detail.Metadata>
        ) : undefined
      }
      actions={
        <ActionPanel>
          {view.viewer && (
            <Action
              title="Open 3D Viewer"
              icon={Icon.Globe}
              shortcut={Keyboard.Shortcut.Common.Open}
              onAction={() => open(view.viewer!)}
            />
          )}
          {view.drawings.length > 0 && (
            <Action.Push
              title="Browse Drawings"
              icon={Icon.Image}
              shortcut={{ modifiers: ["cmd"], key: "d" }}
              target={<DrawingsGrid title={`${tool.title} · drawings`} drawings={view.drawings} />}
            />
          )}
          <Action.CopyToClipboard title="Copy Answer" content={data.result.answer} />
          {data.run.number !== null && (
            <Action
              title="Save Result"
              icon={Icon.SaveDocument}
              shortcut={Keyboard.Shortcut.Common.Save}
              onAction={() => save(data.run.number!)}
            />
          )}
          <Action.ShowInFinder
            title="Show Files in Finder"
            path={view.files[0] ? dirname(view.files[0].path) : data.run.folder}
          />
          <Action.CopyToClipboard
            title="Copy as Markdown"
            content={view.markdown}
            shortcut={{ modifiers: ["cmd", "shift"], key: "m" }}
          />
        </ActionPanel>
      }
    />
  );
}
