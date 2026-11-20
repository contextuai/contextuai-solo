import { useState, useEffect, useCallback } from "react";
import { ShieldAlert, Check, X, Loader2, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui";
import {
  listApprovals,
  approveApproval,
  rejectApproval,
  type Approval,
} from "@/lib/api/approvals-client";

const RETIRED_SOCIAL_CHANNELS = new Set([
  "linkedin",
  "twitter",
  "instagram",
  "facebook",
  "reddit",
]);

export interface ToolApprovalModalProps {
  open?: boolean;
  onClose?: () => void;
  onResolved?: (approval: Approval, decision: "approved" | "rejected") => void;
  className?: string;
  pollIntervalMs?: number;
}

export function ToolApprovalModal({
  open,
  onClose,
  onResolved,
  className,
  pollIntervalMs = 15000,
}: ToolApprovalModalProps) {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [actingId, setActingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchPending = useCallback(async () => {
    setLoading(true);
    try {
      const items = await listApprovals("pending", 20);
      setApprovals(
        items.filter(
          (a) => !RETIRED_SOCIAL_CHANNELS.has((a.channel_type || "").toLowerCase())
        )
      );
    } catch {
      // Non-fatal while sidecar is warming up
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open === false) return;
    void fetchPending();
    if (pollIntervalMs > 0) {
      const timer = setInterval(() => {
        void fetchPending();
      }, pollIntervalMs);
      return () => clearInterval(timer);
    }
  }, [open, pollIntervalMs, fetchPending]);

  const handleApprove = async (item: Approval) => {
    setActingId(item.approval_id);
    setError(null);
    try {
      const updated = await approveApproval(item.approval_id);
      setApprovals((prev) => prev.filter((a) => a.approval_id !== item.approval_id));
      onResolved?.(updated, "approved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve request");
    } finally {
      setActingId(null);
    }
  };

  const handleReject = async (item: Approval) => {
    setActingId(item.approval_id);
    setError(null);
    try {
      const updated = await rejectApproval(item.approval_id);
      setApprovals((prev) => prev.filter((a) => a.approval_id !== item.approval_id));
      onResolved?.(updated, "rejected");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reject request");
    } finally {
      setActingId(null);
    }
  };

  if (open === false) return null;
  if (open === undefined && approvals.length === 0) return null;

  const content = (
    <div
      className={cn(
        "rounded-2xl border border-amber-300/70 dark:border-amber-500/30",
        "bg-amber-50/90 dark:bg-amber-950/30 p-4 space-y-3 shadow-sm",
        className
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
          <span className="text-xs font-semibold text-amber-900 dark:text-amber-200">
            Pending Tool &amp; Action Approvals ({approvals.length})
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => void fetchPending()}
            title="Refresh pending approvals"
            className="p-1 rounded-lg text-amber-700 dark:text-amber-300 hover:bg-amber-200/50 dark:hover:bg-amber-900/40"
          >
            <RefreshCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} />
          </button>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close approvals"
              className="p-1 rounded-lg text-amber-700 dark:text-amber-300 hover:bg-amber-200/50 dark:hover:bg-amber-900/40"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="text-xs text-red-700 dark:text-red-300 bg-red-100/70 dark:bg-red-900/30 rounded-lg px-2.5 py-1.5">
          {error}
        </div>
      )}

      {approvals.length === 0 ? (
        <p className="text-xs text-neutral-600 dark:text-neutral-400 py-2">
          No pending tool or action approvals.
        </p>
      ) : (
        <div className="space-y-2 max-h-72 overflow-y-auto">
          {approvals.map((item) => {
            const busy = actingId === item.approval_id;
            return (
              <div
                key={item.approval_id}
                className="p-3 rounded-xl bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 space-y-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider bg-amber-100 dark:bg-amber-500/15 text-amber-800 dark:text-amber-300">
                      {item.channel_type || "tool"}
                    </span>
                    <span className="text-xs font-medium text-neutral-900 dark:text-white truncate">
                      {item.sender_name || item.channel_id}
                    </span>
                  </div>
                </div>

                {item.inbound_text && (
                  <p className="text-[11px] text-neutral-500 dark:text-neutral-400 line-clamp-2">
                    {item.inbound_text}
                  </p>
                )}

                {item.draft_response && (
                  <div className="p-2 rounded-lg bg-neutral-50 dark:bg-neutral-800/70 text-xs text-neutral-800 dark:text-neutral-200 whitespace-pre-wrap break-words max-h-24 overflow-y-auto">
                    {item.draft_response}
                  </div>
                )}

                <div className="flex items-center justify-end gap-2 pt-1">
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={busy}
                    onClick={() => void handleReject(item)}
                  >
                    <X className="w-3.5 h-3.5" />
                    Reject
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="primary"
                    disabled={busy}
                    onClick={() => void handleApprove(item)}
                  >
                    {busy ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Check className="w-3.5 h-3.5" />
                    )}
                    Approve
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );

  if (open === true) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="absolute inset-0 bg-black/50 backdrop-blur-sm"
          onClick={onClose}
        />
        <div className="relative z-10 w-full max-w-lg">{content}</div>
      </div>
    );
  }

  return content;
}

export default ToolApprovalModal;
