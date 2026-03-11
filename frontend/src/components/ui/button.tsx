import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";
export type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary: cn(
    "bg-primary-500 hover:bg-primary-600 text-white",
    "shadow-sm shadow-primary-500/20",
    "disabled:bg-primary-300 dark:disabled:bg-primary-800"
  ),
  secondary: cn(
    "border border-neutral-200 dark:border-neutral-700",
    "bg-white dark:bg-neutral-800",
    "text-neutral-700 dark:text-neutral-300",
    "hover:bg-neutral-50 dark:hover:bg-neutral-700",
    "disabled:text-neutral-400 dark:disabled:text-neutral-500"
  ),
  danger: cn(
    "bg-error hover:bg-red-600 text-white",
    "shadow-sm shadow-red-500/20",
    "disabled:bg-red-300 dark:disabled:bg-red-900"
  ),
  ghost: cn(
    "text-neutral-600 dark:text-neutral-400",
    "hover:bg-neutral-100 dark:hover:bg-neutral-800",
    "disabled:text-neutral-400 dark:disabled:text-neutral-600"
  ),
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "px-3 py-1.5 text-xs rounded-lg gap-1.5",
  md: "px-4 py-2.5 text-sm rounded-xl gap-2",
  lg: "px-6 py-3 text-sm rounded-xl gap-2",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", className, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center font-medium transition-all",
          "disabled:cursor-not-allowed disabled:opacity-60",
          "focus:outline-none focus:ring-2 focus:ring-primary-500/40",
          variantStyles[variant],
          sizeStyles[size],
          className
        )}
        {...props}
      >
        {children}
      </button>
    );
  }
);

Button.displayName = "Button";
