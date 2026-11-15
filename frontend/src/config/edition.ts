/**
 * SPEC-33: ContextuAI Lite ("Vesper") & Solo Edition Configuration
 *
 * Controls dual-target branding, navigation, and runtime graduation from
 * Lite ("Vesper") into full ContextuAI Solo without reinstalling or
 * re-downloading local GGUF models.
 */
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

export function getActiveEdition(): AppEdition {
  try {
    if (typeof window !== "undefined") {
      const unlocked = window.localStorage.getItem(EDITION_STORAGE_KEY);
      if (unlocked === "solo" || unlocked === "lite") {
        return unlocked;
      }
    }
  } catch {
    // ignore storage errors
  }

  const buildEdition = (
    (import.meta as unknown as { env?: Record<string, string> }).env
      ?.VITE_APP_EDITION || "solo"
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

/**
 * Switches the running Lite ("Vesper") instance to full ContextuAI Solo in-place:
 * 1. Calls backend `POST /api/v1/desktop/unlock-solo` to seed the 96+ agent library & blueprints.
 * 2. Persists `contextuai.edition.unlocked = "solo"` in localStorage.
 */
export async function unlockSoloEdition(): Promise<UnlockSoloResponse> {
  const { data } = await api.post<UnlockSoloResponse>("/desktop/unlock-solo");
  try {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(EDITION_STORAGE_KEY, "solo");
      window.dispatchEvent(new CustomEvent("contextuai:edition-changed", { detail: "solo" }));
    }
  } catch {
    // ignore storage errors
  }
  return data;
}
