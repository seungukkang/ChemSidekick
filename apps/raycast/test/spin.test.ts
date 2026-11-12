import { describe, expect, it } from "vitest";
import type { Frame, RunResponse } from "../src/lib/contract";
import { drawingsOf, frameForDrawing, spinTargets } from "../src/lib/spin";
import { fixture } from "./helpers";

const run = (name: string) => JSON.parse(fixture(name)) as RunResponse;

describe("3D targets", () => {
  it("pairs each stereo drawing with its isomer's frame", () => {
    const targets = spinTargets(run("stereo-dibromobutane").result);
    expect(targets.map((t) => [t.title, t.frame.comment])).toEqual([
      ["#1 · meso", "#1 · meso · (2R,3S)"],
      ["#2 · enantiomer of #3", "#2 · enantiomer of #3 · (2R,3R)"],
      ["#3 · enantiomer of #2", "#3 · enantiomer of #2 · (2S,3S)"],
    ]);
    expect(targets[0].key).toMatch(/isomer-01\.svg$/);
  });

  it("uses the structure itself when there are no drawings", () => {
    const r = run("xyz-water").result;
    expect(drawingsOf(r)).toEqual([]);
    const targets = spinTargets(r);
    expect(targets).toHaveLength(1);
    expect(targets[0].key).toBe("structure:0");
    expect(targets[0].drawing).toBeUndefined();
  });

  it("does not confuse #1 with #10", () => {
    const frames: Frame[] = [{ symbols: ["H"], coords: [[0, 0, 0]], comment: "#10 · x", numbers: [], marks: [] }];
    expect(frameForDrawing(frames, "#1 · y")).toBeUndefined();
    expect(frameForDrawing(frames, "#10 · y")).toBe(frames[0]);
  });
});
