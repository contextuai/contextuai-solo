import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";

type BackendStatus = "checking" | "ready" | "unavailable";

interface BackendStatusContextValue {
  status: BackendStatus;
  retry: () => void;
}

const BackendStatusContext = createContext<BackendStatusContextValue>({
  status: "checking",
  retry: () => {},
});

export function useBackendStatus() {
  return useContext(BackendStatusContext);
}

const HEALTH_URL = "http://127.0.0.1:18741/health";

export function BackendStatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<BackendStatus>("checking");

  const checkHealth = useCallback(async () => {
    setStatus("checking");
    for (let attempt = 0; attempt < 30; attempt++) {
      try {
        const resp = await fetch(HEALTH_URL);
        if (resp.ok) {
          setStatus("ready");
          return;
        }
      } catch {
        // backend not up yet
      }
      await new Promise((r) => setTimeout(r, 1000));
    }
    setStatus("unavailable");
  }, []);

  useEffect(() => {
    checkHealth();
  }, [checkHealth]);

  return (
    <BackendStatusContext.Provider value={{ status, retry: checkHealth }}>
      {children}
    </BackendStatusContext.Provider>
  );
}
