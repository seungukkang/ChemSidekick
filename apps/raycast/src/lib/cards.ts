// Cards drawn as SVG images, because Detail markdown cannot center text, use
// small gray text, or draw borders:
// - drawing cards: a 2D drawing with its caption (same layout as the 3D GIF
//   card that `csk run spin` makes; keep in sync with src/chemsidekick/core/spin.py)
// - highlight cards: key values (e.g. "Stereoisomers 3"), three per row
// Card files get new names every time, because Raycast caches images by path.
import { mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { Artifact, Frame, Highlight, ToolResult } from "./contract";

// Drawing card layout (px), as in core/spin.py.
export const CARD_W = 320;
export const CARD_H = 296;
const PAD = 10;
const IMG_W = 300;
const IMG_H = 240;
const TITLE_Y = 270;
const NOTE_Y = 287;
const CARD_BORDER = "#c8c8c8";
const TEXT_COLOR = "#222222";
const NOTE_COLOR = "#8a8a8a";
const FONT = "Helvetica, Arial, sans-serif";
// macOS's SVG renderer (Raycast) ignores font-weight="bold" but honors the number 700.
const BOLD = `font-family="${FONT}" font-weight="700"`;

// Highlight cards
export const HIGHLIGHTS_PER_ROW = 3;
export const STRIP_W = 660;
const H_GAP = 12;
const H_CARD_H = 78;

export function escapeXml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

// The drawing's own <svg> becomes a nested <svg> placed in the card's drawing area.
export function drawingCardSvg(drawingSvg: string, title: string, note: string): string {
  const open = drawingSvg.match(/<svg\b[^>]*>/);
  const close = drawingSvg.lastIndexOf("</svg>");
  if (!open || open.index === undefined || close < 0) throw new Error("not an SVG drawing");
  const viewBox = open[0].match(/viewBox=['"]([^'"]+)['"]/)?.[1] ?? `0 0 ${IMG_W} ${IMG_H}`;
  const inner = drawingSvg.slice(open.index + open[0].length, close);
  const lines = [
    `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:rdkit="http://www.rdkit.org/xml" width="${CARD_W}" height="${CARD_H}" viewBox="0 0 ${CARD_W} ${CARD_H}">`,
    `<rect x="0.75" y="0.75" width="${CARD_W - 1.5}" height="${CARD_H - 1.5}" rx="12" ry="12" fill="#ffffff" stroke="${CARD_BORDER}" stroke-width="1.5"/>`,
    `<svg x="${PAD}" y="${PAD}" width="${IMG_W}" height="${IMG_H}" viewBox="${viewBox}">${inner}</svg>`,
  ];
  if (title) {
    lines.push(
      `<text x="${CARD_W / 2}" y="${TITLE_Y}" text-anchor="middle" ${BOLD} font-size="14" fill="${TEXT_COLOR}">${escapeXml(title)}</text>`,
    );
  }
  if (note) {
    lines.push(
      `<text x="${CARD_W / 2}" y="${NOTE_Y}" text-anchor="middle" font-family="${FONT}" font-size="11" fill="${NOTE_COLOR}">${escapeXml(note)}</text>`,
    );
  }
  lines.push("</svg>");
  return lines.join("\n");
}

// Largest font size (up to `max`) at which `text` fits in `width` px, roughly.
export function fitFontSize(text: string, width: number, max: number, min = 9): number {
  const perChar = 0.6; // average character width in em (Helvetica, bold digits/letters)
  return Math.max(min, Math.min(max, Math.floor(width / (Math.max(1, text.length) * perChar))));
}

export function highlightCardsSvg(highlights: Highlight[]): string {
  const cardW = (STRIP_W - H_GAP * (HIGHLIGHTS_PER_ROW - 1)) / HIGHLIGHTS_PER_ROW;
  const rows = Math.ceil(highlights.length / HIGHLIGHTS_PER_ROW);
  const height = rows * H_CARD_H + (rows - 1) * H_GAP + 2;
  const parts = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${STRIP_W}" height="${height}" viewBox="0 0 ${STRIP_W} ${height}">`,
  ];
  highlights.forEach((h, i) => {
    const x = (i % HIGHLIGHTS_PER_ROW) * (cardW + H_GAP) + 1;
    const y = Math.floor(i / HIGHLIGHTS_PER_ROW) * (H_CARD_H + H_GAP) + 1;
    const cx = x + cardW / 2;
    const valueSize = fitFontSize(h.value, cardW - 20, 22);
    parts.push(
      `<rect x="${x}" y="${y}" width="${cardW - 2}" height="${H_CARD_H - 2}" rx="10" ry="10" fill="#ffffff" stroke="${CARD_BORDER}" stroke-width="1.5"/>`,
      `<text x="${cx}" y="${y + 20}" text-anchor="middle" font-family="${FONT}" font-size="${fitFontSize(h.label, cardW - 20, 11)}" fill="${NOTE_COLOR}">${escapeXml(h.label)}</text>`,
      `<text x="${cx}" y="${y + 48}" text-anchor="middle" ${BOLD} font-size="${valueSize}" fill="${TEXT_COLOR}">${escapeXml(h.value)}</text>`,
    );
    if (h.note) {
      parts.push(
        `<text x="${cx}" y="${y + 66}" text-anchor="middle" font-family="${FONT}" font-size="${fitFontSize(h.note, cardW - 20, 10, 7)}" fill="${NOTE_COLOR}">${escapeXml(h.note)}</text>`,
      );
    }
  });
  parts.push("</svg>");
  return parts.join("\n");
}

// --- Files ----------------------------------------------------------------------

const MAX_AGE_MS = 60 * 60 * 1000;
let counter = 0;

export function cardsDir(base = tmpdir()): string {
  const dir = join(base, "chemsidekick-raycast-cards");
  mkdirSync(dir, { recursive: true });
  return dir;
}

// Write an SVG under a fresh name; old cards (> 1 hour) are removed.
export function writeCard(svg: string, label: string, dir = cardsDir()): string {
  pruneCards(dir);
  counter += 1;
  const safe = label.replace(/[^A-Za-z0-9-]+/g, "-").slice(0, 40);
  const path = join(dir, `${Date.now()}-${process.pid}-${counter}-${safe}.svg`);
  writeFileSync(path, svg, "utf-8");
  return path;
}

export function pruneCards(dir: string, now = Date.now()): void {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    try {
      if (now - statSync(path).mtimeMs > MAX_AGE_MS) rmSync(path, { force: true });
    } catch {
      // removed by another view
    }
  }
}

// --- 3D -------------------------------------------------------------------------

// The structure frame that belongs to a drawing: stereo titles both "#3 · ...".
export function frameForDrawing(frames: Frame[], drawingTitle: string): Frame | undefined {
  const id = drawingTitle.match(/^#\d+\b/)?.[0];
  if (!id) return undefined;
  return frames.find((f) => f.comment === id || f.comment.startsWith(`${id} `));
}

export function xyzText(frame: Frame): string {
  const atoms = frame.symbols.map((s, i) => {
    const [x, y, z] = frame.coords[i];
    return `${s} ${x.toFixed(6)} ${y.toFixed(6)} ${z.toFixed(6)}`;
  });
  return [String(frame.symbols.length), frame.comment, ...atoms].join("\n") + "\n";
}

// What can be shown as a rotating 3D card: each drawing that has a matching
// structure frame (stereo isomers), or, for results without drawings (xyz),
// the structure itself. `key` is the drawing path, or "structure:<n>".
export interface SpinTarget {
  key: string;
  frame: Frame;
  title: string;
  note: string;
  drawing?: Artifact;
}

export function spinTargets(result: ToolResult): SpinTarget[] {
  const frames = result.structures.flatMap((s) => s.frames);
  const drawings = result.artifacts.filter((a) => a.kind === "svg" || a.kind === "png");
  if (drawings.length) {
    return drawings.flatMap((d) => {
      const frame = frameForDrawing(frames, d.title);
      return frame ? [{ key: d.path, frame, title: d.title, note: d.note, drawing: d }] : [];
    });
  }
  return result.structures.map((s, i) => ({
    key: `structure:${i}`,
    frame: s.frames[s.start_frame] ?? s.frames[0],
    title: s.title,
    note: "",
  }));
}

export interface PreparedCards {
  cards: Record<string, string>; // drawing path -> 2D card SVG
  highlights?: string; // highlight cards SVG
  targets: SpinTarget[];
}

// Write the card images for one result (read the drawings, wrap them in cards).
// A drawing that cannot be read is shown as it is.
export function prepareCards(result: ToolResult, dir = cardsDir()): PreparedCards {
  const cards: Record<string, string> = {};
  for (const d of result.artifacts.filter((a) => a.kind === "svg")) {
    try {
      cards[d.path] = writeCard(drawingCardSvg(readFileSync(d.path, "utf-8"), d.title, d.note), d.title, dir);
    } catch {
      // keep the plain drawing
    }
  }
  const highlights = result.highlights.length
    ? writeCard(highlightCardsSvg(result.highlights), "highlights", dir)
    : undefined;
  return { cards, highlights, targets: spinTargets(result) };
}
