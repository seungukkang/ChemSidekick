// Transport for v0.2: run `csk ... --json` as a child process and read the one
// JSON object it prints (contract v1). Tool input goes to `csk run` on stdin.
import { execFile } from "node:child_process";
import { CONTRACT_VERSION } from "./contract";
import type { ErrorResponse, GifRequest, GifResponse, RunResponse, SaveResponse, ToolListResponse } from "./contract";
import { TransportError } from "./errors";
import { INSTALL_HINT } from "./locate";
import type { RunOptions, Transport } from "./transport";

// Generous on purpose: csk's runner enforces the real limits; this only catches
// a csk that hangs. Slow runs show "Running…" rather than being stopped.
export const SAFETY_TIMEOUT_MS = 10 * 60 * 1000;

export interface ExecResult {
  stdout: string;
  stderr: string;
  exitCode: number;
  timedOut: boolean;
}

export interface CliTransportOptions {
  home: string;
  safetyTimeoutMs?: number;
}

export class CliTransport implements Transport {
  constructor(
    readonly cskPath: string,
    private readonly options: CliTransportOptions,
  ) {}

  async listTools(query?: string): Promise<ToolListResponse | ErrorResponse> {
    const args = query ? ["search", query, "--json"] : ["list", "--json"];
    return parseResponse<ToolListResponse>(await this.exec(args));
  }

  async run(
    tool: string,
    input: Record<string, unknown>,
    options: RunOptions = {},
  ): Promise<RunResponse | ErrorResponse> {
    return parseResponse<RunResponse>(await this.exec(runArgs(tool, options), JSON.stringify(input)));
  }

  async save(number: number): Promise<SaveResponse | ErrorResponse> {
    return parseResponse<SaveResponse>(await this.exec(["save", String(number), "--json"]));
  }

  async gif(request: GifRequest): Promise<GifResponse | ErrorResponse> {
    return parseResponse<GifResponse>(await this.exec(["gif", "--json"], JSON.stringify(request)));
  }

  private exec(args: string[], stdin = ""): Promise<ExecResult> {
    return execCsk(this.cskPath, args, stdin, this.options);
  }
}

export function runArgs(tool: string, options: RunOptions = {}): string[] {
  const args = ["run", tool, "--json", "--no-open"];
  if (options.record === false) args.push("--no-record");
  if (options.timeoutS !== undefined) args.push("--timeout", String(options.timeoutS));
  if (options.confirmed) args.push("--yes");
  return args;
}

export function execCsk(
  file: string,
  args: string[],
  stdin: string,
  options: CliTransportOptions,
): Promise<ExecResult> {
  return new Promise((resolve, reject) => {
    const child = execFile(
      file,
      args,
      {
        timeout: options.safetyTimeoutMs ?? SAFETY_TIMEOUT_MS,
        maxBuffer: 64 * 1024 * 1024,
        // A minimal environment: csk needs no PATH, and Raycast's own variables stay out.
        env: { HOME: options.home, LANG: "en_US.UTF-8", PATH: "/usr/bin:/bin:/usr/sbin:/sbin" },
      },
      (error, stdout, stderr) => {
        if (error && "code" in error && (error.code === "ENOENT" || error.code === "EACCES")) {
          reject(new TransportError("not_found", `csk could not be started: ${file} (${error.code}).`));
          return;
        }
        const timedOut = Boolean(error && error.killed && error.signal === "SIGTERM");
        const exitCode = error ? (typeof error.code === "number" ? error.code : -1) : 0;
        resolve({ stdout, stderr, exitCode, timedOut });
      },
    );
    child.stdin?.on("error", () => {
      // csk may exit before reading stdin (e.g. a usage error); the exit code tells why.
    });
    child.stdin?.end(stdin);
  });
}

// Python could not import a module: the uv tool environment is out of date.
const STARTUP_FAILURE = /ModuleNotFoundError|ImportError/;

export function parseResponse<T extends { ok: true }>(r: ExecResult): T | ErrorResponse {
  if (r.timedOut) {
    throw new TransportError("timeout", "csk did not finish within the safety limit and was stopped.", r.stderr);
  }
  let data: unknown;
  try {
    data = JSON.parse(r.stdout);
  } catch {
    if (r.exitCode === 2) {
      throw new TransportError(
        "usage",
        "csk did not understand the command. The extension and csk may be from different versions.",
        r.stderr,
      );
    }
    if (STARTUP_FAILURE.test(r.stderr)) {
      throw new TransportError(
        "reinstall",
        `csk could not start. Reinstall it in the ChemSidekick folder: \`${INSTALL_HINT} --reinstall\`.`,
        r.stderr,
      );
    }
    throw new TransportError(
      "not_json",
      `csk printed something unexpected (exit code ${r.exitCode}).`,
      r.stderr || r.stdout,
    );
  }
  if (typeof data !== "object" || data === null || !("contract" in data) || !("ok" in data)) {
    throw new TransportError("not_json", "csk printed JSON that is not a contract response.", r.stdout);
  }
  const contract = (data as { contract: unknown }).contract;
  if (contract !== CONTRACT_VERSION) {
    const version = (data as { csk_version?: string }).csk_version ?? "unknown";
    throw new TransportError(
      "contract_mismatch",
      `csk ${version} speaks contract version ${String(contract)}, but this extension expects ${CONTRACT_VERSION}. ` +
        "Update csk or the extension so they match.",
    );
  }
  return data as T | ErrorResponse;
}
