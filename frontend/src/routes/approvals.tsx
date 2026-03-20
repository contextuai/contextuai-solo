import { useState, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import {
  ClipboardCheck,
  X,
  Edit3,
  MessageCircle,
  Clock,
  Send,
  Loader2,
  RefreshCw,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import {
  listApprovals,
  approveApproval,
  rejectApproval,
  type Approval,
} from "@/lib/api/approvals-client";

const CHANNEL_LABELS: Record<string, string> = {
  telegram: "Telegram",
  discord: "Discord",
  whatsapp: "WhatsApp",
  teams: "Teams",
  slack: "Slack",
};

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function ApprovalCard({
  approval,
  onApprove,
  onReject,
}: {
  approval: Approval;
  onApprove: (id: string, edited?: string) => Promise<void>;
  onReject: (id: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(approval.draft_response);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const isPending = approval.status === "pending";

  const handleApprove = async () => {
    setLoading(true);
    try {
      const edited = editing && editText !== approval.draft_response ? editText : undefined;
      await onApprove(approval.approval_id, edited);
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    setLoading(true);
    try {
      await onReject(approval.approval_id);
    } finally {
      setLoading(false);
    }
  };

  const statusColor = {
    pending: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
    approved: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
    edited: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
    rejected: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  }[approval.status] || "";

  return (
    <div className="rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800/50 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <MessageCircle className="w-4 h-4 text-neutral-500" />
            <span className="text-sm font-medium text-neutral-900 dark:text-white">
              {approval.sender_name}
            </span>
          </div>
          <span className="text-xs text-neutral-500">
            via {CHANNEL_LABELS[approval.channel_type] || approval.channel_type}
          </span>
          <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium", statusColor)}>
            {approval.status}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-neutral-400">
            <Clock className="w-3 h-3 inline mr-1" />
            {timeAgo(approval.created_at)}
          </span>
          {expanded ? (
            <ChevronUp className="w-4 h-4 text-neutral-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-neutral-400" />
          )}
        </div>
      </button>

      {/* Body */}
      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-neutral-100 dark:border-neutral-700/50 pt-3">
          {/* Inbound message */}
          <div>
            <p className="text-xs font-medium text-neutral-500 mb-1">Inbound Message</p>
            <div className="rounded-lg bg-neutral-50 dark:bg-neutral-900 p-3 text-sm text-neutral-800 dark:text-neutral-200">
              {approval.inbound_text}
            </div>
          </div>

          {/* Draft response */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <p className="text-xs font-medium text-neutral-500">
                {isPending ? "Draft Response" : "Response"}
              </p>
              {isPending && !editing && (
                <button
                  onClick={() => setEditing(true)}
                  className="text-xs text-primary-500 hover:text-primary-600 flex items-center gap-1"
                >
                  <Edit3 className="w-3 h-3" />
                  Edit
                </button>
              )}
            </div>
            {editing ? (
              <textarea
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                rows={4}
                className="w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 p-3 text-sm text-neutral-800 dark:text-neutral-200 focus:ring-2 focus:ring-primary-500 focus:border-transparent resize-y"
              />
            ) : (
              <div className="rounded-lg bg-primary-50/50 dark:bg-primary-900/20 border border-primary-100 dark:border-primary-800/30 p-3 text-sm text-neutral-800 dark:text-neutral-200">
                {approval.final_response || approval.draft_response}
              </div>
            )}
          </div>

          {/* Actions */}
          {isPending && (
            <div className="flex items-center gap-2 pt-1">
              <button
                onClick={handleApprove}
                disabled={loading}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-green-500 hover:bg-green-600 text-white text-sm font-medium transition-colors disabled:opacity-50"
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
                {editing ? "Send Edited" : "Approve & Send"}
              </button>
              <button
                onClick={handleReject}
                disabled={loading}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-neutral-200 dark:bg-neutral-700 hover:bg-red-100 dark:hover:bg-red-900/30 text-neutral-700 dark:text-neutral-300 hover:text-red-700 dark:hover:text-red-400 text-sm font-medium transition-colors disabled:opacity-50"
              >
                <X className="w-4 h-4" />
                Reject
              </button>
              {editing && (
                <button
                  onClick={() => {
                    setEditing(false);
                    setEditText(approval.draft_response);
                  }}
                  className="text-xs text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300 ml-2"
                >
                  Cancel edit
                </button>
              )}
            </div>
          )}

          {/* Reviewed info */}
          {!isPending && approval.reviewed_at && (
            <p className="text-xs text-neutral-400">
              {approval.status === "rejected" ? "Rejected" : "Approved"}{" "}
              {timeAgo(approval.reviewed_at)} by {approval.reviewed_by || "unknown"}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [filter, setFilter] = useState<"pending" | "all">("pending");
  const [loading, setLoading] = useState(true);

  const loadApprovals = useCallback(async () => {
    setLoading(true);
    try {
      const status = filter === "pending" ? "pending" : undefined;
      const data = await listApprovals(status || "");
      setApprovals(data);
    } catch (err) {
      console.warn("Failed to load approvals:", err);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    loadApprovals();
    // Poll every 10 seconds for new pending approvals
    const interval = setInterval(loadApprovals, 10000);
    return () => clearInterval(interval);
  }, [loadApprovals]);

  const handleApprove = async (id: string, edited?: string) => {
    await approveApproval(id, edited);
    await loadApprovals();
  };

  const handleReject = async (id: string) => {
    await rejectApproval(id);
    await loadApprovals();
  };

  const pendingCount = approvals.filter((a) => a.status === "pending").length;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-amber-100 dark:bg-amber-900/30">
              <ClipboardCheck className="w-5 h-5 text-amber-600 dark:text-amber-400" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-neutral-900 dark:text-white">
                Approval Queue
              </h1>
              <p className="text-sm text-neutral-500">
                Review AI-generated replies before they are sent
              </p>
            </div>
            {pendingCount > 0 && (
              <span className="ml-2 px-2.5 py-0.5 rounded-full bg-amber-500 text-white text-xs font-bold">
                {pendingCount}
              </span>
            )}
          </div>
          <button
            onClick={loadApprovals}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
          >
            <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
            Refresh
          </button>
        </div>

        {/* Filter tabs */}
        <div className="flex gap-1 mb-6 p-1 rounded-lg bg-neutral-100 dark:bg-neutral-800 w-fit">
          {(["pending", "all"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                "px-4 py-1.5 rounded-md text-sm font-medium transition-colors",
                filter === f
                  ? "bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white shadow-sm"
                  : "text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300"
              )}
            >
              {f === "pending" ? "Pending" : "All"}
            </button>
          ))}
        </div>

        {/* List */}
        {loading && approvals.length === 0 ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 text-neutral-400 animate-spin" />
          </div>
        ) : approvals.length === 0 ? (
          <div className="text-center py-16">
            <ClipboardCheck className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
            <p className="text-neutral-500 dark:text-neutral-400">
              {filter === "pending"
                ? "No pending approvals"
                : "No approvals yet"}
            </p>
            <p className="text-sm text-neutral-400 dark:text-neutral-500 mt-1">
              When a trigger has "require approval" enabled, AI-generated replies will appear here
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {approvals.map((a) => (
              <ApprovalCard
                key={a.approval_id}
                approval={a}
                onApprove={handleApprove}
                onReject={handleReject}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
