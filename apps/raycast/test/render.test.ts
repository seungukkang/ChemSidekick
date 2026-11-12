import { describe, expect, it } from "vitest";
import type { RunResponse, Table } from "../src/lib/contract";
import { DRAWING_WIDTH, MAX_TABLE_ROWS, renderResult, tableMarkdown } from "../src/lib/render";
import { fixture } from "./helpers";

const run = (name: string) => JSON.parse(fixture(name)) as RunResponse;

describe("renderResult", () => {
  it("element card: answer, key values as a table three per row, tables and references", () => {
    const r = run("element-card");
    const view = renderResult(r.result, r.run);
    expect(view.markdown.startsWith("# Fe · Iron · Z = 26")).toBe(true);
    expect(view.markdown).toContain(
      "| Standard atomic weight | Electron configuration | Group · Period · Block |\n| :---: | :---: | :---: |\n" +
        "| **55.845(2)** | **[Ar] 3d⁶ 4s²** |",
    );
    expect(view.markdown).toContain("| Electronegativity (Pauling) |\n| :---: |\n| **1.83** |"); // 4th on a new row
    expect(view.markdown).toContain("_Check ✓ 2,3,4 (see References)_");
    expect(view.markdown.indexOf("Standard atomic weight")).toBeLessThan(view.markdown.indexOf("### Identity"));
    expect(view.markdown).toContain("### Natural isotopes");
    expect(view.markdown).toContain("### References");
    expect(view.metadata.map((m) => m.label)).toEqual(["Tool", "Time", "Result"]);
    expect(view.metadata.at(-1)).toEqual({ label: "Result", value: `#${r.run.number}` });
    expect(view.viewer).toBeUndefined();
  });

  it("stereo: drawings two per row with captions, 3D viewer, other files", () => {
    const r = run("stereo-dibromobutane");
    const view = renderResult(r.result, r.run);
    const lines = view.markdown.split("\n");
    const pair = lines.find((l) => l.includes("isomer-01.svg"))!;
    expect(pair).toBe(
      `![#1 · meso](/fixture/cache/recent/00003-stereo/isomers/isomer-01.svg?raycast-width=${DRAWING_WIDTH}) ` +
        `![#2 · enantiomer of #3](/fixture/cache/recent/00003-stereo/isomers/isomer-02.svg?raycast-width=${DRAWING_WIDTH})`,
    );
    expect(view.markdown).toContain("**#1 · meso** (2R,3S)\n\n**#2 · enantiomer of #3** (2R,3R)\n");
    expect(lines.filter((l) => l.includes("isomer-03.svg"))).toHaveLength(1); // third on its own row
    expect(view.drawings).toHaveLength(3);
    expect(view.viewer).toMatch(/viewer\.html$/);
    expect(view.files.map((f) => f.kind)).toEqual(["sdf"]);
    expect(view.markdown.indexOf("isomer-01.svg")).toBeLessThan(view.markdown.indexOf("### Stereoisomers"));
  });

  it("puts the evidence below the result", () => {
    const r = run("element-periodic-table");
    const view = renderResult(r.result, r.run);
    expect(view.markdown.indexOf("### Assumptions")).toBeGreaterThan(view.markdown.indexOf("```"));
  });

  it("shows the periodic table as a fixed-width grid, not a markdown table", () => {
    const r = run("element-periodic-table");
    const md = renderResult(r.result, r.run).markdown;
    expect(md).not.toContain("| Hg |");
    const grid = md.split("```")[1].split("\n").filter(Boolean);
    // Every cell padded to 2 characters, so columns line up and "Hg" stays on one line.
    expect(grid).toContain("6  Cs Ba La Hf Ta W  Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn");
    expect(grid[0]).toBe("   1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17 18");
  });

  it("xyz: the drawing and its rotating 3D view side by side, then the information", () => {
    const r = run("xyz-water");
    const drawing = r.result.artifacts.find((a) => a.kind === "svg")!;
    const view = renderResult(r.result, r.run, { beside: { [drawing.path]: "/gifs/w.gif" } });
    const row = view.markdown.split("\n").find((l) => l.includes("structure.svg"))!;
    expect(row).toContain("/gifs/w.gif");
    expect(view.markdown).toContain("bonds inferred from coordinates · 2D and rotating 3D");
    expect(view.markdown.indexOf("structure.svg")).toBeLessThan(view.markdown.indexOf("### Summary"));
  });

  it("shows a figure in place of a clickable grid when one is given", () => {
    const r = run("element-periodic-table");
    const md = renderResult(r.result, r.run, { grids: { 0: "![Periodic table](/img/pt.svg)" } }).markdown;
    expect(md).toContain("![Periodic table](/img/pt.svg)");
    expect(md).not.toContain("```");
  });

  it("swaps a drawing for its rotating 3D view in place, caption kept", () => {
    const r = run("stereo-dibromobutane");
    const [d1] = r.result.artifacts;
    const view = renderResult(r.result, r.run, { swaps: { [d1.path]: "/gifs/1.gif" } });
    expect(view.markdown).toContain(
      `![#1 · meso](/gifs/1.gif?raycast-width=${DRAWING_WIDTH}) ![#2 · enantiomer of #3](`,
    );
    expect(view.markdown).toContain("**#1 · meso** (2R,3S)");
    expect(view.markdown).not.toContain("isomer-01.svg");
  });

  it("shows rotating views of a structure without drawings near the top", () => {
    const r = run("xyz-water");
    const view = renderResult(r.result, r.run, { spins: ["/gifs/spin.gif"] });
    expect(view.markdown.indexOf("/gifs/spin.gif")).toBeLessThan(view.markdown.indexOf("###"));
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
