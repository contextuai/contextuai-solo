import { Outlet } from "react-router-dom";
import { cn } from "@/lib/utils";
import DesktopSidebar from "./desktop-sidebar";
import DesktopSidebarCoder from "./desktop-sidebar-coder";
import { ModeToggle } from "@/components/shell/mode-toggle";
import { useMode } from "@/contexts/mode-context";

export function DesktopLayout() {
  const { mode } = useMode();

  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-[#242523]">
      {/* Top bar with centred mode toggle — sticky so it stays visible when
          inner pages (e.g. Coder project detail, terminal output) grow past
          the viewport. */}
      <div
        className={cn(
          "sticky top-0 z-30 flex items-center justify-center h-12 px-4",
          "bg-white dark:bg-neutral-900",
          "border-b border-neutral-200 dark:border-neutral-800"
        )}
      >
        <ModeToggle />
      </div>

      <div className="flex">
        {/* Cross-fade between sidebars on mode change */}
        <div className="relative">
          <div
            className={cn(
              "transition-opacity duration-150",
              mode === "solo" ? "opacity-100" : "opacity-0 pointer-events-none absolute inset-0"
            )}
            aria-hidden={mode !== "solo"}
          >
            {mode === "solo" && <DesktopSidebar />}
          </div>
          <div
            className={cn(
              "transition-opacity duration-150",
              mode === "coder" ? "opacity-100" : "opacity-0 pointer-events-none absolute inset-0"
            )}
            aria-hidden={mode !== "coder"}
          >
            {mode === "coder" && <DesktopSidebarCoder />}
          </div>
        </div>

        <main className="flex-1 transition-all duration-300">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
