import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useMode, type AppMode } from "@/contexts/mode-context";

const SEGMENTS: { value: AppMode; label: string }[] = [
  { value: "solo", label: "Solo" },
  { value: "coder", label: "Coder" },
];

const HOME_FOR: Record<AppMode, string> = {
  solo: "/",
  coder: "/coder/projects",
};

export function ModeToggle() {
  const { mode, setMode } = useMode();
  const navigate = useNavigate();

  return (
    <div
      role="tablist"
      aria-label="Application mode"
      className={cn(
        "inline-flex bg-neutral-100 dark:bg-neutral-800 rounded-full p-0.5",
        "h-8 w-[140px]"
      )}
    >
      {SEGMENTS.map((seg) => {
        const active = mode === seg.value;
        return (
          <button
            key={seg.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => {
              setMode(seg.value);
              navigate(HOME_FOR[seg.value]);
            }}
            className={cn(
              "flex-1 inline-flex items-center justify-center",
              "rounded-full text-xs font-medium",
              "transition-all duration-150",
              active
                ? "bg-primary-500 text-white shadow-sm"
                : "text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300"
            )}
          >
            {seg.label}
          </button>
        );
      })}
    </div>
  );
}

export default ModeToggle;
