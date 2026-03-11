import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
}

export function Dialog({ open, onClose, title, children, actions, className }: DialogProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Overlay */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className={cn(
          "relative z-10 w-full max-w-md mx-4",
          "bg-white dark:bg-neutral-900",
          "rounded-2xl border border-neutral-200 dark:border-neutral-800",
          "shadow-xl",
          className
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-3">
          <h3 className="text-lg font-semibold text-neutral-900 dark:text-white">
            {title}
          </h3>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="px-6 pb-4 text-sm text-neutral-600 dark:text-neutral-400">
          {children}
        </div>

        {/* Actions */}
        {actions && (
          <div className="flex items-center justify-end gap-3 px-6 pb-5 pt-2">
            {actions}
          </div>
        )}
      </div>
    </div>
  );
}
