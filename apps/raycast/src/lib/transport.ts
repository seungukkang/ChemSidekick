// How screens talk to ChemSidekick. Screens only know this interface:
// v0.2 runs csk (CliTransport); v0.3 will call a local HTTP API with the same JSON.
import type { ErrorResponse, RunResponse, SaveResponse, ToolListResponse } from "./contract";

export interface RunOptions {
  record?: boolean; // false: --no-record (default true)
  timeoutS?: number; // csk's own time limit (--timeout)
  confirmed?: boolean; // heavy tools: --yes
}

export interface Transport {
  listTools(query?: string): Promise<ToolListResponse | ErrorResponse>;
  run(tool: string, input: Record<string, unknown>, options?: RunOptions): Promise<RunResponse | ErrorResponse>;
  save(number: number): Promise<SaveResponse | ErrorResponse>;
}
