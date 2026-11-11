// Minimal csk runner for M0. Replaced by lib/locate.ts and lib/cli-transport.ts in M2.
import { getPreferenceValues } from "@raycast/api";
import { execFile } from "node:child_process";
import { accessSync, constants } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export interface CskRun {
  stdout: string;
  stderr: string;
  exitCode: number;
  elapsedMs: number;
}

// Raycast does not get the terminal's PATH, so csk is always run by absolute path.
export function cskPath(): string {
  const { cskPath } = getPreferenceValues<{ cskPath?: string }>();
  const candidates = [cskPath, join(homedir(), ".local/bin/csk"), "/opt/homebrew/bin/csk"];
  for (const path of candidates) {
    if (!path) continue;
    try {
      accessSync(path, constants.X_OK);
      return path;
    } catch {
      // try the next one
    }
  }
  throw new Error("csk not found. Install it with `uv tool install --editable .` in the ChemSidekick folder.");
}

// Generous safety limit: csk's own runner enforces the real limits.
const SAFETY_TIMEOUT_MS = 10 * 60 * 1000;

export function runCsk(args: string[]): Promise<CskRun> {
  const file = cskPath();
  const start = performance.now();
  return new Promise((resolve) => {
    execFile(
      file,
      args,
      {
        timeout: SAFETY_TIMEOUT_MS,
        maxBuffer: 64 * 1024 * 1024,
        env: { HOME: homedir(), LANG: "en_US.UTF-8", PATH: "/usr/bin:/bin:/usr/sbin:/sbin" },
      },
      (error, stdout, stderr) => {
        const code = error && typeof error.code === "number" ? error.code : error ? -1 : 0;
        resolve({ stdout, stderr, exitCode: code, elapsedMs: performance.now() - start });
      },
    );
  });
}
