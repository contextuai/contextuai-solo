import { cn } from "@/lib/utils";

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  label?: string;
  size?: "sm" | "md";
}

export function Switch({ checked, onChange, disabled, label, size = "md" }: SwitchProps) {
  const track = size === "sm" ? "h-5 w-9" : "h-6 w-11";
  const thumb = size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4";
  const translate = size === "sm" ? (checked ? "translate-x-4" : "translate-x-1") : (checked ? "translate-x-6" : "translate-x-1");

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex flex-shrink-0 items-center rounded-full transition-colors",
        "focus:outline-none focus:ring-2 focus:ring-primary-500/40",
        track,
        checked ? "bg-primary-500" : "bg-neutral-300 dark:bg-neutral-700",
        disabled && "opacity-60 cursor-not-allowed"
      )}
    >
      <span
        className={cn(
          "inline-block transform rounded-full bg-white shadow transition-transform",
          thumb,
          translate
        )}
      />
    </button>
  );
}
