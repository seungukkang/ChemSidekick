// What to show for each kind of failure: a title, markdown, and an optional command
// to copy (install / reinstall). Pure, so it can be tested without Raycast.
import type { ErrorInfo } from "./contract";
import { isTransportError } from "./errors";
import { INSTALL_HINT } from "./locate";

export interface ErrorText {
  title: string;
  markdown: string;
  copyCommand?: string; // a shell command that fixes the problem
  copyText: string; // everything, for "Copy Error"
  showPreferences: boolean; // offer "Open Extension Preferences"
}

const TITLES: Record<string, string> = {
  input: "Check the input",
  limit: "Stopped at the time or memory limit",
  crash: "The tool crashed",
  confirm: "This tool needs confirmation",
  missing_program: "A required program is missing",
  config: "Problem in the config file",
  not_found: "csk not found",
  timeout: "csk did not finish",
  usage: "csk did not understand the request",
  reinstall: "csk could not start",
  not_json: "Unexpected output from csk",
  contract_mismatch: "csk and the extension do not match",
};

function codeBlock(text: string): string {
  return "```\n" + text.replace(/```/g, "'''").trimEnd() + "\n```";
}

export function errorText(error: unknown): ErrorText {
  if (isTransportError(error)) {
    const parts = [`# ${TITLES[error.kind]}`, "", error.message];
    if (error.detail) parts.push("", codeBlock(error.detail));
    return {
      title: TITLES[error.kind],
      markdown: parts.join("\n"),
      copyCommand:
        error.kind === "not_found"
          ? INSTALL_HINT
          : error.kind === "reinstall"
            ? `${INSTALL_HINT} --reinstall`
            : undefined,
      copyText: [error.message, error.detail].filter(Boolean).join("\n\n"),
      showPreferences: error.kind === "not_found",
    };
  }
  if (isErrorInfo(error)) {
    const title = TITLES[error.type] ?? "Error";
    const parts = [`# ${title}`, "", error.message];
    if (error.details.length) {
      parts.push("", ...error.details.map((d) => `- ${d.field ? `**${d.field}**: ` : ""}${d.message}`));
    }
    if (error.traceback) parts.push("", "## Traceback", "", codeBlock(error.traceback));
    return {
      title,
      markdown: parts.join("\n"),
      copyText: [error.message, error.traceback].filter(Boolean).join("\n\n"),
      showPreferences: false,
    };
  }
  const message = error instanceof Error ? error.message : String(error);
  return { title: "Error", markdown: `# Error\n\n${message}`, copyText: message, showPreferences: false };
}

export function isErrorInfo(value: unknown): value is ErrorInfo {
  return typeof value === "object" && value !== null && "type" in value && "message" in value && "details" in value;
}
