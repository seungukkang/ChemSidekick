import { chmodSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// Shared with the Python tests: real csk responses, normalized (scripts/export_contract.py).
export const FIXTURES = join(__dirname, "..", "..", "..", "tests", "contract", "fixtures");

export function fixture(name: string): string {
  return readFileSync(join(FIXTURES, `${name}.json`), "utf-8");
}

export function tempDir(): string {
  return mkdtempSync(join(tmpdir(), "csk-raycast-test-"));
}

// A fake csk: a shell script that saves its arguments and stdin, then runs `body`.
export function fakeCsk(dir: string, body: string): string {
  const path = join(dir, "csk");
  writeFileSync(path, `#!/bin/sh\necho "$@" > "${dir}/args.txt"\ncat > "${dir}/stdin.txt"\n${body}\n`);
  chmodSync(path, 0o755);
  return path;
}
