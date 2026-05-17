import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  Clock,
  Loader2,
  Play,
  Plus,
  Sparkles,
  Trash2,
  Users,
  XCircle,
  Zap,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import {
  type Automation,
  type AutomationExecution,
  type CreateAutomationPayload,
  createAutomation,
  deleteAutomation,
  listAutomations,
  listExecutions,
  promoteToCrew,
  runAutomation,
  streamExecution,
  updateAutomation,
} from "@/lib/api/automations-client";
import { AutomationBuilder } from "@/components/automations/automation-builder";

export default function AutomationsPage() {
  const [automations, setAutomations] = useState<Automation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<Automation | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const list = await listAutomations({ page_size: 100 });
      setAutomations(list.automations);
      if (!selectedId && list.automations.length > 0) {
        setSelectedId(list.automations[0].automation_id);
      }
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    reload();
  }, [reload]);

  const selected = useMemo(
    () => automations.find((a) => a.automation_id === selectedId) ?? null,
    [automations, selectedId],
  );

  async function handleCreate(payload: CreateAutomationPayload) {
    setSubmitting(true);
    try {
      const created = await createAutomation(payload);
      setAutomations((prev) => [created, ...prev]);
      setSelectedId(created.automation_id);
      setCreateOpen(false);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleUpdate(payload: CreateAutomationPayload) {
    if (!editing) return;
    setSubmitting(true);
    try {
      const updated = await updateAutomation(editing.automation_id, payload);
      setAutomations((prev) =>
        prev.map((a) =>
          a.automation_id === updated.automation_id ? updated : a,
        ),
      );
      setEditing(null);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(a: Automation) {
    if (!confirm(`Delete "${a.name}"? This also removes its run history.`))
      return;
    await deleteAutomation(a.automation_id);
    const remaining = automations.filter(
      (x) => x.automation_id !== a.automation_id,
    );
    setAutomations(remaining);
    setSelectedId(remaining[0]?.automation_id ?? null);
  }

  return (
    <div className="flex h-full overflow-hidden bg-neutral-50 dark:bg-neutral-950">
      {/* Left rail — automations list */}
      <div className="flex flex-col w-72 border-r border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900">
        <div className="flex items-center justify-between px-4 h-16 border-b border-neutral-200 dark:border-neutral-800">
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-primary-500" />
            <h2 className="text-sm font-semibold text-neutral-900 dark:text-white">
              Automations
            </h2>
          </div>
          <Button
            size="sm"
            variant="primary"
            onClick={() => setCreateOpen(true)}
          >
            <Plus className="w-3.5 h-3.5" /> New
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-1">
          {loading && (
            <div className="flex items-center gap-2 px-3 py-4 text-xs text-neutral-500">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…
            </div>
          )}
          {!loading && automations.length === 0 && (
            <div className="px-3 py-8 text-xs text-center text-neutral-500 dark:text-neutral-400">
              <Sparkles className="w-5 h-5 mx-auto mb-2 text-neutral-400" />
              No automations yet. Create one to start chaining your agents.
            </div>
          )}
          {automations.map((a) => (
            <button
              key={a.automation_id}
              onClick={() => setSelectedId(a.automation_id)}
              className={cn(
                "w-full flex items-start gap-2.5 px-3 py-2.5 rounded-lg text-left transition-colors",
                "hover:bg-neutral-100 dark:hover:bg-neutral-800",
                selectedId === a.automation_id &&
                  "bg-primary-50 dark:bg-primary-500/10 text-primary-700 dark:text-primary-300",
              )}
            >
              <Zap
                className={cn(
                  "w-4 h-4 flex-shrink-0 mt-0.5",
                  selectedId === a.automation_id
                    ? "text-primary-500"
                    : "text-neutral-400",
                )}
              />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium truncate text-neutral-900 dark:text-white">
                  {a.name}
                </div>
                <div className="text-[11px] text-neutral-500 dark:text-neutral-400 mt-0.5 flex items-center gap-1.5">
                  <span className="capitalize">{a.status}</span>
                  <span>·</span>
                  <span>
                    {a.personas_detected.length} agent
                    {a.personas_detected.length === 1 ? "" : "s"}
                  </span>
                  <span>·</span>
                  <span>{a.run_count} runs</span>
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Right pane — selected automation */}
      <div className="flex-1 overflow-y-auto">
        {selected ? (
          <AutomationDetail
            key={selected.automation_id}
            automation={selected}
            onEdit={() => setEditing(selected)}
            onDelete={() => handleDelete(selected)}
          />
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-neutral-500 dark:text-neutral-400">
            <Zap className="w-12 h-12 mb-3 opacity-50" />
            <p className="text-sm">
              Select or create an automation to chain your agents.
            </p>
          </div>
        )}
      </div>

      {/* Create dialog */}
      <Dialog
        open={createOpen}
        onClose={() => !submitting && setCreateOpen(false)}
        title="New automation"
        className="max-w-2xl"
      >
        <AutomationBuilder
          onCancel={() => setCreateOpen(false)}
          onSubmit={handleCreate}
          submitting={submitting}
          submitLabel="Create"
        />
      </Dialog>

      {/* Edit dialog */}
      <Dialog
        open={Boolean(editing)}
        onClose={() => !submitting && setEditing(null)}
        title="Edit automation"
        className="max-w-2xl"
      >
        {editing && (
          <AutomationBuilder
            initial={editing}
            onCancel={() => setEditing(null)}
            onSubmit={handleUpdate}
            submitting={submitting}
            submitLabel="Save"
          />
        )}
      </Dialog>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail pane
// ---------------------------------------------------------------------------

function AutomationDetail({
  automation,
  onEdit,
  onDelete,
}: {
  automation: Automation;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const [tab, setTab] = useState<"overview" | "runs">("overview");
  const [runs, setRuns] = useState<AutomationExecution[]>([]);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [running, setRunning] = useState(false);
  const [liveRun, setLiveRun] = useState<AutomationExecution | null>(null);
  const [promoting, setPromoting] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

  const reloadRuns = useCallback(async () => {
    setLoadingRuns(true);
    try {
      const res = await listExecutions(automation.automation_id, 1, 50);
      setRuns(res.executions);
    } finally {
      setLoadingRuns(false);
    }
  }, [automation.automation_id]);

  useEffect(() => {
    if (tab === "runs") reloadRuns();
  }, [tab, reloadRuns]);

  async function handleRun() {
    if (running) return;
    setRunning(true);
    setBanner(null);
    setLiveRun(null);
    try {
      // Kick the run; the engine writes step traces back to the DB row,
      // so we tail the row via SSE for live progress.
      const runPromise = runAutomation(automation.automation_id);
      // Give the engine a beat to create the execution row, then start tailing.
      await new Promise((r) => setTimeout(r, 400));
      const latest = await listExecutions(automation.automation_id, 1, 1);
      const newest = latest.executions[0];
      if (newest && newest.status === "running") {
        const ctrl = new AbortController();
        (async () => {
          try {
            for await (const update of streamExecution(
              newest.execution_id,
              ctrl.signal,
            )) {
              setLiveRun(update);
            }
          } catch {
            // SSE may close when the row reaches terminal state — that's fine.
          }
        })();
        const final = await runPromise;
        ctrl.abort();
        setLiveRun(final);
      } else {
        setLiveRun(await runPromise);
      }
      await reloadRuns();
      setBanner(`Run ${liveRun?.status ?? "completed"}.`);
    } catch (e) {
      setBanner(e instanceof Error ? e.message : "Run failed");
    } finally {
      setRunning(false);
    }
  }

  async function handlePromote() {
    if (promoting) return;
    setPromoting(true);
    setBanner(null);
    try {
      const result = await promoteToCrew(automation.automation_id);
      setBanner(`Promoted to crew ${result.crew_id}. Open Crews to schedule it.`);
    } catch (e) {
      setBanner(e instanceof Error ? e.message : "Promote failed");
    } finally {
      setPromoting(false);
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 px-8 pt-8 pb-4 border-b border-neutral-200 dark:border-neutral-800">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-neutral-900 dark:text-white truncate">
            {automation.name}
          </h1>
          {automation.description && (
            <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
              {automation.description}
            </p>
          )}
          <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-2">
            {automation.personas_detected.length} agent
            {automation.personas_detected.length === 1 ? "" : "s"} ·{" "}
            <span className="capitalize">{automation.execution_mode}</span> ·{" "}
            {automation.run_count} run{automation.run_count === 1 ? "" : "s"}
            {automation.last_run && ` · last run ${automation.last_run}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={handlePromote}
            disabled={promoting}
          >
            {promoting ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Users className="w-3.5 h-3.5" />
            )}
            Promote to crew
          </Button>
          <Button size="sm" variant="ghost" onClick={onEdit}>
            Edit
          </Button>
          <Button size="sm" variant="primary" onClick={handleRun} disabled={running}>
            {running ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Play className="w-3.5 h-3.5" />
            )}
            Run
          </Button>
          <Button size="sm" variant="danger" onClick={onDelete}>
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {banner && (
        <div className="mx-8 mt-4 rounded-xl border border-primary-200 dark:border-primary-700/40 bg-primary-50 dark:bg-primary-500/5 px-4 py-2 text-sm text-primary-700 dark:text-primary-300">
          {banner}
        </div>
      )}

      {/* Tabs */}
      <div className="flex items-center gap-1 px-6 pt-3 border-b border-neutral-200 dark:border-neutral-800">
        {(
          [
            { id: "overview", label: "Overview" },
            { id: "runs", label: "Run history" },
          ] as const
        ).map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "px-4 py-2 text-sm font-medium rounded-t-lg transition-colors",
              tab === t.id
                ? "text-primary-600 dark:text-primary-400 border-b-2 border-primary-500 -mb-px"
                : "text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto px-8 py-6">
        {tab === "overview" && (
          <Overview automation={automation} liveRun={liveRun} />
        )}
        {tab === "runs" && (
          <RunHistory runs={runs} loading={loadingRuns} />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Overview tab
// ---------------------------------------------------------------------------

function Overview({
  automation,
  liveRun,
}: {
  automation: Automation;
  liveRun: AutomationExecution | null;
}) {
  return (
    <div className="space-y-6">
      <Section title="Prompt">
        <pre className="rounded-xl bg-neutral-100 dark:bg-neutral-900 px-4 py-3 text-xs font-mono whitespace-pre-wrap break-words">
          {automation.prompt_template}
        </pre>
      </Section>

      {automation.output_actions && automation.output_actions.length > 0 && (
        <Section title="Output actions">
          <ul className="space-y-1.5">
            {automation.output_actions.map((a, i) => (
              <li
                key={i}
                className="rounded-lg border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 px-3 py-2 text-xs flex items-center gap-2"
              >
                <span className="font-mono text-primary-600 dark:text-primary-400">
                  {a.type}
                </span>
                <span className="text-neutral-500 dark:text-neutral-400 truncate">
                  {summarizeConfig(a.config)}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {liveRun && (
        <Section title="Latest run">
          <RunPanel run={liveRun} />
        </Section>
      )}
    </div>
  );
}

function summarizeConfig(config: Record<string, unknown>): string {
  const keys = Object.keys(config || {}).filter((k) => config[k] !== "" && config[k] != null);
  return keys.map((k) => `${k}: ${String(config[k]).slice(0, 40)}`).join(" · ");
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-neutral-900 dark:text-white mb-2">
        {title}
      </h3>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Run history
// ---------------------------------------------------------------------------

function RunHistory({
  runs,
  loading,
}: {
  runs: AutomationExecution[];
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-neutral-500">
        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading runs…
      </div>
    );
  }
  if (runs.length === 0) {
    return (
      <p className="text-sm text-neutral-500 dark:text-neutral-400">
        No runs yet. Hit Run to fire your first one.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {runs.map((run) => (
        <RunPanel key={run.execution_id} run={run} />
      ))}
    </div>
  );
}

function RunPanel({ run }: { run: AutomationExecution }) {
  const StatusIcon =
    run.status === "success"
      ? CheckCircle2
      : run.status === "failed"
        ? XCircle
        : Clock;
  const statusColor =
    run.status === "success"
      ? "text-emerald-500"
      : run.status === "failed"
        ? "text-red-500"
        : run.status === "partial"
          ? "text-amber-500"
          : "text-sky-500";

  return (
    <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 px-4 py-3">
      <div className="flex items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2">
          <StatusIcon className={cn("w-3.5 h-3.5", statusColor)} />
          <span className="font-medium capitalize">{run.status}</span>
          <span className="text-neutral-500">
            {run.successful_steps}/{run.total_steps} steps
          </span>
          {run.duration_ms != null && (
            <span className="text-neutral-500">· {run.duration_ms}ms</span>
          )}
        </div>
        <span className="text-neutral-500 font-mono">
          {run.execution_id.slice(0, 8)}
        </span>
      </div>
      <div className="mt-2 space-y-1.5">
        {run.steps.map((step) => (
          <div
            key={step.step_number}
            className="text-xs border-l-2 pl-3 py-1"
            style={{
              borderColor:
                step.status === "success"
                  ? "#22c55e"
                  : step.status === "failed"
                    ? "#ef4444"
                    : "#94a3b8",
            }}
          >
            <div className="flex items-center gap-2">
              <span className="font-mono text-primary-600 dark:text-primary-400">
                @{step.persona}
              </span>
              <span className="text-neutral-500">{step.duration_ms}ms</span>
            </div>
            <div className="text-neutral-700 dark:text-neutral-300 mt-0.5">
              {step.instruction}
            </div>
            {step.result && (
              <div className="text-neutral-500 mt-1 line-clamp-3 whitespace-pre-wrap">
                {step.result}
              </div>
            )}
            {step.error && (
              <div className="text-red-500 mt-1">{step.error}</div>
            )}
          </div>
        ))}
      </div>
      {run.output_results && run.output_results.length > 0 && (
        <div className="mt-3 pt-3 border-t border-neutral-200 dark:border-neutral-800 space-y-1">
          <div className="text-[11px] font-medium text-neutral-500 uppercase tracking-wide">
            Outputs
          </div>
          {run.output_results.map((r, i) => (
            <div
              key={i}
              className="text-xs flex items-center gap-2 text-neutral-600 dark:text-neutral-400"
            >
              <span className="font-mono">
                {String((r as Record<string, unknown>).type ?? "?")}
              </span>
              <span>
                {String((r as Record<string, unknown>).status ?? "")}
              </span>
              {(r as Record<string, unknown>).filename ? (
                <span className="truncate">
                  · {String((r as Record<string, unknown>).filename)}
                </span>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
