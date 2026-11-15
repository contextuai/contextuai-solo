import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface Tab {
  id: string;
  label: string;
  icon?: ReactNode;
  badge?: string | number;
}

interface TabsProps {
  tabs: Tab[];
  activeTab: string;
  onChange: (id: string) => void;
  className?: string;
}

export function Tabs({ tabs, activeTab, onChange, className }: TabsProps) {
  return (
    <div
      role="tablist"
      className={cn(
        "inline-flex gap-1 p-1.5 rounded-2xl border",
        "bg-neutral-100/80 dark:bg-neutral-900/80",
        "border-neutral-200/70 dark:border-neutral-800",
        className
      )}
    >
      {tabs.map((tab) => {
        const active = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={active}
            type="button"
            onClick={() => onChange(tab.id)}
            className={cn(
              "flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all duration-150 whitespace-nowrap",
              active
                ? "bg-primary-500/15 text-primary-700 dark:text-primary-300 shadow-sm ring-1 ring-primary-500/25"
                : "text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-200 hover:bg-white/50 dark:hover:bg-neutral-800/60"
            )}
          >
            {tab.icon}
            <span>{tab.label}</span>
            {tab.badge !== undefined && (
              <span
                className={cn(
                  "px-1.5 py-0.5 rounded-full text-[10px] font-bold tabular-nums",
                  active
                    ? "bg-primary-500 text-white"
                    : "bg-neutral-200 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300"
                )}
              >
                {tab.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
