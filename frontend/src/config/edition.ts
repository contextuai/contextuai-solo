/**
 * SPEC-33: ContextuAI Lite ("Vesper") & Solo Edition Configuration
 *
 * Controls dual-target branding, navigation, and runtime graduation from
 * Lite ("Vesper") into full ContextuAI Solo without reinstalling or
 * re-downloading local GGUF models.
 */
import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/transport";

export type AppEdition = "lite" | "solo";

export const EDITION_STORAGE_KEY = "contextuai.edition.unlocked";

export const LITE_BRAND = {
  appName: "Vesper",
  fullTitle: "Vesper by ContextuAI",
  tagline: "Quiet, sovereign intelligence on your metal.",
  edition: "lite" as const,
};

export const SOLO_BRAND = {
  appName: "ContextuAI Solo",
  fullTitle: "ContextuAI Solo",
  tagline: "Your Autonomous AI Workforce on Desktop.",
  edition: "solo" as const,
};

let _cachedBackendEdition: AppEdition | null = null;

export function getActiveEdition(): AppEdition {
  try {
    if (typeof window !== "undefined") {
      const stored = window.localStorage.getItem(EDITION_STORAGE_KEY);
      if (stored === "solo" || stored === "lite") {
        return stored;
      }
    }
  } catch {
    // ignore storage errors
  }

  if (_cachedBackendEdition) {
    return _cachedBackendEdition;
  }

  const envMap = (import.meta as unknown as { env?: Record<string, string> }).env;
  const buildEdition = (
    envMap?.VITE_APP_EDITION ||
    envMap?.VITE_EDITION ||
    "lite"
  )
    .toLowerCase()
    .trim();

  return buildEdition === "lite" ? "lite" : "solo";
}

export function isLiteEdition(): boolean {
  return getActiveEdition() === "lite";
}

export function getBrandConfig() {
  return isLiteEdition() ? LITE_BRAND : SOLO_BRAND;
}

export interface UnlockSoloResponse {
  edition: AppEdition;
  unlocked: boolean;
  agents_seeded: number;
  blueprints_seeded: number;
}

function broadcastEditionChange(next: AppEdition) {
  _cachedBackendEdition = next;
  try {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(EDITION_STORAGE_KEY, next);
      window.dispatchEvent(new CustomEvent("contextuai:edition-changed", { detail: next }));
    }
  } catch {
    // ignore storage errors
  }
}

/**
 * Syncs frontend edition state with the backend `/api/v1/desktop/edition` endpoint.
 */
export async function syncEditionFromBackend(): Promise<AppEdition> {
  try {
    const { data } = await api.get<{ edition: AppEdition }>("/desktop/edition");
    if (data?.edition === "lite" || data?.edition === "solo") {
      broadcastEditionChange(data.edition);
      return data.edition;
    }
  } catch {
    // fallback to current active edition
  }
  return getActiveEdition();
}

/**
 * Switches the running Lite ("Vesper") instance to full ContextuAI Solo in-place:
 * 1. Calls backend `POST /api/v1/desktop/unlock-solo` to seed the 96+ agent library & blueprints.
 * 2. Persists `contextuai.edition.unlocked = "solo"` in localStorage and notifies all components.
 */
export async function unlockSoloEdition(): Promise<UnlockSoloResponse> {
  const { data } = await api.post<UnlockSoloResponse>("/desktop/unlock-solo");
  broadcastEditionChange("solo");
  return data;
}

/**
 * Switches the running instance to Lite ("Vesper") mode.
 */
export async function switchToLiteEdition(): Promise<void> {
  try {
    await api.post("/desktop/switch-lite");
  } catch {
    // even if backend hasn't reloaded yet, switch UI immediately
  }
  broadcastEditionChange("lite");
}

/**
 * Reactive hook for components that render differently in Vesper Lite vs Full Solo.
 */
export function useEdition() {
  const [edition, setEdition] = useState<AppEdition>(() => getActiveEdition());
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    let mounted = true;
    syncEditionFromBackend().then((backendEd) => {
      if (mounted) setEdition(backendEd);
    });

    const handler = (e: Event) => {
      const detail = (e as CustomEvent<AppEdition>).detail;
      if (detail === "lite" || detail === "solo") {
        setEdition(detail);
      } else {
        setEdition(getActiveEdition());
      }
    };
    window.addEventListener("contextuai:edition-changed", handler);
    return () => {
      mounted = false;
      window.removeEventListener("contextuai:edition-changed", handler);
    };
  }, []);

  const unlockSolo = useCallback(async () => {
    setSwitching(true);
    try {
      await unlockSoloEdition();
      setEdition("solo");
    } finally {
      setSwitching(false);
    }
  }, []);

  const switchToLite = useCallback(async () => {
    setSwitching(true);
    try {
      await switchToLiteEdition();
      setEdition("lite");
    } finally {
      setSwitching(false);
    }
  }, []);

  const isLite = edition === "lite";
  const brand = isLite ? LITE_BRAND : SOLO_BRAND;

  return {
    edition,
    isLite,
    brand,
    switching,
    unlockSolo,
    switchToLite,
  };
}
