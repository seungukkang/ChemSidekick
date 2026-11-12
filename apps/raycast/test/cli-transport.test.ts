import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { CliTransport, parseResponse, runArgs } from "../src/lib/cli-transport";
import type { ErrorResponse, RunResponse, ToolListResponse } from "../src/lib/contract";
import { TransportError } from "../src/lib/errors";
import { FIXTURES, fakeCsk, fixture, tempDir } from "./helpers";

const ok = (stdout: string, exitCode = 0) => ({ stdout, stderr: "", exitCode, timedOut: false });

function kindOf(fn: () => unknown): string {
  try {
    fn();
  } catch (e) {
    if (e instanceof TransportError) return e.kind;
    throw e;
  }
  return "no error";
}

describe("parseResponse", () => {
  it("reads a run response", () => {
    const r = parseResponse<RunResponse>(ok(fixture("element-card"))) as RunResponse;
    expect(r.ok).toBe(true);
    expect(r.result.answer).toBe("Fe · Iron · Z = 26");
    expect(r.run.tool_id).toBe("REF-01");
  });

  it("reads an error response without throwing", () => {
    const r = parseResponse<RunResponse>(ok(fixture("element-error"), 1)) as ErrorResponse;
    expect(r.ok).toBe(false);
    expect(r.error.type).toBe("input");
    expect(r.error.message).toContain("Did you mean");
  });

  it("reads the tool list with input schemas", () => {
    const r = parseResponse<ToolListResponse>(ok(fixture("list"))) as ToolListResponse;
    expect(r.tools.map((t) => t.id)).toEqual(["STR-01", "STR-02", "REF-01"]);
    const stereo = r.tools.find((t) => t.name === "stereo")!;
    expect((stereo.input_schema.properties as Record<string, unknown>).smiles).toBeTruthy();
  });

  it("rejects another contract version", () => {
    const other = JSON.stringify({ contract: 2, csk_version: "9.0.0", ok: true });
    expect(kindOf(() => parseResponse(ok(other)))).toBe("contract_mismatch");
  });

  it("classifies output that is not a contract response", () => {
    expect(kindOf(() => parseResponse({ ...ok("Usage: csk ..."), exitCode: 2 }))).toBe("usage");
    const importError = {
      stdout: "",
      stderr: "ModuleNotFoundError: No module named 'rdkit'",
      exitCode: 1,
      timedOut: false,
    };
    expect(kindOf(() => parseResponse(importError))).toBe("reinstall");
    expect(kindOf(() => parseResponse(ok("hello", 1)))).toBe("not_json");
    expect(kindOf(() => parseResponse(ok('{"a": 1}')))).toBe("not_json");
    expect(kindOf(() => parseResponse({ ...ok(""), timedOut: true }))).toBe("timeout");
  });
});

describe("runArgs", () => {
  it("always asks for JSON and never opens a browser", () => {
    expect(runArgs("stereo")).toEqual(["run", "stereo", "--json", "--no-open"]);
  });

  it("maps options to flags", () => {
    expect(runArgs("element", { record: false, timeoutS: 30, confirmed: true })).toEqual([
      "run",
      "element",
      "--json",
      "--no-open",
      "--no-record",
      "--timeout",
      "30",
      "--yes",
    ]);
  });
});

describe("CliTransport with a fake csk", () => {
  it("sends the input as JSON on stdin", async () => {
    const dir = tempDir();
    const csk = fakeCsk(dir, `cat "${join(FIXTURES, "element-card.json")}"`);
    const transport = new CliTransport(csk, { home: dir });
    const r = (await transport.run("element", { query: "Fe" })) as RunResponse;
    expect(r.result.answer).toBe("Fe · Iron · Z = 26");
    expect(JSON.parse(readFileSync(join(dir, "stdin.txt"), "utf-8"))).toEqual({ query: "Fe" });
    expect(readFileSync(join(dir, "args.txt"), "utf-8").trim()).toBe("run element --json --no-open");
  });

  it("returns csk's error response as data", async () => {
    const dir = tempDir();
    const body = `printf '%s' '${fixture("element-error").replace(/'/g, "'\\''")}'; exit 1`;
    const r = (await new CliTransport(fakeCsk(dir, body), { home: dir }).run("element", {})) as ErrorResponse;
    expect(r.ok).toBe(false);
    expect(r.error.type).toBe("input");
  });

  it("lists tools with `csk list --json` and searches with `csk search`", async () => {
    const dir = tempDir();
    const listPath = join(FIXTURES, "list.json");
    const transport = new CliTransport(fakeCsk(dir, `cat "${listPath}"`), { home: dir });
    await transport.listTools();
    expect(readFileSync(join(dir, "args.txt"), "utf-8").trim()).toBe("list --json");
    await transport.listTools("xyz");
    expect(readFileSync(join(dir, "args.txt"), "utf-8").trim()).toBe("search xyz --json");
  });

  it("runs csk with a minimal environment", async () => {
    const dir = tempDir();
    const body = `printf '{"contract": 1, "csk_version": "x", "ok": true, "number": 1, "saved_to": "%s|%s"}' "$HOME" "$PATH"`;
    const r = await new CliTransport(fakeCsk(dir, body), { home: "/Users/me" }).save(1);
    expect(r.ok && "saved_to" in r && r.saved_to).toBe("/Users/me|/usr/bin:/bin:/usr/sbin:/sbin");
  });

  it("asks `csk gif` for a rotating view with the frame on stdin", async () => {
    const dir = tempDir();
    const transport = new CliTransport(fakeCsk(dir, `cat "${join(FIXTURES, "gif.json")}"`), { home: dir });
    const frame = {
      symbols: ["H", "H"],
      coords: [
        [0, 0, 0],
        [0, 0, 0.74],
      ] as [number, number, number][],
      comment: "",
    };
    const r = await transport.gif({ frame });
    expect(r.ok && "path" in r && r.path).toMatch(/spin\.gif$/);
    expect(readFileSync(join(dir, "args.txt"), "utf-8").trim()).toBe("gif --json");
    expect(JSON.parse(readFileSync(join(dir, "stdin.txt"), "utf-8"))).toEqual({ frame });
  });

  it("stops a csk that hangs", async () => {
    const dir = tempDir();
    const transport = new CliTransport(fakeCsk(dir, "sleep 5"), { home: dir, safetyTimeoutMs: 300 });
    await expect(transport.run("element", {})).rejects.toMatchObject({ kind: "timeout" });
  });

  it("reports a csk that cannot be started", async () => {
    const transport = new CliTransport("/nonexistent/csk", { home: "/tmp" });
    await expect(transport.listTools()).rejects.toMatchObject({ kind: "not_found" });
  });
});
