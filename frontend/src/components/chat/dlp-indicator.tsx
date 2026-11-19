import { ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DlpRedactionSummary } from "@/types/chat";

export interface DlpIndicatorProps {
  summary?: (DlpRedactionSummary & { total_redactions?: number }) | null;
  className?: string;
}

export function DlpIndicator({ summary, className }: DlpIndicatorProps) {
  const total = summary?.total ?? summary?.total_redactions ?? 0;
  if (!summary || total <= 0) {
    return null;
  }

  const categories = Array.isArray(summary.categories) ? summary.categories : [];
  const categoryText =
    categories.length > 0 ? ` (${categories.join(", ")})` : "";

  return (
    <span
      data-testid="dlp-indicator"
      title={`Local DLP redacted ${total} sensitive item${total === 1 ? "" : "s"}${categoryText} before cloud dispatch.`}
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium border",
        "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
        "border-emerald-200 dark:border-emerald-500/25",
        className
      )}
    >
      <ShieldCheck className="w-3 h-3 text-emerald-500 flex-shrink-0" />
      <span>
        DLP Protected · {total} redacted{categoryText}
      </span>
    </span>
  );
}
