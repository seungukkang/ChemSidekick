// Placeholder command (M0): shows where csk was found and how long it takes to run
// from inside Raycast. The tool list, forms, and results come in M2-M3.
import { Action, ActionPanel, Detail } from "@raycast/api";
import { usePromise } from "@raycast/utils";
import { cskPath, runCsk } from "./csk";

const CHECKS: { label: string; args: string[] }[] = [
  { label: "csk --version", args: ["--version"] },
  { label: "csk element Fe --json", args: ["element", "Fe", "--json"] },
  {
    label: "csk stereo CC(O)C(O)C(O)C --json --no-3d",
    args: ["stereo", "CC(O)C(O)C(O)C", "--json", "--no-3d", "--no-open"],
  },
  { label: "csk stereo CC(O)C(O)C(O)C --json (with 3D)", args: ["stereo", "CC(O)C(O)C(O)C", "--json", "--no-open"] },
];

async function measure(): Promise<string> {
  const lines = [`# ChemSidekick`, "", `csk: \`${cskPath()}\``, "", "| Command | Time | Exit |", "|---|---|---|"];
  for (const check of CHECKS) {
    const run = await runCsk(check.args);
    lines.push(`| \`${check.label}\` | ${(run.elapsedMs / 1000).toFixed(2)} s | ${run.exitCode} |`);
  }
  lines.push("", "_Times are for reference only (measured from Raycast, one run each)._");
  return lines.join("\n");
}

export default function Command() {
  const { data, isLoading, error, revalidate } = usePromise(measure);
  const markdown = error ? `# csk not available\n\n${error.message}` : (data ?? "Running csk…");
  return (
    <Detail
      isLoading={isLoading}
      markdown={markdown}
      actions={
        <ActionPanel>
          <Action title="Measure Again" onAction={revalidate} />
        </ActionPanel>
      }
    />
  );
}
