import { Outlet } from "react-router-dom";
import { cn } from "@/lib/utils";
import DesktopSidebar from "./desktop-sidebar";
import DesktopSidebarCoder from "./desktop-sidebar-coder";
import { ModeToggle } from "@/components/shell/mode-toggle";
import { useMode } from "@/contexts/mode-context";

export function DesktopLayout() {
  const { mode } = useMode();

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-neutral-50 dark:bg-[#242523]">
      {/* Top bar with the mode toggle. Lives outside the scroll container so
          inner pages never push it out of view. */}
      <div
        className={cn(
          "flex-shrink-0 flex items-center justify-center h-12 px-4",
          "bg-white dark:bg-neutral-900",
          "border-b border-neutral-200 dark:border-neutral-800"
        )}
      >
        <ModeToggle />
      </div>

      <div className="flex flex-1 min-h-0">
        {/* Cross-fade between sidebars on mode change. Explicit `h-full` on
            the wrapper chain so the sidebar's `h-full` resolves against the
            flex row's height — without it the chain breaks at the auto-height
            inner div and the sidebar collapses to its content height, leaving
            blank space below it on tall pages like Settings. */}
        <div className="relative h-full">
          <div
            className={cn(
              "h-full transition-opacity duration-150",
              mode === "solo" ? "opacity-100" : "opacity-0 pointer-events-none absolute inset-0"
            )}
            aria-hidden={mode !== "solo"}
          >
            {mode === "solo" && <DesktopSidebar />}
          </div>
          <div
            className={cn(
              "h-full transition-opacity duration-150",
              mode === "coder" ? "opacity-100" : "opacity-0 pointer-events-none absolute inset-0"
            )}
            aria-hidden={mode !== "coder"}
          >
            {mode === "coder" && <DesktopSidebarCoder />}
          </div>
        </div>

        <main className="flex-1 overflow-y-auto transition-all duration-300">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
