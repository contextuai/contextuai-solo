import { useState, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { crewsApi, type CrewRun, type CrewRunStep } from "@/lib/api/crews-client";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  Circle,
  ChevronDown,
  ChevronUp,
  DollarSign,
  Zap,
  Timer,
  X,
  StopCircle,
} from "lucide-react";

interface CrewRunProgressProps {
  crewId: string;
  runId: string;
  onClose: () => void;
}

function formatDuration(seconds?: number): string {
  if (seconds == null) return "--";
  if (seconds < 60) return `${seconds}s`;
  const min = Math.floor(seconds / 60);
  const sec = seconds % 60;
  return `${min}m ${sec}s`;
}

function StepIcon({ status }: { status: string }) {
  switch (status) {
    case "completed":
      return <CheckCircle2 className="w-5 h-5 text-green-500" />;
    case "failed":
      return <XCircle className="w-5 h-5 text-red-500" />;
    case "running":
      return <Loader2 className="w-5 h-5 text-primary-500 animate-spin" />;
    default:
      return <Circle className="w-5 h-5 text-neutral-300 dark:text-neutral-600" />;
  }
}

export function CrewRunProgress({ crewId, runId, onClose }: CrewRunProgressProps) {
  const [run, setRun] = useState<CrewRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());
  const [cancelling, setCancelling] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let mounted = true;

    const fetchRun = async () => {
      try {
        const data = await crewsApi.getRun(crewId, runId);
        if (!mounted) return;
        setRun(data);
        setLoading(false);

        // Stop polling when run is terminal
        if (["completed", "failed", "cancelled"].includes(data.status)) {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        }
      } catch (err) {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : "Failed to load run");
        setLoading(false);
      }
    };

    fetchRun();
    intervalRef.current = setInterval(fetchRun, 2000);

    return () => {
      mounted = false;
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [crewId, runId]);

  const toggleStep = (index: number) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const handleCancel = async () => {
    setCancelling(true);
    try {
      await crewsApi.cancelRun(crewId, runId);
    } catch {
      // ignore
    } finally {
      setCancelling(false);
    }
  };

  const isTerminal = run
    ? ["completed", "failed", "cancelled"].includes(run.status)
    : false;

  const completedSteps = run?.steps?.filter((s) => s.status === "completed").length ?? 0;
  const totalSteps = run?.steps?.length ?? 0;

  if (loading) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
        <div className="bg-white dark:bg-neutral-900 rounded-2xl p-12 shadow-2xl border border-neutral-200 dark:border-neutral-700">
          <Loader2 className="w-8 h-8 animate-spin text-primary-500 mx-auto" />
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-3">Loading run...</p>
        </div>
      </div>
    );
  }

  if (error || !run) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
        <div className="bg-white dark:bg-neutral-900 rounded-2xl p-8 shadow-2xl border border-neutral-200 dark:border-neutral-700 max-w-md text-center">
          <XCircle className="w-10 h-10 text-red-400 mx-auto mb-3" />
          <p className="text-sm text-neutral-700 dark:text-neutral-300 mb-4">
            {error || "Run not found"}
          </p>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-primary-500 text-white text-sm font-medium hover:bg-primary-600 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-2xl max-h-[85vh] bg-white dark:bg-neutral-900 rounded-2xl shadow-2xl border border-neutral-200 dark:border-neutral-700 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-800">
          <div>
            <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
              Run Progress
            </h2>
            <p className="text-xs text-neutral-500 dark:text-neutral-400">
              {run.run_id.slice(0, 12)}...
            </p>
          </div>
          <div className="flex items-center gap-2">
            {!isTerminal && (
              <button
                onClick={handleCancel}
                disabled={cancelling}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
              >
                {cancelling ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <StopCircle className="w-3.5 h-3.5" />
                )}
                Cancel
              </button>
            )}
            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
            >
              <X className="w-5 h-5 text-neutral-500" />
            </button>
          </div>
        </div>

        {/* Stats bar */}
        <div className="grid grid-cols-4 gap-3 px-6 py-3 border-b border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-800/30">
          <div className="text-center">
            <div className="flex items-center justify-center gap-1 text-xs text-neutral-500 dark:text-neutral-400 mb-0.5">
              <Timer className="w-3 h-3" />
              Duration
            </div>
            <p className="text-sm font-semibold text-neutral-900 dark:text-white">
              {formatDuration(run.duration_seconds)}
            </p>
          </div>
          <div className="text-center">
            <div className="flex items-center justify-center gap-1 text-xs text-neutral-500 dark:text-neutral-400 mb-0.5">
              <Zap className="w-3 h-3" />
              Tokens
            </div>
            <p className="text-sm font-semibold text-neutral-900 dark:text-white">
              {run.total_tokens?.toLocaleString() ?? "--"}
            </p>
          </div>
          <div className="text-center">
            <div className="flex items-center justify-center gap-1 text-xs text-neutral-500 dark:text-neutral-400 mb-0.5">
              <DollarSign className="w-3 h-3" />
              Cost
            </div>
            <p className="text-sm font-semibold text-neutral-900 dark:text-white">
              {run.cost_usd != null ? `$${run.cost_usd.toFixed(4)}` : "--"}
            </p>
          </div>
          <div className="text-center">
            <div className="flex items-center justify-center gap-1 text-xs text-neutral-500 dark:text-neutral-400 mb-0.5">
              <CheckCircle2 className="w-3 h-3" />
              Progress
            </div>
            <p className="text-sm font-semibold text-neutral-900 dark:text-white">
              {completedSteps}/{totalSteps}
            </p>
          </div>
        </div>

        {/* Progress bar */}
        {totalSteps > 0 && (
          <div className="px-6 pt-3">
            <div className="w-full h-2 rounded-full bg-neutral-200 dark:bg-neutral-700 overflow-hidden">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-500",
                  run.status === "failed"
                    ? "bg-red-500"
                    : run.status === "completed"
                    ? "bg-green-500"
                    : "bg-primary-500"
                )}
                style={{
                  width: `${totalSteps > 0 ? (completedSteps / totalSteps) * 100 : 0}%`,
                }}
              />
            </div>
          </div>
        )}

        {/* Steps */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
          {run.steps && run.steps.length > 0 ? (
            run.steps.map((step, i) => (
              <StepCard
                key={i}
                step={step}
                index={i}
                expanded={expandedSteps.has(i)}
                onToggle={() => toggleStep(i)}
                isLast={i === run.steps!.length - 1}
              />
            ))
          ) : (
            <div className="text-center py-8">
              <p className="text-sm text-neutral-500 dark:text-neutral-400">
                {run.status === "pending"
                  ? "Waiting for execution to start..."
                  : "No step data available for this run."}
              </p>
              {run.status === "pending" && (
                <Loader2 className="w-5 h-5 animate-spin text-primary-500 mx-auto mt-3" />
              )}
            </div>
          )}

          {/* Error display */}
          {run.error && (
            <div className="p-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 text-sm">
              {run.error}
            </div>
          )}

          {/* Output data */}
          {run.output_data && Object.keys(run.output_data).length > 0 && (
            <div className="p-4 rounded-xl bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-800">
              <h4 className="text-sm font-medium text-green-800 dark:text-green-300 mb-2">
                Final Output
              </h4>
              <pre className="text-xs text-green-700 dark:text-green-400 overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(run.output_data, null, 2)}
              </pre>
            </div>
          )}
        </div>

        {/* Footer status */}
        <div className="px-6 py-3 border-t border-neutral-200 dark:border-neutral-800 flex items-center justify-between">
          <RunStatusBadge status={run.status} />
          {run.completed_at && (
            <span className="text-xs text-neutral-400">
              Completed {new Date(run.completed_at).toLocaleString()}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function StepCard({
  step,
  index,
  expanded,
  onToggle,
  isLast,
}: {
  step: CrewRunStep;
  index: number;
  expanded: boolean;
  onToggle: () => void;
  isLast: boolean;
}) {
  return (
    <div className="relative">
      {/* Connecting line */}
      {!isLast && (
        <div className="absolute left-[18px] top-10 bottom-0 w-0.5 bg-neutral-200 dark:bg-neutral-700" />
      )}

      <div
        className={cn(
          "bg-white dark:bg-neutral-800/50 rounded-xl border transition-colors",
          step.status === "running"
            ? "border-primary-300 dark:border-primary-700"
            : step.status === "completed"
            ? "border-green-200 dark:border-green-800/50"
            : step.status === "failed"
            ? "border-red-200 dark:border-red-800/50"
            : "border-neutral-200 dark:border-neutral-700"
        )}
      >
        <button
          onClick={onToggle}
          className="w-full flex items-center gap-3 p-3 text-left"
        >
          <StepIcon status={step.status} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-neutral-900 dark:text-white truncate">
                {step.agent_name}
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-neutral-100 dark:bg-neutral-700 text-neutral-500 dark:text-neutral-400 uppercase flex-shrink-0">
                Step {index + 1}
              </span>
            </div>
            <div className="flex items-center gap-3 mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
              {step.duration_seconds != null && (
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {formatDuration(step.duration_seconds)}
                </span>
              )}
              {step.tokens_used != null && (
                <span>{step.tokens_used.toLocaleString()} tokens</span>
              )}
            </div>
          </div>
          {step.output && (
            expanded ? (
              <ChevronUp className="w-4 h-4 text-neutral-400 flex-shrink-0" />
            ) : (
              <ChevronDown className="w-4 h-4 text-neutral-400 flex-shrink-0" />
            )
          )}
        </button>

        {expanded && step.output && (
          <div className="px-3 pb-3 pt-0">
            <div className="p-3 rounded-lg bg-neutral-50 dark:bg-neutral-900/50 text-xs text-neutral-700 dark:text-neutral-300 whitespace-pre-wrap max-h-48 overflow-y-auto">
              {step.output}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function RunStatusBadge({ status }: { status: string }) {
  const config: Record<string, { label: string; cls: string }> = {
    pending: { label: "Pending", cls: "bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400" },
    running: { label: "Running", cls: "bg-primary-50 dark:bg-primary-500/10 text-primary-600 dark:text-primary-400" },
    completed: { label: "Completed", cls: "bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400" },
    failed: { label: "Failed", cls: "bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400" },
    cancelled: { label: "Cancelled", cls: "bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400" },
  };
  const c = config[status] ?? config.pending;
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium", c.cls)}>
      {status === "running" && <Loader2 className="w-3 h-3 animate-spin" />}
      {status === "completed" && <CheckCircle2 className="w-3 h-3" />}
      {status === "failed" && <XCircle className="w-3 h-3" />}
      {c.label}
    </span>
  );
}
