// Amino Acids: every proteinogenic amino acid as a card with its structure,
// grouped by side-chain class; type W, Trp, a name, or a class to find one.
import type { LaunchProps } from "@raycast/api";
import { AminoAcidsView } from "./components/AminoAcidsView";

export default function Command(props: LaunchProps<{ arguments: { query?: string } }>) {
  return <AminoAcidsView initialSearch={props.arguments.query ?? ""} />;
}
