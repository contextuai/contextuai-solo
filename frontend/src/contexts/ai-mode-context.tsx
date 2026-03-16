import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { getModels } from "@/lib/api/models-client";

export type AiMode = "local" | "cloud";

interface AiModeContextValue {
  aiMode: AiMode;
  setAiMode: (mode: AiMode) => void;
}

const AiModeContext = createContext<AiModeContextValue | null>(null);

const STORAGE_KEY = "contextuai-solo-ai-mode";

export function AiModeProvider({ children }: { children: ReactNode }) {
  const [aiMode, setAiModeState] = useState<AiMode>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "local" || stored === "cloud") return stored;
    } catch {}
    return "cloud"; // temporary default, will resolve in useEffect
  });
  const [, setInitialized] = useState(false);

  // On mount: if no stored preference, check if any local model exists
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "local" || stored === "cloud") {
      setInitialized(true);
      return;
    }
    // Auto-detect: default to "local" if any local model is available
    getModels()
      .then((models) => {
        const hasLocal = models.some(
          (m) => m.provider === "local" || m.id.startsWith("local-")
        );
        const mode: AiMode = hasLocal ? "local" : "cloud";
        setAiModeState(mode);
        localStorage.setItem(STORAGE_KEY, mode);
      })
      .catch(() => {
        // Keep cloud default on error
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
