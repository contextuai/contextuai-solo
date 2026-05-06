import { useEffect } from "react";

export interface KeyboardShortcutBinding {
  /**
   * Combo string in the form `mod+shift+m`.
   * Tokens (case-insensitive): `mod` (Cmd on macOS, Ctrl elsewhere),
   * `ctrl`, `meta`, `cmd`, `alt`, `option`, `shift`, plus a single key
   * (e.g. `m`, `Enter`, `ArrowUp`).
   */
  combo: string;
  handler: (e: KeyboardEvent) => void;
}

interface ParsedCombo {
  mod: boolean;
  ctrl: boolean;
  meta: boolean;
  alt: boolean;
  shift: boolean;
  key: string;
}

function parseCombo(combo: string): ParsedCombo {
  const parts = combo
    .split("+")
    .map((p) => p.trim().toLowerCase())
    .filter(Boolean);

  const result: ParsedCombo = {
    mod: false,
    ctrl: false,
    meta: false,
    alt: false,
    shift: false,
    key: "",
  };

  for (const part of parts) {
    switch (part) {
      case "mod":
        result.mod = true;
        break;
      case "ctrl":
      case "control":
        result.ctrl = true;
        break;
      case "meta":
      case "cmd":
      case "command":
        result.meta = true;
        break;
      case "alt":
      case "option":
        result.alt = true;
        break;
      case "shift":
        result.shift = true;
        break;
      default:
        result.key = part;
    }
  }

  return result;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!target || !(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return false;
}

function matches(parsed: ParsedCombo, e: KeyboardEvent): boolean {
  if (parsed.mod) {
    if (!(e.metaKey || e.ctrlKey)) return false;
  } else {
    if (parsed.ctrl !== e.ctrlKey) return false;
    if (parsed.meta !== e.metaKey) return false;
  }
  if (parsed.alt !== e.altKey) return false;
  if (parsed.shift !== e.shiftKey) return false;
  if (!parsed.key) return false;
  return e.key.toLowerCase() === parsed.key;
}

/**
 * Registers global keyboard shortcuts on `window`.
 * Shortcuts do not fire when an input/textarea/contenteditable is focused.
 */
export function useKeyboardShortcuts(bindings: KeyboardShortcutBinding[]): void {
  useEffect(() => {
    if (!bindings.length) return;
    const parsed = bindings.map((b) => ({
      parsed: parseCombo(b.combo),
      handler: b.handler,
    }));

    const onKeyDown = (e: KeyboardEvent) => {
      if (isEditableTarget(e.target)) return;
      for (const { parsed: p, handler } of parsed) {
        if (matches(p, e)) {
          handler(e);
          break;
        }
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // bindings is a fresh array each render; consumers should memoize handlers
    // if they need stable identity. We re-bind cheaply here.
  }, [bindings]);
}
