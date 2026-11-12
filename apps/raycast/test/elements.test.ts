import { existsSync, utimesSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { RunResponse } from "../src/lib/contract";
import { blockColors, periodicTableSize, periodicTableSvg } from "../src/lib/elements";
import { pruneImages, writeImage } from "../src/lib/images";
import { clickableTable, pickItems } from "../src/lib/pick";
import { fixture, tempDir } from "./helpers";

const periodic = (JSON.parse(fixture("element-periodic-table")) as RunResponse).result;
const table = periodic.tables[0];

describe("clickable table as a list", () => {
  const items = pickItems(table);

  it("finds the clickable table only in the periodic table result", () => {
    expect(clickableTable(periodic)).toBe(table);
    expect(clickableTable((JSON.parse(fixture("element-card")) as RunResponse).result)).toBeUndefined();
  });

  it("lists all 118 elements in order of atomic number", () => {
    expect(items).toHaveLength(118);
    expect(items.map((i) => Number(i.top))).toEqual(Array.from({ length: 118 }, (_, i) => i + 1));
  });

  it("keeps what search needs: symbol, number, name", () => {
    expect(items[25]).toEqual({ value: "Fe", top: "26", name: "Iron", extra: "55.845", tag: "d" });
    expect(items[57]).toMatchObject({ value: "Ce", tag: "f" });
  });

  it("colors blocks like the web UI", () => {
    expect(blockColors(table)).toEqual({ s: "#f43f5e", p: "#f59e0b", d: "#3b82f6", f: "#10b981" });
  });
});

describe("periodicTableSvg", () => {
  const dark = periodicTableSvg(table, "dark", "Fe");
  const light = periodicTableSvg(table, "light");

  it("has one tile per element, plus the legend", () => {
    expect(dark.match(/<rect /g)).toHaveLength(118 + 4);
    expect(dark).toContain(">Fe<");
    expect(dark).toContain(">26<");
    expect(dark).not.toContain(">Iron<"); // compact tiles: number and symbol only
  });

  it("has a transparent background and theme-colored text", () => {
    expect(dark).not.toMatch(/<rect [^>]*fill="#ffffff"/);
    expect(dark).toContain('fill="#f3f4f6">Fe<');
    expect(light).toContain('fill="#111827">Fe<');
  });

  it("outlines the selected element", () => {
    expect(dark).toMatch(/stroke="#ffffff" stroke-width="2.5"\/>\n<text[^>]*>26</);
    expect(light).not.toContain('stroke-width="2.5"');
  });

  it("uses font-weight 700, which macOS's SVG renderer honors", () => {
    expect(dark).toContain('font-weight="700"');
    expect(dark).not.toContain('font-weight="bold"');
  });

  it("fits its declared size", () => {
    const { width, height } = periodicTableSize(table);
    expect(dark).toContain(`width="${width}" height="${height}"`);
    expect(width).toBeLessThan(700);
  });
});

describe("image files", () => {
  it("get a new name every time and are pruned after an hour", () => {
    const dir = tempDir();
    const a = writeImage("<svg/>", "periodic table", dir);
    const b = writeImage("<svg/>", "periodic table", dir);
    expect(a).not.toBe(b);
    expect(a).toMatch(/periodic-table\.svg$/);
    utimesSync(a, new Date(0), new Date(0));
    pruneImages(dir);
    expect(existsSync(a)).toBe(false);
    expect(existsSync(b)).toBe(true);
  });
});
