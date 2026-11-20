import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { getModels } from "@/lib/api/models-client";

export type AiMode = "local" | "cloud";

interface AiModeContextValue {
  aiMode: AiMode;
  setAiMode: (mode: AiMode) => void;
}

const AiModeContext = createContext<AiModeContextValue | null>(null);

const STORAGE_KEY = "contextuai-solo-ai-mode";

function isLocalModel(m: { provider?: string; id: string }): boolean {
  return (
    (m.provider || "").toLowerCase() === "local" ||
    m.id.startsWith("local:") ||
    m.id.startsWith("local-")
  );
}

export function AiModeProvider({ children }: { children: ReactNode }) {
  const [aiMode, setAiModeState] = useState<AiMode>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "local" || stored === "cloud") return stored;
    } catch {}
    return "cloud"; // temporary default, will resolve in useEffect
  });
  const [, setInitialized] = useState(false);

  // On mount: detect usable local models and recover profiles stuck on "cloud" with 0 cloud keys
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "local") {
      setInitialized(true);
      return;
    }
    getModels()
      .then((models) => {
        const hasEnabledLocal = models.some((m) => m.enabled && isLocalModel(m));
        const hasEnabledCloud = models.some((m) => m.enabled && !isLocalModel(m));
        if (!stored || stored !== "cloud") {
          const mode: AiMode = hasEnabledLocal ? "local" : "cloud";
          setAiModeState(mode);
          localStorage.setItem(STORAGE_KEY, mode);
        } else if (!hasEnabledCloud && hasEnabledLocal) {
          setAiModeState("local");
          localStorage.setItem(STORAGE_KEY, "local");
        }
      })
      .catch(() => {
        // Keep current mode on error
      })
      .finally(() => setInitialized(true));
  }, []);

  const setAiMode = useCallback((mode: AiMode) => {
    setAiModeState(mode);
    localStorage.setItem(STORAGE_KEY, mode);
    // Sync preference to backend (fire-and-forget)
    import("@/lib/transport").then(({ api }) => {
      api.put("/models/preference", { ai_mode: mode }).catch(() => {});
    });
  }, []);

  return (
    <AiModeContext.Provider value={{ aiMode, setAiMode }}>
      {children}
    </AiModeContext.Provider>
  );
}

export function useAiMode(): AiModeContextValue {
  const ctx = useContext(AiModeContext);
  if (!ctx) throw new Error("useAiMode must be used within AiModeProvider");
  return ctx;
}
