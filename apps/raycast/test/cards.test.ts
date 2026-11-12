import { existsSync, readdirSync, utimesSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  CARD_H,
  CARD_W,
  drawingCardSvg,
  escapeXml,
  fitFontSize,
  frameForDrawing,
  highlightCardsSvg,
  pruneCards,
  spinTargets,
  writeCard,
  xyzText,
} from "../src/lib/cards";
import type { RunResponse } from "../src/lib/contract";
import { fixture, tempDir } from "./helpers";

const RDKIT_LIKE = `<?xml version='1.0' encoding='iso-8859-1'?>
<svg version='1.1' baseProfile='full' xmlns='http://www.w3.org/2000/svg' xmlns:rdkit='http://www.rdkit.org/xml'
 width='300px' height='240px' viewBox='0 0 300 240'><rect id='csk-backdrop'/><path d='M0 0'/></svg>`;

const run = (name: string) => JSON.parse(fixture(name)) as RunResponse;

describe("drawingCardSvg", () => {
  it("nests the drawing in the card's drawing area with a centered caption", () => {
    const svg = drawingCardSvg(RDKIT_LIKE, "#1 · meso", "(2R,3S)");
    expect(svg).toContain(`width="${CARD_W}" height="${CARD_H}"`);
    expect(svg).toContain(
      `<svg x="10" y="10" width="300" height="240" viewBox="0 0 300 240"><rect id='csk-backdrop'/>`,
    );
    expect(svg).not.toContain("<?xml");
    expect(svg).toMatch(/text-anchor="middle"[^>]*font-weight="700"[^>]*>#1 · meso</);
    expect(svg).toMatch(/fill="#8a8a8a">\(2R,3S\)</);
    expect(svg).toContain('xmlns:rdkit="http://www.rdkit.org/xml"'); // RDKit metadata stays valid XML
  });

  it("escapes caption text", () => {
    expect(drawingCardSvg(RDKIT_LIKE, "a<b & c", "")).toContain(">a&lt;b &amp; c<");
    expect(escapeXml(`"'`)).toBe("&quot;&apos;");
  });

  it("rejects text that is not SVG", () => {
    expect(() => drawingCardSvg("hello", "", "")).toThrow("not an SVG");
  });
});

describe("highlightCardsSvg", () => {
  it("puts three cards per row", () => {
    const r = run("element-card");
    const svg = highlightCardsSvg(r.result.highlights); // 4 highlights -> 2 rows
    expect(svg.match(/<rect /g)).toHaveLength(4);
    expect(svg).toContain(">Standard atomic weight<");
    expect(svg).toContain(">55.845(2)<");
    expect(svg).toContain("Check ✓ 2,3,4 (see References)");
    const ys = [...svg.matchAll(/<rect x="[\d.]+" y="([\d.]+)"/g)].map((m) => Number(m[1]));
    expect(new Set(ys.slice(0, 3)).size).toBe(1);
    expect(ys[3]).toBeGreaterThan(ys[0]);
  });

  it("shrinks long values to fit", () => {
    expect(fitFontSize("3", 190, 22)).toBe(22);
    expect(fitFontSize("1s² 2s² 2p⁶ 3s² 3p⁶ 3d⁶ 4s² and more", 190, 22)).toBeLessThan(22);
  });
});

describe("3D targets", () => {
  it("pairs each stereo drawing with its isomer's frame", () => {
    const targets = spinTargets(run("stereo-dibromobutane").result);
    expect(targets.map((t) => [t.title, t.frame.comment])).toEqual([
      ["#1 · meso", "#1 · meso · (2R,3S)"],
      ["#2 · enantiomer of #3", "#2 · enantiomer of #3 · (2R,3R)"],
      ["#3 · enantiomer of #2", "#3 · enantiomer of #2 · (2S,3S)"],
    ]);
    expect(targets[0].key).toMatch(/isomer-01\.svg$/);
    expect(targets[0].note).toBe("(2R,3S)");
  });

  it("uses the structure itself when there are no drawings", () => {
    const targets = spinTargets(run("xyz-water").result);
    expect(targets).toHaveLength(1);
    expect(targets[0].key).toBe("structure:0");
    expect(targets[0].drawing).toBeUndefined();
  });

  it("does not confuse #1 with #10", () => {
    const frames = [{ symbols: ["H"], coords: [[0, 0, 0]], comment: "#10 · x", numbers: [], marks: [] }];
    expect(frameForDrawing(frames as never, "#1 · y")).toBeUndefined();
  });

  it("writes standard XYZ for csk", () => {
    const frame = spinTargets(run("xyz-water").result)[0].frame;
    const lines = xyzText(frame).trim().split("\n");
    expect(lines[0]).toBe("3");
    expect(lines[2]).toMatch(/^O -?\d+\.\d{6} /);
  });
});

describe("card files", () => {
  it("get a new name every time (Raycast caches images by path)", () => {
    const dir = tempDir();
    const a = writeCard("<svg/>", "#1 · meso", dir);
    const b = writeCard("<svg/>", "#1 · meso", dir);
    expect(a).not.toBe(b);
    expect(a).toMatch(/-1-meso\.svg$/);
  });

  it("older than an hour are removed", () => {
    const dir = tempDir();
    const old = writeCard("<svg/>", "old", dir);
    utimesSync(old, new Date(0), new Date(0));
    pruneCards(dir);
    expect(existsSync(old)).toBe(false);
    expect(readdirSync(dir)).toHaveLength(0);
    expect(join(dir, "x")).toBeTruthy();
  });
});
