import { useCachedPromise } from "@raycast/utils";
import { getTransport } from "../connection";
import type { ToolInfo, ToolListResponse } from "../lib/contract";

async function loadTools(): Promise<ToolListResponse> {
  const response = await getTransport().listTools();
  if (!response.ok) throw response.error; // ErrorInfo: shown by ErrorView
  return response;
}

// One tool's description (title, input schema, ...) from `csk list --json`,
// cached between launches, for commands made for one tool.
export function useToolInfo(name: string): {
  tool?: ToolInfo;
  isLoading: boolean;
  error?: unknown;
  revalidate: () => void;
} {
  const { data, isLoading, error, revalidate } = useCachedPromise(loadTools, [], { keepPreviousData: true });
  const tool = data?.tools.find((t) => t.name === name);
  const missing = data && !tool ? new Error(`csk has no tool named "${name}". Update csk.`) : undefined;
  return { tool, isLoading, error: error ?? missing, revalidate };
}
