import { Action, ActionPanel, Detail, Grid, Icon } from "@raycast/api";
import type { SpinTarget } from "../lib/cards";
import type { Artifact } from "../lib/contract";
import { toggle3D, useSpinState } from "./spin-store";

function LargeView({ path, title }: { path: string; title: string }) {
  return (
    <Detail
      navigationTitle={title || "Drawing"}
      markdown={`![${title}](${encodeURI(path)})`}
      actions={
        <ActionPanel>
          <Action.Open title="Open in Default App" target={path} />
          <Action.ShowInFinder path={path} />
        </ActionPanel>
      }
    />
  );
}

// All drawing cards of a result, two per row. Enter switches a card between its
// 2D drawing and the rotating 3D view (the closest Raycast has to clicking a card).
export function DrawingsGrid({
  title,
  drawings,
  cards,
  targets,
}: {
  title: string;
  drawings: Artifact[];
  cards: Record<string, string>;
  targets: SpinTarget[];
}) {
  const spin = useSpinState();
  return (
    <Grid navigationTitle={title} columns={2} aspectRatio="1" fit={Grid.Fit.Contain} inset={Grid.Inset.Small}>
      {drawings.map((d) => {
        const target = targets.find((t) => t.key === d.path);
        const shown = spin.gif(d.path) ?? cards[d.path] ?? d.path;
        const is3D = spin.is3D(d.path);
        return (
          <Grid.Item
            key={d.path}
            content={{ source: shown }}
            keywords={[d.title, d.note]}
            accessory={is3D ? { icon: Icon.RotateClockwise, tooltip: "3D" } : undefined}
            actions={
              <ActionPanel>
                {target && (
                  <Action
                    title={is3D ? "Show 2D" : "Show Rotating 3D"}
                    icon={is3D ? Icon.Image : Icon.RotateClockwise}
                    onAction={() => toggle3D(target)}
                  />
                )}
                <Action.Push
                  title="Show Large"
                  icon={Icon.MagnifyingGlass}
                  target={<LargeView path={shown} title={d.title} />}
                />
                <Action.Open title="Open in Default App" target={shown} />
                <Action.ShowInFinder path={d.path} />
              </ActionPanel>
            }
          />
        );
      })}
    </Grid>
  );
}
