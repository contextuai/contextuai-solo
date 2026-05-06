import { Wrench } from "lucide-react";

export default function CoderComingSoon() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-48px)] px-6 py-12 text-center">
      <div
        className={[
          "flex items-center justify-center w-20 h-20 rounded-2xl mb-6",
          "bg-primary-50 dark:bg-primary-500/10 text-primary-500",
        ].join(" ")}
      >
        <Wrench className="w-10 h-10" />
      </div>

      <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
        Solo Coder — coming soon
      </h1>

      <p className="mt-3 max-w-md text-sm text-neutral-600 dark:text-neutral-400">
        We're building local, free, business-user-friendly software building.
        Stay tuned.
      </p>

      <div
        className={[
          "mt-8 inline-flex items-center gap-2 px-4 py-2 rounded-full",
          "bg-neutral-100 dark:bg-neutral-800",
          "text-xs text-neutral-600 dark:text-neutral-400",
        ].join(" ")}
      >
        <span>Switch back to Solo mode any time with</span>
        <kbd
          className={[
            "px-1.5 py-0.5 rounded font-mono text-[11px]",
            "bg-white dark:bg-neutral-900",
            "border border-neutral-200 dark:border-neutral-700",
            "text-neutral-700 dark:text-neutral-300",
          ].join(" ")}
        >
          Cmd/Ctrl+Shift+M
        </kbd>
      </div>
    </div>
  );
}
