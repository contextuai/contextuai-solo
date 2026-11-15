/**
 * Top-bar quick theme switcher: color theme swatches + Light/Dark/System.
 * Makes the brand theme one click away instead of buried in Settings.
 */
import { useEffect, useRef, useState } from "react";
import { Check, Monitor, Moon, Palette, RotateCcw, Sun } from "lucide-react";
import { cn } from "@/lib/utils";
import { M3_COLOR_THEMES, useTheme, type Theme } from "@/components/providers/theme-provider";

const MODES: { value: Theme; label: string; icon: React.ElementType }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

export function ThemeQuickPicker() {
  const { colorTheme, setColorTheme, theme, setTheme, resetColorThemeToBrand } = useTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const active = M3_COLOR_THEMES.find((t) => t.id === colorTheme) ?? M3_COLOR_THEMES[0];

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title={`Theme: ${active.name}`}
        className={cn(
          "inline-flex items-center gap-1.5 h-8 px-2 rounded-full border transition-colors",
          "border-neutral-200 dark:border-neutral-800 hover:bg-neutral-100 dark:hover:bg-neutral-800",
          open && "bg-neutral-100 dark:bg-neutral-800"
        )}
      >
        <span
          className="w-4 h-4 rounded-full ring-2 ring-white dark:ring-neutral-900 shadow"
          style={{ backgroundColor: active.primaryHex }}
        />
        <Palette className="w-3.5 h-3.5 text-neutral-500 dark:text-neutral-400" />
      </button>

      {open && (
        <div
          className={cn(
            "absolute right-0 top-10 z-50 w-72 p-3 rounded-2xl border shadow-xl",
            "bg-white dark:bg-neutral-900 border-neutral-200 dark:border-neutral-800"
          )}
        >
          <div className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500 mb-2">
            Color theme
          </div>
          <div className="space-y-1">
            {M3_COLOR_THEMES.map((t) => {
              const selected = t.id === colorTheme;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setColorTheme(t.id)}
                  className={cn(
                    "w-full flex items-center gap-2.5 px-2 py-1.5 rounded-lg text-left transition-colors",
                    selected
                      ? "bg-primary-500/10"
                      : "hover:bg-neutral-100 dark:hover:bg-neutral-800"
                  )}
                >
                  <span className="relative flex -space-x-1 shrink-0">
                    <span
                      className="w-5 h-5 rounded-full ring-2 ring-white dark:ring-neutral-900"
                      style={{ backgroundColor: t.primaryHex }}
                    />
                    <span
                      className="w-4 h-4 mt-0.5 rounded-full ring-2 ring-white dark:ring-neutral-900"
                      style={{ backgroundColor: t.surfaceDarkHex }}
                    />
                  </span>
                  <span className="flex-1 min-w-0 text-xs font-medium text-neutral-800 dark:text-neutral-200 truncate">
                    {t.name}
                  </span>
                  {t.badge && (
                    <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase bg-neutral-100 dark:bg-neutral-800 text-neutral-500">
                      {t.badge}
                    </span>
                  )}
                  {selected && <Check className="w-3.5 h-3.5 text-primary-500 shrink-0" />}
                </button>
              );
            })}
          </div>

          <div className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500 mt-3 mb-2">
            Appearance
          </div>
          <div className="flex rounded-lg bg-neutral-100 dark:bg-neutral-800 p-0.5">
            {MODES.map((m) => {
              const Icon = m.icon;
              const selected = theme === m.value;
              return (
                <button
                  key={m.value}
                  type="button"
                  onClick={() => setTheme(m.value)}
                  className={cn(
                    "flex-1 inline-flex items-center justify-center gap-1 py-1.5 rounded-md text-[11px] font-medium transition-all",
                    selected
                      ? "bg-white dark:bg-neutral-700 text-primary-600 dark:text-primary-400 shadow-sm"
                      : "text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300"
                  )}
                >
                  <Icon className="w-3 h-3" />
                  {m.label}
                </button>
              );
            })}
          </div>

          <button
            type="button"
            onClick={resetColorThemeToBrand}
            className="mt-3 w-full inline-flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-[11px] text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800"
          >
            <RotateCcw className="w-3 h-3" />
            Use edition brand theme
          </button>
        </div>
      )}
    </div>
  );
}

export default ThemeQuickPicker;
