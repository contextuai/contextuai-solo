import { forwardRef, type TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  helperText?: string;
  error?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, helperText, error, className, ...props }, ref) => {
    return (
      <div className="w-full">
        {label && (
          <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          className={cn(
            "w-full px-4 py-2.5 rounded-xl text-sm resize-none",
            "bg-neutral-50 dark:bg-neutral-800",
            "border border-neutral-200 dark:border-neutral-700",
            "text-neutral-900 dark:text-white",
            "placeholder:text-neutral-400 dark:placeholder:text-neutral-500",
            "focus:outline-none focus:ring-2 focus:ring-primary-500/40 focus:border-primary-500",
            "transition-all",
            error && "border-error focus:ring-error/40 focus:border-error",
            className
          )}
          {...props}
        />
        {helperText && !error && (
          <p className="mt-1.5 text-xs text-neutral-500 dark:text-neutral-400">{helperText}</p>
        )}
        {error && <p className="mt-1.5 text-xs text-error">{error}</p>}
      </div>
    );
  }
);

Textarea.displayName = "Textarea";
