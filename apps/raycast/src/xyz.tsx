// XYZ Viewer: the xyz tool's form, filled in from the clipboard when it holds
// coordinates, so one Enter shows the formula, molecular weight, and 3D view.
import { Clipboard, Detail, getPreferenceValues } from "@raycast/api";
import { useEffect, useState } from "react";
import { ErrorView } from "./components/ErrorView";
import { ToolForm } from "./components/ToolForm";
import { useToolInfo } from "./components/use-tool";
import { looksLikeXyz } from "./lib/xyz-detect";

export default function Command() {
  const { autoOpen3D } = getPreferenceValues<{ autoOpen3D?: boolean }>();
  const { tool, error, revalidate } = useToolInfo("xyz");
  // null: not read yet. The form appears only after the clipboard has been read.
  const [clip, setClip] = useState<string | undefined | null>(null);
  useEffect(() => {
    Clipboard.readText()
      .then((text) => setClip(looksLikeXyz(text) ? text : undefined))
      .catch(() => setClip(undefined));
  }, []);
  if (error) return <ErrorView error={error} onRetry={revalidate} />;
  if (!tool || clip === null) return <Detail isLoading markdown="Reading the clipboard…" />;
  return <ToolForm tool={tool} input={clip ? { text: clip } : undefined} autoOpenViewer={autoOpen3D !== false} />;
}
