import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { crewsApi, type Crew, type CrewRun } from "@/lib/api/crews-client";
import { CrewBuilder } from "@/components/crews/crew-builder";
import { CrewRunProgress } from "@/components/crews/crew-run-progress";
import {
  ArrowLeft,
  Users,
  Brain,
  Play,
  Clock,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Loader2,
  Calendar,
  Zap,
  Shield,
  DollarSign,
  Sparkles,
  Settings,
  Trash2,
  Pencil,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  running: { label: "Running", color: "text-primary-600 dark:text-primary-400", bg: "bg-primary-50 dark:bg-primary-500/10" },
  completed: { label: "Completed", color: "text-green-600 dark:text-green-400", bg: "bg-green-50 dark:bg-green-900/20" },
  failed: { label: "Failed", color: "text-red-600 dark:text-red-400", bg: "bg-red-50 dark:bg-red-900/20" },
  pending: { label: "Pending", color: "text-neutral-600 dark:text-neutral-400", bg: "bg-neutral-100 dark:bg-neutral-800" },
  cancelled: { label: "Cancelled", color: "text-yellow-600 dark:text-yellow-400", bg: "bg-yellow-50 dark:bg-yellow-900/20" },
  scheduled: { label: "Scheduled", color: "text-blue-600 dark:text-blue-400", bg: "bg-blue-50 dark:bg-blue-900/20" },
  active: { label: "Active", color: "text-green-600 dark:text-green-400", bg: "bg-green-50 dark:bg-green-900/20" },
  paused: { label: "Paused", color: "text-yellow-600 dark:text-yellow-400", bg: "bg-yellow-50 dark:bg-yellow-900/20" },
  idle: { label: "Idle", color: "text-neutral-600 dark:text-neutral-400", bg: "bg-neutral-100 dark:bg-neutral-800" },
};

function StatusBadge({ status }: { status: string }) {
  const info = STATUS_CONFIG[status] ?? STATUS_CONFIG.idle;
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium", info.color, info.bg)}>
      {status === "running" && <Loader2 className="w-3 h-3 animate-spin" />}
      {status === "completed" && <CheckCircle2 className="w-3 h-3" />}
      {status === "failed" && <XCircle className="w-3 h-3" />}
      {status === "scheduled" && <Clock className="w-3 h-3" />}
      {info.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function CrewDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [crew, setCrew] = useState<Crew | null>(null);
  const [runs, setRuns] = useState<CrewRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"overview" | "runs" | "schedule">("overview");
  const [editorOpen, setEditorOpen] = useState(false);
  const [activeRunView, setActiveRunView] = useState<{ crewId: string; runId: string } | null>(null);

  const loadData = useCallback(async () => {
    if (!id) return;
    try {
      setError(null);
      const [crewData, runsData] = await Promise.all([
        crewsApi.get(id),
        crewsApi.listRuns(id, 50).catch(() => []),
      ]);
      setCrew(crewData);
      setRuns(runsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load crew");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [id]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const handleStartRun = async () => {
    if (!id) return;
    try {
      const run = await crewsApi.startRun(id);
      setActiveRunView({ crewId: id, runId: run.run_id });
      handleRefresh();
    } catch (err) {
      console.error("Failed to start run:", err);
    }
  };

  const handleDelete = async () => {
    if (!id || !confirm("Are you sure you want to delete this crew?")) return;
    try {
      await crewsApi.delete(id);
      navigate("/crews");
    } catch (err) {
      console.error("Failed to delete crew:", err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full bg-neutral-50 dark:bg-neutral-950">
        <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
      </div>
    );
  }

  if (error || !crew) {
    return (
      <div className="flex items-center justify-center h-full bg-neutral-50 dark:bg-neutral-950">
        <div className="text-center">
          <XCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
          <h2 className="text-lg font-medium text-neutral-900 dark:text-white mb-2">
            Crew not found
          </h2>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-6">
            {error || "This crew does not exist."}
          </p>
          <button
            onClick={() => navigate("/crews")}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary-500 text-white hover:bg-primary-600 transition-colors text-sm font-medium"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Crews
          </button>
        </div>
      </div>
    );
  }

  const isAutonomous = crew.execution_config?.mode === "autonomous";
  const completedRuns = runs.filter((r) => r.status === "completed").length;
  const failedRuns = runs.filter((r) => r.status === "failed").length;

  return (
    <div className="flex flex-col h-full bg-neutral-50 dark:bg-neutral-950">
      {/* Header */}
      <div className="border-b border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate("/crews")}
              className="p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
            >
              <ArrowLeft className="w-5 h-5 text-neutral-500" />
            </button>
            <div className="p-2 rounded-lg bg-primary-50 dark:bg-primary-500/10">
              <Users className="w-6 h-6 text-primary-500" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-semibold text-neutral-900 dark:text-white">
                  {crew.name}
                </h1>
                {isAutonomous && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400">
                    <Sparkles className="w-3 h-3" />
                    Autonomous
                  </span>
                )}
                <StatusBadge status={crew.status || "active"} />
              </div>
              {crew.description && (
                <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
                  {crew.description}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              className="p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
            >
              <RefreshCw className={cn("w-5 h-5 text-neutral-500", refreshing && "animate-spin")} />
            </button>
            <button
              onClick={() => setEditorOpen(true)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
            >
              <Pencil className="w-4 h-4" />
              Edit
            </button>
            <button
              onClick={handleStartRun}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary-500 text-white hover:bg-primary-600 transition-colors text-sm font-medium"
            >
              <Play className="w-4 h-4" />
              Run Crew
            </button>
            <button
              onClick={handleDelete}
              className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
              title="Delete crew"
            >
              <Trash2 className="w-5 h-5 text-red-400 hover:text-red-500" />
            </button>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="px-6 py-4">
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-white dark:bg-neutral-900 rounded-xl p-4 border border-neutral-200 dark:border-neutral-800">
            <div className="flex items-center gap-2 text-neutral-500 dark:text-neutral-400 text-sm mb-1">
              {isAutonomous ? <Sparkles className="w-4 h-4" /> : <Brain className="w-4 h-4" />}
              {isAutonomous ? "Mode" : "Agents"}
            </div>
            <p className="text-2xl font-bold text-neutral-900 dark:text-white">
              {isAutonomous ? "Auto" : crew.agents?.length || 0}
            </p>
          </div>
          <div className="bg-white dark:bg-neutral-900 rounded-xl p-4 border border-neutral-200 dark:border-neutral-800">
            <div className="flex items-center gap-2 text-blue-500 text-sm mb-1">
              <Play className="w-4 h-4" />
              Total Runs
            </div>
            <p className="text-2xl font-bold text-neutral-900 dark:text-white">{runs.length}</p>
          </div>
          <div className="bg-white dark:bg-neutral-900 rounded-xl p-4 border border-neutral-200 dark:border-neutral-800">
            <div className="flex items-center gap-2 text-green-500 text-sm mb-1">
              <CheckCircle2 className="w-4 h-4" />
              Completed
            </div>
            <p className="text-2xl font-bold text-neutral-900 dark:text-white">{completedRuns}</p>
          </div>
          <div className="bg-white dark:bg-neutral-900 rounded-xl p-4 border border-neutral-200 dark:border-neutral-800">
            <div className="flex items-center gap-2 text-red-500 text-sm mb-1">
              <XCircle className="w-4 h-4" />
              Failed
            </div>
            <p className="text-2xl font-bold text-neutral-900 dark:text-white">{failedRuns}</p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="px-6 mb-4">
        <div className="flex gap-1 bg-neutral-100 dark:bg-neutral-800 rounded-lg p-1 w-fit">
          {(["overview", "runs", "schedule"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                "px-4 py-2 rounded-md text-sm font-medium transition-colors capitalize",
                activeTab === tab
                  ? "bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white shadow-sm"
                  : "text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200"
              )}
            >
              {tab === "overview" && <Settings className="w-4 h-4 inline mr-1.5" />}
              {tab === "runs" && <Play className="w-4 h-4 inline mr-1.5" />}
              {tab === "schedule" && <Calendar className="w-4 h-4 inline mr-1.5" />}
              {tab} {tab === "runs" ? `(${runs.length})` : ""}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto px-6 pb-6">
        {activeTab === "overview" && (
          <OverviewTab crew={crew} isAutonomous={isAutonomous} />
        )}
        {activeTab === "runs" && (
          <RunsTab
            runs={runs}
            crewId={crew.crew_id}
            onStartRun={handleStartRun}
            onViewRun={(runId) => setActiveRunView({ crewId: crew.crew_id, runId })}
          />
        )}
        {activeTab === "schedule" && <ScheduleTab crew={crew} />}
      </div>

      {/* Crew Editor */}
      {editorOpen && (
        <CrewBuilder
          open={editorOpen}
          onClose={() => setEditorOpen(false)}
          onCreated={handleRefresh}
          editCrew={{
            crew_id: crew.crew_id,
            name: crew.name,
            description: crew.description,
            execution_config: crew.execution_config as {
              mode: "sequential" | "parallel" | "pipeline" | "autonomous";
              max_agent_invocations?: number;
              budget_limit_usd?: number;
            },
            agents: crew.agents,
          }}
        />
      )}

      {/* Run Progress */}
      {activeRunView && (
        <CrewRunProgress
          crewId={activeRunView.crewId}
          runId={activeRunView.runId}
          onClose={() => {
            setActiveRunView(null);
            handleRefresh();
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Overview
// ---------------------------------------------------------------------------

function OverviewTab({ crew, isAutonomous }: { crew: Crew; isAutonomous: boolean }) {
  return (
    <div className="grid gap-6 md:grid-cols-2">
      {/* Configuration */}
      <div className="bg-white dark:bg-neutral-900 rounded-xl p-5 border border-neutral-200 dark:border-neutral-800">
        <h3 className="font-medium text-neutral-900 dark:text-white mb-4 flex items-center gap-2">
          <Settings className="w-4 h-4 text-neutral-400" />
          Configuration
        </h3>
        <div className="space-y-3 text-sm">
          <div className="flex justify-between">
            <span className="text-neutral-500 dark:text-neutral-400">Execution Mode</span>
            <span className="font-medium text-neutral-900 dark:text-white capitalize">
              {crew.execution_config?.mode || "sequential"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-neutral-500 dark:text-neutral-400">Timeout</span>
            <span className="font-medium text-neutral-900 dark:text-white">
              {crew.execution_config?.timeout_seconds || 600}s
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-neutral-500 dark:text-neutral-400">Max Iterations</span>
            <span className="font-medium text-neutral-900 dark:text-white">
              {crew.execution_config?.max_iterations || 1}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-neutral-500 dark:text-neutral-400">Created</span>
            <span className="font-medium text-neutral-900 dark:text-white">
              {crew.created_at ? new Date(crew.created_at).toLocaleDateString() : "N/A"}
            </span>
          </div>
        </div>
      </div>

      {/* Autonomous Safety Limits */}
      {isAutonomous && (
        <div className="bg-white dark:bg-neutral-900 rounded-xl p-5 border border-purple-200 dark:border-purple-800/50">
          <h3 className="font-medium text-neutral-900 dark:text-white mb-4 flex items-center gap-2">
            <Shield className="w-4 h-4 text-purple-500" />
            Autonomous Safety Limits
          </h3>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-neutral-500 dark:text-neutral-400 flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5" />
                Max Agent Invocations
              </span>
              <span className="font-medium text-neutral-900 dark:text-white">
                {crew.execution_config?.max_agent_invocations || 10}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-neutral-500 dark:text-neutral-400 flex items-center gap-1.5">
                <DollarSign className="w-3.5 h-3.5" />
                Budget Limit
              </span>
              <span className="font-medium text-neutral-900 dark:text-white">
                ${(crew.execution_config?.budget_limit_usd || 1).toFixed(2)}
              </span>
            </div>
          </div>
          <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-4">
            The coordinator will dynamically discover and invoke specialist agents within these limits.
          </p>
        </div>
      )}

      {/* Agents */}
      {!isAutonomous && crew.agents && crew.agents.length > 0 && (
        <div className="bg-white dark:bg-neutral-900 rounded-xl p-5 border border-neutral-200 dark:border-neutral-800 md:col-span-2">
          <h3 className="font-medium text-neutral-900 dark:text-white mb-4 flex items-center gap-2">
            <Brain className="w-4 h-4 text-neutral-400" />
            Agent Pipeline ({crew.agents.length})
          </h3>

          {/* Visual pipeline */}
          <div className="flex items-center gap-1 mb-4 overflow-x-auto pb-2">
            {crew.agents.map((agent, i) => (
              <div key={agent.agent_id || i} className="flex items-center gap-1 flex-shrink-0">
                <div className="px-3 py-1.5 rounded-lg text-xs font-medium border border-primary-200 dark:border-primary-800 bg-primary-50 dark:bg-primary-500/10 text-primary-700 dark:text-primary-400">
                  {(agent as unknown as Record<string, string>).name || `Agent ${i + 1}`}
                </div>
                {i < crew.agents!.length - 1 && (
                  <span className="text-neutral-300 dark:text-neutral-600 text-xs">
                    &rarr;
                  </span>
                )}
              </div>
            ))}
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            {crew.agents.map((agent, i) => (
              <div
                key={agent.agent_id || i}
                className="p-3 rounded-lg border border-neutral-100 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-800/50"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-sm text-neutral-900 dark:text-white">
                    {(agent as unknown as Record<string, string>).name || `Agent ${i + 1}`}
                  </span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-neutral-100 dark:bg-neutral-700 text-neutral-500 dark:text-neutral-400 uppercase">
                    {agent.role}
                  </span>
                  {agent.library_agent_id && (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-primary-50 dark:bg-primary-500/10 text-primary-500">
                      Library
                    </span>
                  )}
                </div>
                {agent.instructions && (
                  <p className="text-xs text-neutral-500 dark:text-neutral-400 line-clamp-2 mt-1">
                    {agent.instructions}
                  </p>
                )}
                {agent.tools && agent.tools.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {agent.tools.map((tool) => (
                      <span
                        key={tool}
                        className="px-1.5 py-0.5 rounded text-[10px] bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400"
                      >
                        {tool}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tags */}
      {crew.tags && crew.tags.length > 0 && (
        <div className="bg-white dark:bg-neutral-900 rounded-xl p-5 border border-neutral-200 dark:border-neutral-800">
          <h3 className="font-medium text-neutral-900 dark:text-white mb-3">Tags</h3>
          <div className="flex flex-wrap gap-2">
            {crew.tags.map((tag) => (
              <span
                key={tag}
                className="px-2.5 py-1 rounded-full text-xs font-medium bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400"
              >
                {tag}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Runs
// ---------------------------------------------------------------------------

function RunsTab({
  runs,
  crewId: _crewId,
  onStartRun,
  onViewRun,
}: {
  runs: CrewRun[];
  crewId: string;
  onStartRun: () => void;
  onViewRun: (runId: string) => void;
}) {
  if (runs.length === 0) {
    return (
      <div className="text-center py-20">
        <Play className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-neutral-900 dark:text-white mb-2">
          No runs yet
        </h3>
        <p className="text-neutral-500 dark:text-neutral-400 mb-6 text-sm">
          Start a run to execute this crew.
        </p>
        <button
          onClick={onStartRun}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary-500 text-white hover:bg-primary-600 transition-colors text-sm font-medium"
        >
          <Play className="w-4 h-4" />
          Run Crew
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* Table header */}
      <div className="grid grid-cols-6 gap-4 px-4 py-2 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
        <span>Status</span>
        <span>Run ID</span>
        <span>Progress</span>
        <span>Duration</span>
        <span>Cost</span>
        <span>Date</span>
      </div>

      {runs.map((run) => (
        <button
          key={run.run_id}
          onClick={() => onViewRun(run.run_id)}
          className="w-full grid grid-cols-6 gap-4 px-4 py-3 bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-800 hover:shadow-sm hover:border-primary-300 dark:hover:border-primary-700 transition-all text-left text-sm"
        >
          <div>
            <StatusBadge status={run.status} />
          </div>
          <div className="text-neutral-900 dark:text-white font-mono text-xs self-center">
            {run.run_id.slice(0, 12)}...
          </div>
          <div className="text-neutral-500 dark:text-neutral-400 self-center">
            {run.phases_completed != null && run.total_phases != null
              ? `${run.phases_completed}/${run.total_phases}`
              : "--"}
          </div>
          <div className="text-neutral-500 dark:text-neutral-400 self-center flex items-center gap-1">
            {run.duration_seconds != null ? (
              <>
                <Clock className="w-3 h-3" />
                {run.duration_seconds}s
              </>
            ) : (
              "--"
            )}
          </div>
          <div className="self-center">
            {run.cost_usd != null ? (
              <span className="text-green-600 dark:text-green-400 font-medium">
                ${run.cost_usd.toFixed(4)}
              </span>
            ) : (
              <span className="text-neutral-400">--</span>
            )}
          </div>
          <div className="text-neutral-500 dark:text-neutral-400 self-center text-xs">
            {new Date(run.created_at).toLocaleString()}
          </div>
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Schedule
// ---------------------------------------------------------------------------

function ScheduleTab({ crew }: { crew: Crew }) {
  const schedule = crew.schedule;

  if (!schedule?.enabled) {
    return (
      <div className="text-center py-20">
        <Calendar className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-neutral-900 dark:text-white mb-2">
          No schedule configured
        </h3>
        <p className="text-neutral-500 dark:text-neutral-400 text-sm">
          This crew runs on-demand. You can configure a schedule to automate execution.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-lg">
      <div className="bg-white dark:bg-neutral-900 rounded-xl p-5 border border-neutral-200 dark:border-neutral-800 space-y-4">
        <h3 className="font-medium text-neutral-900 dark:text-white flex items-center gap-2">
          <Calendar className="w-4 h-4 text-blue-500" />
          Schedule
        </h3>
        <div className="space-y-3 text-sm">
          <div className="flex justify-between">
            <span className="text-neutral-500 dark:text-neutral-400">Status</span>
            <span className="font-medium text-green-600 dark:text-green-400">
              Enabled
            </span>
          </div>
          {schedule.cron_expression && (
            <div className="flex justify-between">
              <span className="text-neutral-500 dark:text-neutral-400">Cron Expression</span>
              <code className="font-mono text-xs bg-neutral-100 dark:bg-neutral-800 px-2 py-0.5 rounded text-neutral-700 dark:text-neutral-300">
                {schedule.cron_expression}
              </code>
            </div>
          )}
          {schedule.timezone && (
            <div className="flex justify-between">
              <span className="text-neutral-500 dark:text-neutral-400">Timezone</span>
              <span className="font-medium text-neutral-900 dark:text-white">
                {schedule.timezone}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
