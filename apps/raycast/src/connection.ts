// The one place that knows how this extension reaches ChemSidekick.
// v0.2: run csk. v0.3: return an HTTP transport here instead.
import { getPreferenceValues } from "@raycast/api";
import { homedir } from "node:os";
import { CliTransport } from "./lib/cli-transport";
import { locateCsk } from "./lib/locate";
import type { Transport } from "./lib/transport";

export function getTransport(): Transport {
  const { cskPath } = getPreferenceValues<{ cskPath?: string }>();
  const home = homedir();
  return new CliTransport(locateCsk(cskPath, home), { home });
}
