import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useMode } from "@/contexts/mode-context";

/**
 * Effect-only component that keeps `document.title` in sync with the active
 * app mode. Re-runs on route changes so the title is consistent after
 * client-side navigations that may have set their own title.
 */
export function WindowTitle() {
  const { mode } = useMode();
  const location = useLocation();

  useEffect(() => {
    document.title = mode === "coder" ? "Solo Coder" : "ContextuAI Solo";
  }, [mode, location.pathname]);

  return null;
}

export default WindowTitle;
