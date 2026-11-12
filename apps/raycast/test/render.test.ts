import { describe, expect, it } from "vitest";
import type { RunResponse, Table } from "../src/lib/contract";
import { MAX_TABLE_ROWS, renderResult, tableMarkdown } from "../src/lib/render";
import { fixture } from "./helpers";

const run = (name: string) => JSON.parse(fixture(name)) as RunResponse;

describe("renderResult", () => {
  it("element card: answer first, highlights in the side panel, tables and references", () => {
    const r = run("element-card");
    const view = renderResult(r.result, r.run);
    expect(view.markdown.startsWith("# Fe · Iron · Z = 26")).toBe(true);
    expect(view.markdown).toContain("### Natural isotopes");
    expect(view.markdown).toContain("### References");
    expect(view.metadata[0]).toEqual({
      label: "Standard atomic weight",
      value: "55.845(2)  (Check ✓ 2,3,4 (see References))",
    });
    expect(view.metadata.at(-1)).toEqual({ label: "Result", value: `#${r.run.number}` });
    expect(view.viewer).toBeUndefined();
  });

  it("stereo: drawings with captions, 3D viewer, other files", () => {
    const r = run("stereo-dibromobutane");
    const view = renderResult(r.result, r.run);
    expect(view.markdown).toContain("![#1 · meso](/fixture/cache/recent/00003-stereo/isomers/isomer-01.svg)");
    expect(view.markdown).toContain("**#1 · meso** · (2R,3S)");
    expect(view.viewer).toMatch(/viewer\.html$/);
    expect(view.files.map((f) => f.kind)).toEqual(["sdf"]);
    // drawings come before tables
    expect(view.markdown.indexOf("isomer-01.svg")).toBeLessThan(view.markdown.indexOf("### Stereoisomers"));
  });

  it("puts warnings above the answer", () => {
    const r = run("xyz-water");
    const view = renderResult({ ...r.result, warnings: ["Atoms 1 and 2 are only 0.1 Å apart."] }, r.run);
    expect(view.markdown.startsWith("> ⚠️ Atoms 1 and 2")).toBe(true);
  });

  it("marks a run that was not kept", () => {
    const r = run("element-periodic-table");
    expect(renderResult(r.result, r.run).metadata.at(-1)).toEqual({ label: "Result", value: "not kept" });
  });

  it("renders LaTeX formulas for Raycast", () => {
    const r = run("xyz-water");
    const view = renderResult({ ...r.result, formulas: [{ latex: "k = \\frac{k_B T}{h}", text: "k = kB T / h" }] });
    expect(view.markdown).toContain("$$k = \\frac{k_B T}{h}$$");
  });
});

describe("tableMarkdown", () => {
  const base: Table = {
    title: "T",
    columns: ["a", "b"],
    rows: [],
    minor_columns: [],
    action_field: null,
    action_columns: [],
    cells: {},
    tags: {},
    column_gaps: [],
  };

  it("escapes pipes and new lines in cells", () => {
    const md = tableMarkdown({
      ...base,
      rows: [
        ["x|y", "line1\nline2"],
        [null, 3],
      ],
    });
    expect(md).toContain("| x\\|y | line1 line2 |");
    expect(md).toContain("|  | 3 |");
  });

  it("cuts very long tables", () => {
    const rows = Array.from({ length: MAX_TABLE_ROWS + 5 }, (_, i) => [i, i]);
    const md = tableMarkdown({ ...base, rows });
    expect(md).toContain("5 more rows");
    expect(md).not.toContain(`| ${MAX_TABLE_ROWS} | ${MAX_TABLE_ROWS} |`);
  });
});
