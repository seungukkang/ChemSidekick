import { Action, ActionPanel, Detail, Grid, Icon, Keyboard, open, showToast, Toast } from "@raycast/api";
import { usePromise } from "@raycast/utils";
import { dirname } from "node:path";
import { useEffect, useMemo } from "react";
import { getTransport } from "../connection";
import type { Artifact, RunResponse, ToolInfo } from "../lib/contract";
import { isGrid, renderResult } from "../lib/render";
import { clickableTable } from "../lib/pick";
import { drawingsOf, type SpinTarget, spinTargets } from "../lib/spin";
import type { RunOptions } from "../lib/transport";
import { ErrorView } from "./ErrorView";
import { ToolForm } from "./ToolForm";
import { periodicTableMarkdown } from "./PeriodicTableView";
import { PickList } from "./PickList";
import { combinedKey, ensureCombined, toggle3D, useSpinState } from "./spin-store";

const NO_OPTIONS: RunOptions = {};
const SHOW_DETAILS: Keyboard.Shortcut = { modifiers: ["cmd"], key: "i" };
const SWITCH_3D: Keyboard.Shortcut = { modifiers: ["cmd"], key: "t" };

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

// Runs one tool and shows its result. Used by every tool (generic view): a
// clickable table (periodic table) as a searchable list, several drawings
// (stereoisomers) as a grid of cards, anything else as a page.
export function ResultView({
  tool,
  input,
  options = NO_OPTIONS,
  autoOpenViewer = false,
}: {
  tool: ToolInfo;
  input: Record<string, unknown>;
  options?: RunOptions;
  autoOpenViewer?: boolean; // open the HTML 3D viewer in the browser when the result arrives
}) {
  const { data, isLoading, error, revalidate } = usePromise(runTool, [tool.name, input, options], {
    failureToastOptions: { title: tool.title },
  });
  useEffect(() => {
    const viewer = data?.result.artifacts.find((a) => a.kind === "html")?.path;
    if (autoOpenViewer && viewer) open(viewer);
  }, [data, autoOpenViewer]);
  if (error) return <ErrorView error={error} onRetry={revalidate} />;
  if (!data) return <Detail isLoading={isLoading} navigationTitle={tool.title} markdown={`Running ${tool.title}…`} />;
  const pick = clickableTable(data.result);
  if (pick && Object.keys(pick.cells).length) return <PickList tool={tool} table={pick} />;
  if (drawingsOf(data.result).length > 1) return <DrawingsResult tool={tool} data={data} input={input} />;
  return <ResultDetail tool={tool} data={data} input={input} />;
}

// Actions every view of a result offers.
function CommonActions({
  tool,
  data,
  input,
  markdown,
}: {
  tool: ToolInfo;
  data: RunResponse;
  input: Record<string, unknown>;
  markdown: string;
}) {
  const viewer = data.result.artifacts.find((a) => a.kind === "html")?.path;
  const files = data.result.artifacts.filter((a) => !["svg", "png", "html"].includes(a.kind));
  return (
    <>
      {viewer && (
        <Action
          title="Open 3D Viewer"
          icon={Icon.Globe}
          shortcut={Keyboard.Shortcut.Common.Open}
          onAction={() => open(viewer)}
        />
      )}
      {Object.keys(tool.input_schema).length > 0 && (
        <Action.Push
          title="Change Input"
          icon={Icon.Pencil}
          shortcut={Keyboard.Shortcut.Common.Edit}
          target={<ToolForm tool={tool} input={input} />}
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
      <Action.ShowInFinder title="Show Files in Finder" path={files[0] ? dirname(files[0].path) : data.run.folder} />
      <Action.CopyToClipboard
        title="Copy as Markdown"
        content={markdown}
        shortcut={{ modifiers: ["cmd", "shift"], key: "m" }}
      />
    </>
  );
}

function Switch3D({ target, is3D }: { target: SpinTarget; is3D: boolean }) {
  return (
    <Action
      title={is3D ? "Show 2D Drawing" : "Show Rotating 3D"}
      icon={is3D ? Icon.Image : Icon.RotateClockwise}
      shortcut={SWITCH_3D}
      onAction={() => toggle3D(target)}
    />
  );
}

// The whole result as a page: answer, key values, drawings, tables, evidence, references.
export function ResultDetail({
  tool,
  data,
  input,
}: {
  tool: ToolInfo;
  data: RunResponse;
  input: Record<string, unknown>;
}) {
  const targets = useMemo(() => spinTargets(data.result), [data]);
  const spin = useSpinState();
  // One drawing of one structure (xyz): one wide card with the 2D drawing and the
  // rotating 3D view, made when the page opens.
  const pair = targets.length === 1 && targets[0].drawing ? targets[0] : undefined;
  useEffect(() => {
    if (pair) ensureCombined(pair);
  }, [pair?.key]);
  const card = pair ? spin.made(combinedKey(pair.key)) : undefined;
  const combined = pair && card ? { [pair.key]: card } : {};
  // Show the page when the card is ready, so 2D and 3D appear together (the 2D
  // drawing alone only if the card cannot be made).
  const waiting = Boolean(pair && !card && !spin.failed(combinedKey(pair.key)));
  const swaps = Object.fromEntries(
    targets.flatMap((t) => (t.drawing && spin.gif(t.key) ? [[t.key, spin.gif(t.key)!]] : [])),
  );
  const spins = targets.flatMap((t) => (!t.drawing && spin.gif(t.key) ? [spin.gif(t.key)!] : []));
  // Clickable grids (the periodic table) as a figure; a markdown table squeezes them.
  const grids = useMemo(
    () =>
      Object.fromEntries(
        data.result.tables.flatMap((t, i) => (isGrid(t) ? [[i, periodicTableMarkdown(t)]] : [])),
      ) as Record<number, string>,
    [data],
  );
  const view = renderResult(data.result, data.run, { swaps, spins, grids, combined });
  if (waiting) {
    return <Detail isLoading navigationTitle={tool.title} markdown={`# ${data.result.answer}\n\nDrawing 2D and 3D…`} />;
  }
  return (
    <Detail
      navigationTitle={tool.title}
      markdown={view.markdown}
      metadata={
        <Detail.Metadata>
          {view.metadata.map((m) => (
            <Detail.Metadata.Label key={m.label} title={m.label} text={m.value} />
          ))}
        </Detail.Metadata>
      }
      actions={
        <ActionPanel>
          {targets.length === 1 && !pair && <Switch3D target={targets[0]} is3D={spin.is3D(targets[0].key)} />}
          {targets.length > 1 && (
            <ActionPanel.Submenu title="Switch 2D / 3D" icon={Icon.RotateClockwise} shortcut={SWITCH_3D}>
              {targets.map((t) => (
                <Action
                  key={t.key}
                  title={`${spin.is3D(t.key) ? "2D" : "3D"} · ${t.title || "structure"}`}
                  onAction={() => toggle3D(t)}
                />
              ))}
            </ActionPanel.Submenu>
          )}
          <CommonActions tool={tool} data={data} input={input} markdown={view.markdown} />
        </ActionPanel>
      }
    />
  );
}

// Several drawings (e.g. stereoisomers): native cards, two per row, with the
// title and the stereodescriptors as text. Enter switches a card to its rotating
// 3D view in place; cmd-I shows the whole result (tables, references).
function DrawingsResult({ tool, data, input }: { tool: ToolInfo; data: RunResponse; input: Record<string, unknown> }) {
  const targets = useMemo(() => spinTargets(data.result), [data]);
  const spin = useSpinState();
  const markdown = renderResult(data.result, data.run).markdown;
  const { result } = data;
  const summary = [
    ...result.warnings.map((w) => `⚠️ ${w}`),
    ...result.highlights.map((h) => `${h.label}: ${h.value}`),
  ].join("  ·  ");

  const card = (d: Artifact) => {
    const target = targets.find((t) => t.key === d.path);
    const is3D = spin.is3D(d.path);
    return (
      <Grid.Item
        key={d.path}
        content={{ source: spin.gif(d.path) ?? d.path }}
        title={d.title}
        subtitle={d.note}
        keywords={[d.title, d.note]}
        accessory={is3D ? { icon: Icon.RotateClockwise, tooltip: "Rotating 3D view" } : undefined}
        actions={
          <ActionPanel>
            {target && <Switch3D target={target} is3D={is3D} />}
            <Action.Push
              title="Show Details"
              icon={Icon.Document}
              shortcut={SHOW_DETAILS}
              target={<ResultDetail tool={tool} data={data} input={input} />}
            />
            <CommonActions tool={tool} data={data} input={input} markdown={markdown} />
            <Action.Open title="Open Drawing" target={spin.gif(d.path) ?? d.path} />
          </ActionPanel>
        }
      />
    );
  };

  return (
    <Grid
      navigationTitle={tool.title}
      columns={2}
      aspectRatio="4/3"
      fit={Grid.Fit.Contain}
      inset={Grid.Inset.Small}
      searchBarPlaceholder="Filter by number, relation, or descriptor"
    >
      <Grid.Section title={result.answer} subtitle={summary}>
        {drawingsOf(result).map(card)}
      </Grid.Section>
    </Grid>
  );
}
