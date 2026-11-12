// Convert Units: type a value, pick its unit from the dropdown beside the search
// bar, and read every related unit; the selected row shows its evidence.
import type { LaunchProps } from "@raycast/api";
import { UnitsView } from "./components/UnitsView";

export default function Command(props: LaunchProps<{ arguments: { query?: string } }>) {
  return <UnitsView initialText={props.arguments.query ?? ""} />;
}
