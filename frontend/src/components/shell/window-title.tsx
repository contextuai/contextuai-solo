import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useMode } from "@/contexts/mode-context";
import { useEdition } from "@/config/edition";

/**
 * Effect-only component that keeps `document.title` in sync with the active
 * app edition and mode.
 */
export function WindowTitle() {
  const { mode } = useMode();
  const { isLite } = useEdition();
  const location = useLocation();

  useEffect(() => {
    if (isLite) {
      document.title = "Vesper by ContextuAI";
    } else {
      document.title = mode === "coder" ? "Vesper Coder" : "Vesper Solo";
    }
  }, [isLite, mode, location.pathname]);

  return null;
}

export default WindowTitle;
