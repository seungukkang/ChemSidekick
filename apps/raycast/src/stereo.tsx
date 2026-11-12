// Stereoisomers: type a SMILES after the command (e.g. "stereo CC(Br)C(Br)C")
// and see every stereoisomer as a card; Enter on a card turns it in 3D.
// cmd-E changes the options (max isomers, 3D, ...).
import { Detail, type LaunchProps } from "@raycast/api";
import { ErrorView } from "./components/ErrorView";
import { ResultView } from "./components/ResultView";
import { useToolInfo } from "./components/use-tool";

export default function Command(props: LaunchProps<{ arguments: { smiles: string } }>) {
  const { tool, error, revalidate } = useToolInfo("stereo");
  if (error) return <ErrorView error={error} onRetry={revalidate} />;
  if (!tool) return <Detail isLoading markdown="Starting…" />;
  return <ResultView tool={tool} input={{ smiles: props.arguments.smiles.trim() }} />;
}
