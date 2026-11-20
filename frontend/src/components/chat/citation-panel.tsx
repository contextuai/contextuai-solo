import { useState } from "react";
import { BookOpen, ChevronDown, ChevronUp, FileText, Search, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatCitation } from "@/types/chat";

export interface CitationPanelProps {
  citations: ChatCitation[];
  ragMode?: string;
  activeIndex?: number | null;
  onSelectIndex?: (idx: number | null) => void;
}

function formatScore(citation: ChatCitation, isFullContext: boolean): string | null {
  if (isFullContext || citation.mode === "full_context") {
    return "Full document";
  }
  if (typeof citation.score !== "number" || Number.isNaN(citation.score)) {
    return null;
  }
  if (citation.score <= 1 && citation.score >= 0) {
    return `${Math.round(citation.score * 100)}% match`;
  }
  return `Score ${citation.score.toFixed(2)}`;
}

export function CitationPanel({
  citations,
  ragMode,
  activeIndex,
  onSelectIndex,
}: CitationPanelProps) {
  const [internalIndex, setInternalIndex] = useState<number | null>(null);

  if (!citations || citations.length === 0) {
    return null;
  }

  const selectedIndex = activeIndex !== undefined ? activeIndex : internalIndex;
  const setSelected = (idx: number | null) => {
    onSelectIndex?.(idx);
    if (activeIndex === undefined) {
      setInternalIndex(idx);
    }
  };

  const effectiveMode = ragMode || citations[0]?.mode || "hybrid_rag";
  const isFullContext = effectiveMode === "full_context";
  const activeCitation =
    selectedIndex !== null
      ? citations.find((c) => c.index === selectedIndex) ?? null
      : null;

  return (
    <div className="mt-2.5 pt-2 border-t border-neutral-200/70 dark:border-neutral-700/60">
      <div className="flex flex-wrap items-center gap-1.5">
        {/* Retrieval mode pill */}
        <span
          className={cn(
            "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium border",
            isFullContext
              ? "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/25"
              : "bg-primary-50 dark:bg-primary-500/10 text-primary-700 dark:text-primary-300 border-primary-200 dark:border-primary-500/25"
          )}
          title={
            isFullContext
              ? "Entire document context injected within model context budget"
              : "Hybrid dense + BM25 retrieval"
          }
        >
          {isFullContext ? (
            <BookOpen className="w-2.5 h-2.5" />
          ) : (
            <Search className="w-2.5 h-2.5" />
          )}
          <span>{isFullContext ? "Full Context" : "Hybrid Search"}</span>
        </span>

        {/* Clickable citation chips */}
        {citations.map((c) => {
          const isSelected = selectedIndex === c.index;
          const pageSuffix =
            c.page !== undefined && c.page !== null && c.page > 0
              ? ` p.${c.page}`
              : "";
          return (
            <button
              key={`${c.index}-${c.doc_id ?? c.filename}-${c.chunk_index ?? 0}`}
              type="button"
              onClick={() => setSelected(isSelected ? null : c.index)}
              aria-expanded={isSelected}
              title={`Inspect [${c.index}] ${c.filename}${pageSuffix}`}
              className={cn(
                "inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium border transition-colors max-w-[220px]",
                isSelected
                  ? "bg-primary-100/80 dark:bg-primary-500/20 text-primary-700 dark:text-primary-200 border-primary-300 dark:border-primary-500/50"
                  : "bg-white/80 dark:bg-neutral-900/60 text-neutral-700 dark:text-neutral-300 border-neutral-200 dark:border-neutral-700 hover:border-primary-300 dark:hover:border-primary-600 hover:bg-neutral-50 dark:hover:bg-neutral-800"
              )}
            >
              <span className="font-semibold text-primary-600 dark:text-primary-400 shrink-0">
                [{c.index}]
              </span>
              <span className="truncate">{c.filename}</span>
              {pageSuffix && (
                <span className="text-neutral-500 dark:text-neutral-400 shrink-0">
                  {pageSuffix}
                </span>
              )}
              {isSelected ? (
                <ChevronUp className="w-3 h-3 shrink-0 opacity-70" />
              ) : (
                <ChevronDown className="w-3 h-3 shrink-0 opacity-70" />
              )}
            </button>
          );
        })}
      </div>

      {/* Expandable verbatim excerpt preview card */}
      {activeCitation && (
        <div className="mt-2 rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white/95 dark:bg-neutral-900/85 p-3 shadow-sm">
          <div className="flex items-start justify-between gap-2 pb-2 border-b border-neutral-200/70 dark:border-neutral-700/60">
            <div className="flex flex-wrap items-center gap-2 min-w-0">
              <FileText className="w-3.5 h-3.5 text-primary-500 shrink-0" />
              <span className="text-xs font-semibold text-neutral-900 dark:text-neutral-100 truncate">
                [{activeCitation.index}] {activeCitation.filename}
              </span>
              {activeCitation.page !== undefined &&
                activeCitation.page !== null &&
                activeCitation.page > 0 && (
                  <span className="px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 text-[10px] font-medium text-neutral-600 dark:text-neutral-300">
                    Page {activeCitation.page}
                  </span>
                )}
              {typeof activeCitation.chunk_index === "number" && (
                <span className="px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 text-[10px] font-medium text-neutral-600 dark:text-neutral-300">
                  Chunk #{activeCitation.chunk_index}
                </span>
              )}
              {(() => {
                const scoreText = formatScore(activeCitation, isFullContext);
                if (!scoreText) return null;
                const scoreDetail =
                  typeof activeCitation.vector_score === "number" ||
                  typeof activeCitation.bm25_score === "number"
                    ? `Vector: ${(activeCitation.vector_score ?? 0).toFixed(3)} · BM25: ${(activeCitation.bm25_score ?? 0).toFixed(2)}`
                    : undefined;
                return (
                  <span
                    title={scoreDetail}
                    className="px-1.5 py-0.5 rounded bg-primary-50 dark:bg-primary-500/15 text-[10px] font-medium text-primary-700 dark:text-primary-300"
                  >
                    {scoreText}
                  </span>
                );
              })()}
            </div>
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="p-0.5 rounded text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors shrink-0"
              title="Close excerpt"
              aria-label="Close citation preview"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="mt-2 max-h-48 overflow-y-auto text-xs leading-relaxed text-neutral-700 dark:text-neutral-300 whitespace-pre-wrap break-words font-normal">
            {activeCitation.excerpt}
          </div>
        </div>
      )}
    </div>
  );
}

export default CitationPanel;
