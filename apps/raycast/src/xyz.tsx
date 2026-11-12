// XYZ Viewer: the xyz tool's form (paste coordinates, or cmd-shift-V to paste
// from the clipboard), then the formula, molecular weight, 2D and 3D views.
import { Detail, getPreferenceValues } from "@raycast/api";
import { ErrorView } from "./components/ErrorView";
import { ToolForm } from "./components/ToolForm";
import { useToolInfo } from "./components/use-tool";

export default function Command() {
  const { autoOpen3D } = getPreferenceValues<{ autoOpen3D?: boolean }>();
  const { tool, error, revalidate } = useToolInfo("xyz");
  if (error) return <ErrorView error={error} onRetry={revalidate} />;
  if (!tool) return <Detail isLoading markdown="Starting…" />;
  return <ToolForm tool={tool} autoOpenViewer={autoOpen3D !== false} />;
}
