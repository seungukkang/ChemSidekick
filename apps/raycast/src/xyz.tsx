// XYZ Viewer: the xyz tool's form, filled in from the clipboard when it holds
// coordinates, so one Enter shows the formula, molecular weight, and 3D view.
import { Clipboard, Form, getPreferenceValues } from "@raycast/api";
import { usePromise } from "@raycast/utils";
import { ErrorView } from "./components/ErrorView";
import { ToolForm } from "./components/ToolForm";
import { useToolInfo } from "./components/use-tool";
import { looksLikeXyz } from "./lib/xyz-detect";

async function clipboardXyz(): Promise<string | undefined> {
  const text = await Clipboard.readText();
  return looksLikeXyz(text) ? text : undefined;
}

export default function Command() {
  const { autoOpen3D } = getPreferenceValues<{ autoOpen3D?: boolean }>();
  const { tool, error, revalidate } = useToolInfo("xyz");
  const clip = usePromise(clipboardXyz);
  if (error) return <ErrorView error={error} onRetry={revalidate} />;
  if (!tool || clip.isLoading) return <Form isLoading />;
  return (
    <ToolForm tool={tool} input={clip.data ? { text: clip.data } : undefined} autoOpenViewer={autoOpen3D !== false} />
  );
}
