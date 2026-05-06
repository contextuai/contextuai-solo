/**
 * Thin wrapper around `@tauri-apps/plugin-dialog` so other modules can call a
 * native folder picker from Tauri builds without touching Tauri APIs directly.
 * In dev mode (or any non-Tauri context) `pickFolder()` resolves to `null` so
 * the caller can fall back to a free-text path input.
 */
import { open } from "@tauri-apps/plugin-dialog";

export function isTauri(): boolean {
  return Boolean((window as unknown as { __TAURI__?: unknown }).__TAURI__);
}

/** Open a native folder picker. Returns the selected absolute path or null. */
export async function pickFolder(): Promise<string | null> {
  if (!isTauri()) return null;
  const result = await open({ directory: true, multiple: false });
  if (!result) return null;
  return Array.isArray(result) ? result[0] ?? null : (result as string);
}

/**
 * Reveal `path` in the OS file explorer (Finder / Explorer / xdg-open). On
 * non-Tauri (dev) builds this is a no-op that resolves to `false` so callers
 * can branch on the result. Errors from the shell plugin are swallowed and
 * surface as `false`.
 */
export async function openFolder(path: string): Promise<boolean> {
  if (!isTauri()) return false;
  try {
    const { open: shellOpen } = await import("@tauri-apps/plugin-shell");
    await shellOpen(path);
    return true;
  } catch {
    return false;
  }
}
