import { useState } from "react";
import { Check, Pencil, Pin, Trash2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { MemoryFact } from "@/lib/api/memory-client";

function formatDate(iso?: string | null): string | null {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
  } catch {
    return null;
  }
}

function ConfidenceDot({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const color =
    confidence >= 0.8
      ? "bg-emerald-500"
      : confidence >= 0.6
        ? "bg-amber-500"
        : "bg-red-500";
  return (
    <span
      className="inline-flex items-center gap-1 text-[11px] text-neutral-500 dark:text-neutral-400"
      title={`Extraction confidence: ${pct}%`}
    >
      <span className={cn("w-1.5 h-1.5 rounded-full", color)} />
      {pct}%
    </span>
  );
}

export function FactRow({
  fact,
  onEdit,
  onDelete,
  onTogglePin,
}: {
  fact: MemoryFact;
  onEdit: () => void;
  onDelete: () => Promise<void> | void;
  onTogglePin: () => Promise<void> | void;
}) {
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [pinning, setPinning] = useState(false);

  const sourceText =
    fact.origin === "user"
      ? "added by you"
      : `learned from ${fact.source_label || fact.source_kind}`;
  const created = formatDate(fact.created_at);

  async function handleConfirmDelete() {
    setDeleting(true);
    try {
      await onDelete();
    } finally {
      setDeleting(false);
      setConfirmingDelete(false);
    }
  }

  async function handleTogglePin() {
    setPinning(true);
    try {
      await onTogglePin();
    } finally {
      setPinning(false);
    }
  }

  return (
    <li
      className={cn(
        "flex items-start gap-3 px-4 py-3 text-sm",
        fact.status === "review" && "bg-amber-50/50 dark:bg-amber-500/[0.04]",
      )}
    >
      <div className="min-w-0 flex-1">
        <p className="text-neutral-900 dark:text-white leading-snug">
          {fact.text}
        </p>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-neutral-500 dark:text-neutral-400">
          <span>{sourceText}</span>
          {created && <span>· {created}</span>}
          {fact.status === "review" && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-400 font-medium">
              Needs review
            </span>
          )}
          {fact.origin === "extracted" && (
            <ConfidenceDot confidence={fact.confidence} />
          )}
          {typeof fact.score === "number" && (
            <span className="font-mono">match {fact.score.toFixed(2)}</span>
          )}
        </div>
      </div>

      {confirmingDelete ? (
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span className="text-xs text-neutral-500 dark:text-neutral-400 mr-1">
            Delete?
          </span>
          <button
            onClick={handleConfirmDelete}
            disabled={deleting}
            className="p-1.5 rounded-lg text-white bg-red-500 hover:bg-red-600 disabled:opacity-60 transition-colors"
            title="Confirm delete"
          >
            <Check className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setConfirmingDelete(false)}
            disabled={deleting}
            className="p-1.5 rounded-lg text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
            title="Cancel"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            onClick={handleTogglePin}
            disabled={pinning}
            className={cn(
              "p-1.5 rounded-lg transition-colors",
              fact.pinned
                ? "text-primary-500 hover:bg-primary-50 dark:hover:bg-primary-500/10"
                : "text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800",
            )}
            title={fact.pinned ? "Unpin" : "Pin"}
          >
            <Pin className={cn("w-3.5 h-3.5", fact.pinned && "fill-current")} />
          </button>
          <button
            onClick={onEdit}
            className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
            title="Edit"
          >
            <Pencil className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setConfirmingDelete(true)}
            className="p-1.5 rounded-lg text-neutral-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
            title="Delete"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </li>
  );
}
