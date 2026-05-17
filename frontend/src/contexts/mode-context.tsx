import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type AppMode = "solo" | "coder";

interface ModeContextValue {
  mode: AppMode;
  setMode: (next: AppMode) => void;
}

const ModeContext = createContext<ModeContextValue | null>(null);

const STORAGE_KEY = "solo.app.mode";
const MODE_CHANGE_EVENT = "solo:app-mode-change";

function readStoredMode(): AppMode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "solo" || stored === "coder") return stored;
  } catch {
    /* ignore */
  }
  return "solo";
}

function titleFor(mode: AppMode): string {
  return mode === "coder" ? "Solo Coder" : "ContextuAI Solo";
}

export function ModeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<AppMode>(() => readStoredMode());

  // Apply initial title once on mount.
  useEffect(() => {
    document.title = titleFor(mode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setMode = useCallback((next: AppMode) => {
    setModeState((prev) => {
      if (prev === next) return prev;
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        /* ignore */
      }
      document.title = titleFor(next);
      try {
        window.dispatchEvent(
          new CustomEvent<AppMode>(MODE_CHANGE_EVENT, { detail: next })
        );
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  return (
    <ModeContext.Provider value={{ mode, setMode }}>
      {children}
    </ModeContext.Provider>
  );
}

export function useMode(): ModeContextValue {
  const ctx = useContext(ModeContext);
  if (!ctx) throw new Error("useMode must be used within ModeProvider");
  return ctx;
}

export const MODE_STORAGE_KEY = STORAGE_KEY;
export const MODE_CHANGE_EVENT_NAME = MODE_CHANGE_EVENT;
