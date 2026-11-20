import { Outlet } from "react-router-dom";
import { cn } from "@/lib/utils";
import DesktopSidebar from "./desktop-sidebar";
import DesktopSidebarCoder from "./desktop-sidebar-coder";
import { ModeToggle } from "@/components/shell/mode-toggle";
import { useMode } from "@/contexts/mode-context";
import { useEdition } from "@/config/edition";

export function DesktopLayout() {
  const { mode } = useMode();
  const { isLite } = useEdition();

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-neutral-50 dark:bg-neutral-950">
      {/* Top bar only in Full Solo mode for the Solo/Coder switcher — Vesper Lite
          keeps all utilities in the sidebar so pages start cleanly at y = 0. */}
      {!isLite && (
        <div
          className={cn(
            "flex-shrink-0 flex items-center justify-between h-11 px-4 brand-topline",
            "bg-white dark:bg-neutral-900",
            "border-b border-neutral-200 dark:border-neutral-800"
          )}
        >
          <div className="w-48" />
          <ModeToggle />
          <div className="w-48" />
        </div>
      )}

      <div className="flex flex-1 min-h-0">
        <div className="relative h-full">
          <div
            className={cn(
              "h-full transition-opacity duration-150",
              isLite || mode === "solo"
                ? "opacity-100"
                : "opacity-0 pointer-events-none absolute inset-0"
            )}
            aria-hidden={!isLite && mode !== "solo"}
          >
            {(isLite || mode === "solo") && <DesktopSidebar />}
          </div>
          {!isLite && (
            <div
              className={cn(
                "h-full transition-opacity duration-150",
                mode === "coder"
                  ? "opacity-100"
                  : "opacity-0 pointer-events-none absolute inset-0"
              )}
              aria-hidden={mode !== "coder"}
            >
              {mode === "coder" && <DesktopSidebarCoder />}
            </div>
          )}
        </div>

        <main className="flex-1 overflow-y-auto transition-all duration-300 app-ambient">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
