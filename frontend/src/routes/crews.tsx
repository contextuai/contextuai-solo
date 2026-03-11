import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { crewsApi, type Crew, type CrewRun } from "@/lib/api/crews-client";
import { CrewBuilder } from "@/components/crews/crew-builder";
import {
  Users,
  Play,
  Clock,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Plus,
  Brain,
  Calendar,
  Loader2,
  ChevronRight,
  Zap,
  BarChart3,
  Sparkles,
  Search,
  Filter,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

const RUN_STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  running: {
    label: "Running",
    color: "text-primary-600 dark:text-primary-400",
    bg: "bg-primary-50 dark:bg-primary-500/10",
  },
  completed: {
    label: "Completed",
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-50 dark:bg-green-900/20",
  },
  failed: {
    label: "Failed",
    color: "text-red-600 dark:text-red-400",
    bg: "bg-red-50 dark:bg-red-900/20",
  },
  pending: {
    label: "Pending",
    color: "text-neutral-600 dark:text-neutral-400",
    bg: "bg-neutral-100 dark:bg-neutral-800",
  },
  cancelled: {
    label: "Cancelled",
    color: "text-yellow-600 dark:text-yellow-400",
    bg: "bg-yellow-50 dark:bg-yellow-900/20",
  },
  scheduled: {
    label: "Scheduled",
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-50 dark:bg-blue-900/20",
  },
  active: {
    label: "Active",
    color: "text-green-600 dark:text-green-400",
    bg: "bg-green-50 dark:bg-green-900/20",
  },
  paused: {
    label: "Paused",
    color: "text-yellow-600 dark:text-yellow-400",
    bg: "bg-yellow-50 dark:bg-yellow-900/20",
  },
  idle: {
    label: "Idle",
    color: "text-neutral-600 dark:text-neutral-400",
    bg: "bg-neutral-100 dark:bg-neutral-800",
  },
};

function StatusBadge({ status }: { status: string }) {
  const info = RUN_STATUS_CONFIG[status] ?? RUN_STATUS_CONFIG.idle;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium",
        info.color,
        info.bg
      )}
    >
      {status === "running" && <Loader2 className="w-3 h-3 animate-spin" />}
      {status === "completed" && <CheckCircle2 className="w-3 h-3" />}
      {status === "failed" && <XCircle className="w-3 h-3" />}
      {status === "scheduled" && <Clock className="w-3 h-3" />}
      {info.label}
    </span>
  );
}

const MODE_BADGES: Record<string, { label: string; cls: string; icon: React.ElementType }> = {
  sequential: {
    label: "Sequential",
    cls: "bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400",
    icon: Play,
  },
  parallel: {
    label: "Parallel",
    cls: "bg-purple-50 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400",
    icon: Zap,
  },
  pipeline: {
    label: "Pipeline",
    cls: "bg-teal-50 dark:bg-teal-900/20 text-teal-600 dark:text-teal-400",
    icon: BarChart3,
  },
  autonomous: {
    label: "Autonomous",
    cls: "bg-primary-50 dark:bg-primary-500/10 text-primary-600 dark:text-primary-400",
    icon: Sparkles,
  },
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function CrewsPage() {
  const navigate = useNavigate();

  const [crews, setCrews] = useState<Crew[]>([]);
  const [runs, setRuns] = useState<CrewRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState<"crews" | "runs">("crews");
  const [builderOpen, setBuilderOpen] = useState(false);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [modeFilter, setModeFilter] = useState<string>("all");

  const loadData = useCallback(async () => {
    try {
      const [crewsData, runsData] = await Promise.all([
        crewsApi.list().catch(() => []),
        crewsApi.listRuns(undefined, 50).catch(() => []),
      ]);
      setCrews(crewsData);
      setRuns(runsData);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const handleRunCrew = async (crewId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await crewsApi.startRun(crewId);
      handleRefresh();
    } catch (err) {
      console.error("Failed to start run:", err);
    }
  };

  // Stats
  const runningCount = runs.filter((r) => r.status === "running").length;
  const completedCount = runs.filter((r) => r.status === "completed").length;
  const failedCount = runs.filter((r) => r.status === "failed").length;

  // Filtered crews
  const filteredCrews = crews.filter((crew) => {
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      if (
        !crew.name.toLowerCase().includes(q) &&
        !(crew.description ?? "").toLowerCase().includes(q)
      ) {
        return false;
      }
    }
    if (statusFilter !== "all" && (crew.status || "active") !== statusFilter) return false;
    if (
      modeFilter !== "all" &&
      (crew.execution_config?.mode || "sequential") !== modeFilter
    ) {
      return false;
    }
    return true;
  });

  // Filtered runs
  const filteredRuns = runs.filter((r) => {
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      if (
        !(r.crew_name ?? "").toLowerCase().includes(q) &&
        !r.run_id.toLowerCase().includes(q)
      ) {
        return false;
      }
    }
    return true;
  });

  return (
    <div className="flex flex-col h-full bg-neutral-50 dark:bg-neutral-950">
      {/* Header */}
      <div className="border-b border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary-50 dark:bg-primary-500/10">
              <Users className="w-6 h-6 text-primary-500" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-neutral-900 dark:text-white">
                Crews
              </h1>
              <p className="text-sm text-neutral-500 dark:text-neutral-400">
                {crews.length} crew{crews.length !== 1 ? "s" : ""} &middot;{" "}
                {runs.length} run{runs.length !== 1 ? "s" : ""}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleRefresh}
              className="p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
              title="Refresh"
            >
              <RefreshCw
                className={cn(
                  "w-5 h-5 text-neutral-500",
                  refreshing && "animate-spin"
                )}
              />
            </button>
            <button
              onClick={() => setBuilderOpen(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary-500 text-white hover:bg-primary-600 transition-colors text-sm font-medium"
            >
              <Plus className="w-4 h-4" />
              Create Crew
            </button>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="px-6 py-4">
        <div className="grid grid-cols-4 gap-4">
          <StatCard icon={Users} label="Total Crews" value={crews.length} color="text-neutral-500 dark:text-neutral-400" />
          <StatCard icon={Zap} label="Running" value={runningCount} color="text-primary-500" />
          <StatCard icon={CheckCircle2} label="Completed" value={completedCount} color="text-green-500" />
          <StatCard icon={XCircle} label="Failed" value={failedCount} color="text-red-500" />
        </div>
      </div>

      {/* Search + Filters + Tabs */}
      <div className="px-6 flex flex-col gap-3 mb-4">
        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
          <input
            type="text"
            placeholder={activeTab === "crews" ? "Search crews..." : "Search runs..."}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full max-w-md pl-10 pr-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none transition-colors"
          />
        </div>

        <div className="flex items-center justify-between">
          {/* Tabs */}
          <div className="flex gap-1 bg-neutral-100 dark:bg-neutral-800 rounded-lg p-1 w-fit">
            <button
              onClick={() => setActiveTab("crews")}
              className={cn(
                "px-4 py-2 rounded-md text-sm font-medium transition-colors",
                activeTab === "crews"
                  ? "bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white shadow-sm"
                  : "text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200"
              )}
            >
              <Users className="w-4 h-4 inline mr-1.5" />
              Crews ({crews.length})
            </button>
            <button
              onClick={() => setActiveTab("runs")}
              className={cn(
                "px-4 py-2 rounded-md text-sm font-medium transition-colors",
                activeTab === "runs"
                  ? "bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white shadow-sm"
                  : "text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200"
              )}
            >
              <BarChart3 className="w-4 h-4 inline mr-1.5" />
              Runs ({runs.length})
            </button>
          </div>

          {/* Filters (crews tab only) */}
          {activeTab === "crews" && (
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-neutral-400" />
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="px-2 py-1.5 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-xs focus:ring-2 focus:ring-primary-500/30 outline-none"
              >
                <option value="all">All statuses</option>
                <option value="active">Active</option>
                <option value="paused">Paused</option>
                <option value="archived">Archived</option>
              </select>
              <select
                value={modeFilter}
                onChange={(e) => setModeFilter(e.target.value)}
                className="px-2 py-1.5 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-xs focus:ring-2 focus:ring-primary-500/30 outline-none"
              >
                <option value="all">All modes</option>
                <option value="sequential">Sequential</option>
                <option value="parallel">Parallel</option>
                <option value="pipeline">Pipeline</option>
                <option value="autonomous">Autonomous</option>
              </select>
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 pb-6">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
          </div>
        ) : activeTab === "crews" ? (
          <CrewsList
            crews={filteredCrews}
            onNavigate={(id) => navigate(`/crews/${id}`)}
            onRunCrew={handleRunCrew}
            onCreateCrew={() => setBuilderOpen(true)}
          />
        ) : (
          <RunsList runs={filteredRuns} />
        )}
      </div>

      {/* Crew Builder Modal */}
      <CrewBuilder
        open={builderOpen}
        onClose={() => setBuilderOpen(false)}
        onCreated={handleRefresh}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ElementType;
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="bg-white dark:bg-neutral-900 rounded-xl p-4 border border-neutral-200 dark:border-neutral-800">
      <div className={cn("flex items-center gap-2 text-sm mb-1", color)}>
        <Icon className="w-4 h-4" />
        {label}
      </div>
      <p className="text-2xl font-bold text-neutral-900 dark:text-white">{value}</p>
    </div>
  );
}

function CrewsList({
  crews,
  onNavigate,
  onRunCrew,
  onCreateCrew,
}: {
  crews: Crew[];
  onNavigate: (id: string) => void;
  onRunCrew: (id: string, e: React.MouseEvent) => void;
  onCreateCrew: () => void;
}) {
  if (crews.length === 0) {
    return (
      <div className="text-center py-20">
        <Users className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-neutral-900 dark:text-white mb-2">
          No crews yet
        </h3>
        <p className="text-neutral-500 dark:text-neutral-400 mb-6 text-sm">
          Create your first agent team to get started.
        </p>
        <button
          onClick={onCreateCrew}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary-500 text-white hover:bg-primary-600 transition-colors text-sm font-medium"
        >
          <Plus className="w-4 h-4" />
          Create Crew
        </button>
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      {crews.map((crew) => {
        const mode = crew.execution_config?.mode || "sequential";
        const modeBadge = MODE_BADGES[mode] ?? MODE_BADGES.sequential;
        const ModeIcon = modeBadge.icon;

        return (
          <div
            key={crew.crew_id}
            onClick={() => onNavigate(crew.crew_id)}
            className="bg-white dark:bg-neutral-900 rounded-xl p-5 border border-neutral-200 dark:border-neutral-800 hover:shadow-md hover:border-primary-300 dark:hover:border-primary-700 cursor-pointer transition-all group"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4 min-w-0">
                <div className="p-2.5 rounded-lg bg-primary-50 dark:bg-primary-500/10 group-hover:bg-primary-100 dark:group-hover:bg-primary-500/20 transition-colors flex-shrink-0">
                  <Users className="w-5 h-5 text-primary-500" />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-medium text-neutral-900 dark:text-white truncate">
                      {crew.name}
                    </h3>
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium",
                        modeBadge.cls
                      )}
                    >
                      <ModeIcon className="w-3 h-3" />
                      {modeBadge.label}
                    </span>
                  </div>
                  {crew.description && (
                    <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5 line-clamp-1">
                      {crew.description}
                    </p>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-4 flex-shrink-0">
                <div className="flex items-center gap-4 text-sm text-neutral-500 dark:text-neutral-400">
                  <span className="flex items-center gap-1">
                    <Brain className="w-4 h-4" />
                    {crew.agents?.length || 0} agent{(crew.agents?.length || 0) !== 1 ? "s" : ""}
                  </span>
                  {crew.schedule?.enabled && (
                    <span className="flex items-center gap-1 text-blue-500">
                      <Calendar className="w-4 h-4" />
                      Scheduled
                    </span>
                  )}
                </div>
                <StatusBadge status={crew.status || "active"} />
                <button
                  onClick={(e) => onRunCrew(crew.crew_id, e)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-500/10 hover:bg-primary-100 dark:hover:bg-primary-500/20 transition-colors"
                  title="Run now"
                >
                  <Play className="w-3.5 h-3.5" />
                  Run
                </button>
                <ChevronRight className="w-5 h-5 text-neutral-400 group-hover:text-primary-500 transition-colors" />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function RunsList({ runs }: { runs: CrewRun[] }) {
  if (runs.length === 0) {
    return (
      <div className="text-center py-20">
        <BarChart3 className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-neutral-900 dark:text-white mb-2">
          No runs yet
        </h3>
        <p className="text-neutral-500 dark:text-neutral-400 text-sm">
          Start a crew run to see execution history here.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      {runs.map((run) => (
        <div
          key={run.run_id}
          className="bg-white dark:bg-neutral-900 rounded-xl p-4 border border-neutral-200 dark:border-neutral-800 hover:shadow-sm transition-all"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <StatusBadge status={run.status} />
              <div>
                <span className="text-sm font-medium text-neutral-900 dark:text-white">
                  {run.crew_name || run.crew_id.slice(0, 8)}
                </span>
                <span className="text-xs text-neutral-400 ml-2">
                  {run.run_id.slice(0, 8)}...
                </span>
              </div>
            </div>
            <div className="flex items-center gap-4 text-sm text-neutral-500 dark:text-neutral-400">
              {run.phases_completed != null && run.total_phases != null && (
                <span>
                  {run.phases_completed}/{run.total_phases} phases
                </span>
              )}
              {run.duration_seconds != null && (
                <span className="flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  {run.duration_seconds}s
                </span>
              )}
              {run.cost_usd != null && (
                <span className="text-green-600 dark:text-green-400 font-medium">
                  ${run.cost_usd.toFixed(4)}
                </span>
              )}
              <span className="text-xs">
                {new Date(run.created_at).toLocaleDateString()}
              </span>
            </div>
          </div>
          {run.error && (
            <p className="mt-2 text-sm text-red-500 bg-red-50 dark:bg-red-900/20 rounded px-3 py-1.5">
              {run.error}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
