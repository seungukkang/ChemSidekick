// Finding the csk executable. Raycast does not get the terminal's PATH, so csk is
// always run by absolute path: the "csk Path" preference, else the usual places.
import { accessSync, constants } from "node:fs";
import { join } from "node:path";
import { TransportError } from "./errors";

export const INSTALL_HINT = "uv tool install --editable .";

export function candidatePaths(preferred: string | undefined, home: string): string[] {
  if (preferred && preferred.trim()) return [preferred.trim()];
  return [join(home, ".local/bin/csk"), "/opt/homebrew/bin/csk", "/usr/local/bin/csk"];
}

export function isExecutable(path: string): boolean {
  try {
    accessSync(path, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

export function locateCsk(
  preferred: string | undefined,
  home: string,
  executable: (path: string) => boolean = isExecutable,
): string {
  const candidates = candidatePaths(preferred, home);
  const found = candidates.find(executable);
  if (found) return found;
  if (preferred && preferred.trim()) {
    throw new TransportError(
      "not_found",
      `The csk Path in the extension preferences is not an executable file: ${preferred.trim()}`,
    );
  }
  throw new TransportError(
    "not_found",
    `csk was not found. Install it in the ChemSidekick folder with \`${INSTALL_HINT}\`, ` +
      "or set its path in the extension preferences.",
    `Looked in:\n${candidates.join("\n")}`,
  );
}
