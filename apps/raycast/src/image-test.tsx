// Development check (M0, plan question Q2). Remove once the real result view exists (M3).
//
// Round 1: Detail markdown shows a local SVG by absolute path, file:// URL, base64
// data URI, and with a size hint.
// Round 2: macOS's SVG renderer draws <rect width='100%'> as a small square, and
// Raycast caches images by path (always write new file names).
// Round 3 (decided): solid white backdrop with a border in the theme color (#ff4b4b).
// This command now just shows what csk makes.
import { Detail } from "@raycast/api";
import { usePromise } from "@raycast/utils";
import { readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { runCsk } from "./csk";
import { THEME_COLOR } from "./theme";

async function build(): Promise<string> {
  const run = await runCsk(["stereo", "CC(Br)C(Br)C", "--json", "--no-3d", "--no-open"]);
  if (run.exitCode !== 0) return `# csk failed\n\n\`\`\`\n${run.stderr}\n\`\`\``;
  // JSON contract v1: the ToolResult is under "result".
  const { result } = JSON.parse(run.stdout) as { result: { artifacts: { kind: string; path: string }[] } };
  const molecule = result.artifacts.find((a) => a.kind === "svg")?.path;
  if (!molecule) return "# No SVG artifact in the stereo result";
  const svg = readFileSync(molecule, "utf-8");
  if (!svg.includes(`stroke='${THEME_COLOR}'`)) return "# The SVG border is not the theme color (unexpected)";

  // A new file name every run: Raycast caches images by path.
  const path = join(tmpdir(), `chemsidekick-final-${Date.now()}.svg`);
  writeFileSync(path, svg, "utf-8");
  const sections = ["# Drawing as csk makes it", "", `![molecule](${encodeURI(path)})`, ""];
  return sections.join("\n");
}

export default function Command() {
  const { data, isLoading, error } = usePromise(build);
  return <Detail isLoading={isLoading} markdown={error ? `# Error\n\n${error.message}` : (data ?? "")} />;
}
