import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Material Design 3 (M3) & Flutter-inspired layout primitives.
 */

interface M3CardProps {
  children: ReactNode;
  variant?: "outlined" | "tonal" | "elevated";
  interactive?: boolean;
  className?: string;
  onClick?: () => void;
}

export function M3Card({
  children,
  variant = "outlined",
  interactive = false,
  className,
  onClick,
}: M3CardProps) {
  const variantClass =
    variant === "tonal"
      ? "m3-card-tonal"
      : variant === "elevated"
        ? "m3-card-elevated"
        : "m3-card";

  return (
    <div
      onClick={onClick}
      className={cn(
        variantClass,
        "transition-all duration-150",
        interactive &&
          "cursor-pointer hover:-translate-y-0.5 hover:border-primary-500/40 hover:shadow-md active:translate-y-0",
        className
      )}
    >
      {children}
    </div>
  );
}

interface M3PageHeaderProps {
  icon?: ReactNode;
  title: string;
  subtitle?: string;
  badge?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
}

export function M3PageHeader({
  icon,
  title,
  subtitle,
  badge,
  actions,
  children,
  className,
}: M3PageHeaderProps) {
  return (
    <header
      className={cn(
        "px-6 pt-6 pb-4 border-b border-neutral-200/75 dark:border-neutral-800/90",
        "bg-white/80 dark:bg-neutral-900/75 backdrop-blur-md",
        className
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3.5 min-w-0">
          {icon && (
            <div className="flex items-center justify-center w-11 h-11 rounded-2xl bg-primary-500/12 text-primary-600 dark:text-primary-400 border border-primary-500/20 shrink-0">
              {icon}
            </div>
          )}
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white truncate">
                {title}
              </h1>
              {badge}
            </div>
            {subtitle && (
              <p className="text-xs sm:text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
                {subtitle}
              </p>
            )}
          </div>
        </div>
        {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
      </div>
      {children && <div className="mt-4">{children}</div>}
    </header>
  );
}

interface M3StatTileProps {
  label: string;
  value: ReactNode;
  sublabel?: string;
  icon?: ReactNode;
  accent?: boolean;
  className?: string;
}

export function M3StatTile({
  label,
  value,
  sublabel,
  icon,
  accent = false,
  className,
}: M3StatTileProps) {
  return (
    <div
      className={cn(
        "p-4 rounded-2xl border transition-colors",
        accent
          ? "bg-primary-500/10 border-primary-500/25"
          : "bg-white/85 dark:bg-neutral-900/80 border-neutral-200/75 dark:border-neutral-800",
        className
      )}
    >
      <div className="flex items-center justify-between gap-2 text-xs font-medium text-neutral-500 dark:text-neutral-400 mb-1.5">
        <span>{label}</span>
        {icon && <span className="text-primary-500">{icon}</span>}
      </div>
      <div className="text-base font-bold text-neutral-900 dark:text-white tracking-tight">
        {value}
      </div>
      {sublabel && (
        <div className="text-[11px] text-neutral-500 dark:text-neutral-400 mt-1 truncate">
          {sublabel}
        </div>
      )}
    </div>
  );
}

interface M3EmptyStateProps {
  icon: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
  className?: string;
}

export function M3EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: M3EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center px-6 py-12 rounded-3xl",
        "border border-dashed border-neutral-200 dark:border-neutral-800",
        "bg-white/50 dark:bg-neutral-900/40",
        className
      )}
    >
      <div className="flex items-center justify-center w-14 h-14 rounded-3xl bg-primary-500/12 text-primary-500 border border-primary-500/20 mb-4">
        {icon}
      </div>
      <h3 className="text-base font-semibold text-neutral-900 dark:text-white mb-1">
        {title}
      </h3>
      <p className="text-xs sm:text-sm text-neutral-500 dark:text-neutral-400 max-w-md mb-5 leading-relaxed">
        {description}
      </p>
      {action}
    </div>
  );
}
