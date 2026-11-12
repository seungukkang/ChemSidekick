// Which drawings can switch to a rotating 3D view (`csk gif`), and with which
// structure frame. Pure, so it can be tested.
import type { Artifact, Frame, ToolResult } from "./contract";

// `key` is the drawing path, or "structure:<n>" for a result without drawings (xyz).
export interface SpinTarget {
  key: string;
  frame: Frame;
  title: string;
  drawing?: Artifact;
}

// The structure frame that belongs to a drawing: stereo titles both "#3 · ...".
export function frameForDrawing(frames: Frame[], drawingTitle: string): Frame | undefined {
  const id = drawingTitle.match(/^#\d+\b/)?.[0];
  if (!id) return undefined;
  return frames.find((f) => f.comment === id || f.comment.startsWith(`${id} `));
}

export function drawingsOf(result: ToolResult): Artifact[] {
  return result.artifacts.filter((a) => a.kind === "svg" || a.kind === "png");
}

export function spinTargets(result: ToolResult): SpinTarget[] {
  const frames = result.structures.flatMap((s) => s.frames);
  const drawings = drawingsOf(result);
  if (drawings.length) {
    return drawings.flatMap((d) => {
      const frame = frameForDrawing(frames, d.title);
      return frame ? [{ key: d.path, frame, title: d.title, drawing: d }] : [];
    });
  }
  return result.structures.map((s, i) => ({
    key: `structure:${i}`,
    frame: s.frames[s.start_frame] ?? s.frames[0],
    title: s.title,
  }));
}
