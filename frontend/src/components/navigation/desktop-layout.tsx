import { Outlet } from "react-router-dom";
import { cn } from "@/lib/utils";
import DesktopSidebar from "./desktop-sidebar";
import DesktopSidebarCoder from "./desktop-sidebar-coder";
import { ModeToggle } from "@/components/shell/mode-toggle";
import { CommandPalette } from "@/components/shell/command-palette";
import { PrivacyShield } from "@/components/privacy/privacy-shield";
import { ThemeQuickPicker } from "@/components/shell/theme-quick-picker";
import { useMode } from "@/contexts/mode-context";
import { useEdition } from "@/config/edition";

export function DesktopLayout() {
  const { mode } = useMode();
  const { isLite } = useEdition();

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-neutral-50 dark:bg-neutral-950">
      {/* Top bar with the mode toggle (or Vesper Lite badge) + Command Palette + Glass-Box Privacy Shield */}
      <div
        className={cn(
          "flex-shrink-0 flex items-center justify-between h-12 px-4 brand-topline",
          "bg-white dark:bg-neutral-900",
          "border-b border-neutral-200 dark:border-neutral-800"
        )}
      >
        <div className="w-64 flex items-center gap-2">
          {isLite && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium bg-primary-500/10 text-primary-600 dark:text-primary-400 border border-primary-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-primary-500 animate-pulse" />
              Vesper · Sovereign GGUF Engine
            </span>
          )}
        </div>
        {isLite ? (
          <div className="hidden md:block text-xs font-medium text-neutral-500 dark:text-neutral-400">
            Quiet, sovereign intelligence on your metal
          </div>
        ) : (
          <ModeToggle />
        )}
        <div className="w-64 flex items-center justify-end gap-2">
          <CommandPalette />
          <ThemeQuickPicker />
          <PrivacyShield />
        </div>
      </div>

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
