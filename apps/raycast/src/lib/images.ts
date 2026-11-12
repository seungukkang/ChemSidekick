// Image files the extension draws itself (e.g. the periodic table). Every file
// gets a new name, because Raycast caches images by path; files older than an
// hour are removed.
import { mkdirSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const MAX_AGE_MS = 60 * 60 * 1000;
let counter = 0;

export function imagesDir(base = tmpdir()): string {
  const dir = join(base, "chemsidekick-raycast-images");
  mkdirSync(dir, { recursive: true });
  return dir;
}

export function writeImage(svg: string, label: string, dir = imagesDir()): string {
  pruneImages(dir);
  counter += 1;
  const safe = label.replace(/[^A-Za-z0-9-]+/g, "-").slice(0, 40);
  const path = join(dir, `${Date.now()}-${process.pid}-${counter}-${safe}.svg`);
  writeFileSync(path, svg, "utf-8");
  return path;
}

export function pruneImages(dir: string, now = Date.now()): void {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    try {
      if (now - statSync(path).mtimeMs > MAX_AGE_MS) rmSync(path, { force: true });
    } catch {
      // removed by another view
    }
  }
}
