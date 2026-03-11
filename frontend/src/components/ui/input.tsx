import { forwardRef, useState, type InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";
import { Eye, EyeOff } from "lucide-react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  helperText?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, helperText, error, className, type, ...props }, ref) => {
    const [showPassword, setShowPassword] = useState(false);
    const isPassword = type === "password";

    return (
      <div className="w-full">
        {label && (
          <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
            {label}
          </label>
        )}
        <div className="relative">
          <input
            ref={ref}
            type={isPassword && showPassword ? "text" : type}
            className={cn(
              "w-full px-4 py-2.5 rounded-xl text-sm",
              "bg-neutral-50 dark:bg-neutral-800",
              "border border-neutral-200 dark:border-neutral-700",
              "text-neutral-900 dark:text-white",
              "placeholder:text-neutral-400 dark:placeholder:text-neutral-500",
              "focus:outline-none focus:ring-2 focus:ring-primary-500/40 focus:border-primary-500",
              "transition-all",
              error && "border-error focus:ring-error/40 focus:border-error",
              isPassword && "pr-10",
              className
            )}
            {...props}
          />
          {isPassword && (
            <button
              type="button"
              tabIndex={-1}
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          )}
        </div>
        {helperText && !error && (
          <p className="mt-1.5 text-xs text-neutral-500 dark:text-neutral-400">{helperText}</p>
        )}
        {error && <p className="mt-1.5 text-xs text-error">{error}</p>}
      </div>
    );
  }
);

Input.displayName = "Input";
