/**
 * Vesper Advanced Mode hook.
 *
 * Persists user preference in `localStorage` under `vesper.advanced_mode`
 * (default `false`) and synchronizes across components and tabs via the
 * `vesper:advanced-mode-changed` CustomEvent and `storage` listener.
 */
import { useState, useEffect, useCallback } from "react";

export const ADVANCED_MODE_KEY = "vesper.advanced_mode";
export const ADVANCED_MODE_EVENT = "vesper:advanced-mode-changed";

export function getAdvancedMode(): boolean {
  try {
    if (typeof window !== "undefined") {
      return window.localStorage.getItem(ADVANCED_MODE_KEY) === "true";
    }
  } catch {
    // ignore storage errors
  }
  return false;
}

export function setStoredAdvancedMode(enabled: boolean): void {
  try {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ADVANCED_MODE_KEY, enabled ? "true" : "false");
      window.dispatchEvent(
        new CustomEvent<boolean>(ADVANCED_MODE_EVENT, { detail: enabled })
      );
    }
  } catch {
    // ignore storage errors
  }
}

export function useAdvancedMode() {
  const [advancedMode, setState] = useState<boolean>(() => getAdvancedMode());

  useEffect(() => {
    const onCustomEvent = (e: Event) => {
      const detail = (e as CustomEvent<boolean>).detail;
      if (typeof detail === "boolean") {
        setState(detail);
      } else {
        setState(getAdvancedMode());
      }
    };

    const onStorage = (e: StorageEvent) => {
      if (e.key === ADVANCED_MODE_KEY) {
        setState(e.newValue === "true");
      }
    };

    window.addEventListener(ADVANCED_MODE_EVENT, onCustomEvent);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(ADVANCED_MODE_EVENT, onCustomEvent);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const setAdvancedMode = useCallback((next: boolean) => {
    setState(next);
    setStoredAdvancedMode(next);
  }, []);

  const toggleAdvancedMode = useCallback(() => {
    setAdvancedMode(!getAdvancedMode());
  }, [setAdvancedMode]);

  return {
    advancedMode,
    setAdvancedMode,
    toggleAdvancedMode,
  };
}
