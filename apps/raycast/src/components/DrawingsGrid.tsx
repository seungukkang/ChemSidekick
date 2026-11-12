import { Action, ActionPanel, Detail, Grid, Icon } from "@raycast/api";
import type { Artifact } from "../lib/contract";

function DrawingDetail({ drawing }: { drawing: Artifact }) {
  const caption = [drawing.title && `**${drawing.title}**`, drawing.note].filter(Boolean).join(" · ");
  return (
    <Detail
      navigationTitle={drawing.title || "Drawing"}
      markdown={`![${drawing.title}](${encodeURI(drawing.path)})\n\n${caption}`}
      actions={
        <ActionPanel>
          <Action.Open title="Open in Default App" target={drawing.path} />
          <Action.ShowInFinder path={drawing.path} />
        </ActionPanel>
      }
    />
  );
}

// All drawings of a result, two per row; Enter shows one large.
export function DrawingsGrid({ title, drawings }: { title: string; drawings: Artifact[] }) {
  return (
    <Grid navigationTitle={title} columns={2} aspectRatio="4/3" fit={Grid.Fit.Contain} inset={Grid.Inset.Small}>
      {drawings.map((d) => (
        <Grid.Item
          key={d.path}
          content={{ source: d.path }}
          title={d.title}
          subtitle={d.note}
          actions={
            <ActionPanel>
              <Action.Push title="Show Large" icon={Icon.MagnifyingGlass} target={<DrawingDetail drawing={d} />} />
              <Action.Open title="Open in Default App" target={d.path} />
              <Action.ShowInFinder path={d.path} />
            </ActionPanel>
          }
        />
      ))}
    </Grid>
  );
}
