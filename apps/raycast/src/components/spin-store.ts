// Which drawings show their rotating 3D view instead, shared by every view of a
// result (a pushed view does not get its parent's state updates).
// GIFs are made on demand with `csk gif` and kept for the session.
import { showToast, Toast } from "@raycast/api";
import { useSyncExternalStore } from "react";
import { getTransport } from "../connection";
import type { SpinTarget } from "../lib/spin";

const gifs = new Map<string, string>(); // target key -> GIF path
const shown = new Set<string>();
const loading = new Set<string>();
const listeners = new Set<() => void>();
let version = 0;

function changed() {
  version += 1;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

// The combined card (2D drawing + rotating 3D) is kept under its own key.
export function combinedKey(key: string): string {
  return `${key}|with-2d`;
}

async function makeGif(target: SpinTarget, beside2D = false) {
  const key = beside2D ? combinedKey(target.key) : target.key;
  loading.add(key);
  changed();
  const toast = await showToast({ style: Toast.Style.Animated, title: "Making the 3D view…" });
  try {
    const { symbols, coords, comment, marks } = target.frame;
    const response = await getTransport().gif({
      frame: { symbols, coords, comment, marks },
      ...(beside2D ? { beside_2d: true } : {}),
    });
    if (!response.ok) throw new Error(response.error.message);
    gifs.set(key, response.path);
    await toast.hide();
  } catch (e) {
    shown.delete(key);
    toast.style = Toast.Style.Failure;
    toast.title = "Could not make the 3D view";
    toast.message = e instanceof Error ? e.message : String(e);
  } finally {
    loading.delete(key);
    changed();
  }
}

// Make the combined card (2D drawing + rotating 3D, one GIF) if not made yet,
// without switching anything: for a page that shows both from the start (xyz).
export function ensureCombined(target: SpinTarget) {
  const key = combinedKey(target.key);
  if (!gifs.has(key) && !loading.has(key)) void makeGif(target, true);
}

export function toggle3D(target: SpinTarget) {
  if (shown.has(target.key)) {
    shown.delete(target.key);
    changed();
    return;
  }
  shown.add(target.key);
  changed();
  if (!gifs.has(target.key) && !loading.has(target.key)) void makeGif(target);
}

export interface SpinState {
  is3D(key: string): boolean; // switched to 3D (the GIF may still be in the making)
  gif(key: string): string | undefined; // GIF to show now, if switched to 3D and ready
  made(key: string): string | undefined; // the GIF if it exists, switched or not
}

export function useSpinState(): SpinState {
  useSyncExternalStore(subscribe, () => version);
  return {
    is3D: (key) => shown.has(key),
    gif: (key) => (shown.has(key) ? gifs.get(key) : undefined),
    made: (key) => gifs.get(key),
  };
}
