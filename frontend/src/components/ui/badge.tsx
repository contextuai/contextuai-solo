import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type BadgeVariant = "success" | "warning" | "error" | "info" | "default";

interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  className?: string;
  dot?: boolean;
}

const variantStyles: Record<BadgeVariant, string> = {
  success: "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  warning: "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400",
  error: "bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400",
  info: "bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400",
  default: "bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400",
};

const dotStyles: Record<BadgeVariant, string> = {
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  error: "bg-red-500",
  info: "bg-blue-500",
  default: "bg-neutral-400",
};

export function Badge({ variant = "default", children, className, dot }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium",
        variantStyles[variant],
        className
      )}
    >
      {dot && <span className={cn("w-1.5 h-1.5 rounded-full", dotStyles[variant])} />}
      {children}
    </span>
  );
}
