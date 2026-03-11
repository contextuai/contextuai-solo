import { forwardRef, type SelectHTMLAttributes } from "react";
import { cn } from "@/lib/utils";
import { ChevronDown } from "lucide-react";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  helperText?: string;
  error?: string;
  options: { value: string; label: string }[];
  placeholder?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, helperText, error, options, placeholder, className, value, ...props }, ref) => {
    return (
      <div className="w-full">
        {label && (
          <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
            {label}
          </label>
        )}
        <div className="relative">
          <select
            ref={ref}
            value={value}
            className={cn(
              "w-full px-4 py-2.5 rounded-xl text-sm appearance-none pr-10",
              "bg-neutral-50 dark:bg-neutral-800",
              "border border-neutral-200 dark:border-neutral-700",
              "text-neutral-900 dark:text-white",
              "focus:outline-none focus:ring-2 focus:ring-primary-500/40 focus:border-primary-500",
              "transition-all",
              !value && "text-neutral-400 dark:text-neutral-500",
              error && "border-error focus:ring-error/40 focus:border-error",
              className
            )}
            {...props}
          >
            {placeholder && <option value="">{placeholder}</option>}
            {options.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400 pointer-events-none" />
        </div>
        {helperText && !error && (
          <p className="mt-1.5 text-xs text-neutral-500 dark:text-neutral-400">{helperText}</p>
        )}
        {error && <p className="mt-1.5 text-xs text-error">{error}</p>}
      </div>
    );
  }
);

Select.displayName = "Select";
