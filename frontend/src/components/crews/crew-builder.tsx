import { useState } from "react";
import { cn } from "@/lib/utils";
import { crewsApi, type CrewAgent } from "@/lib/api/crews-client";
import {
  Users,
  Plus,
  Trash2,
  Loader2,
  Brain,
  AlertCircle,
  ArrowRightLeft,
  Layers,
  GitBranch,
  Sparkles,
  Shield,
  DollarSign,
  X,
  GripVertical,
  ArrowRight,
} from "lucide-react";

type ExecutionMode = "sequential" | "parallel" | "pipeline" | "autonomous";

interface AgentForm {
  name: string;
  role: string;
  instructions: string;
}

function emptyAgent(): AgentForm {
  return { name: "", role: "custom", instructions: "" };
}

const EXECUTION_MODES: {
  mode: ExecutionMode;
  label: string;
  description: string;
  icon: React.ElementType;
}[] = [
  {
    mode: "sequential",
    label: "Sequential",
    description: "Agents run one after another, passing output forward",
    icon: ArrowRightLeft,
  },
  {
    mode: "parallel",
    label: "Parallel",
    description: "All agents run at the same time independently",
    icon: Layers,
  },
  {
    mode: "pipeline",
    label: "Pipeline",
    description: "Agents run in dependency-ordered stages",
    icon: GitBranch,
  },
  {
    mode: "autonomous",
    label: "Autonomous",
    description: "A coordinator discovers and invokes agents dynamically",
    icon: Sparkles,
  },
];

const ROLE_OPTIONS = [
  "custom",
  "researcher",
  "analyst",
  "writer",
  "reviewer",
  "coordinator",
  "coder",
];

interface CrewBuilderProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  /** When provided the builder is in edit mode */
  editCrew?: {
    crew_id: string;
    name: string;
    description?: string;
    execution_config?: { mode: ExecutionMode; max_agent_invocations?: number; budget_limit_usd?: number };
    agents?: CrewAgent[];
  };
}

export function CrewBuilder({ open, onClose, onCreated, editCrew }: CrewBuilderProps) {
  const isEdit = !!editCrew;

  const [name, setName] = useState(editCrew?.name ?? "");
  const [description, setDescription] = useState(editCrew?.description ?? "");
  const [executionMode, setExecutionMode] = useState<ExecutionMode>(
    editCrew?.execution_config?.mode ?? "sequential"
  );
  const [agents, setAgents] = useState<AgentForm[]>(
    editCrew?.agents?.map((a) => ({
      name: a.name,
      role: a.role,
      instructions: a.instructions ?? "",
    })) ?? [emptyAgent()]
  );
  const [maxInvocations, setMaxInvocations] = useState(
    editCrew?.execution_config?.max_agent_invocations ?? 10
  );
  const [budgetLimit, setBudgetLimit] = useState(
    editCrew?.execution_config?.budget_limit_usd ?? 1.0
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isAutonomous = executionMode === "autonomous";

  const canSubmit = isAutonomous
    ? !!name.trim()
    : name.trim() && agents.every((a) => a.name.trim() && a.instructions.trim());

  const updateAgent = (index: number, field: keyof AgentForm, value: string) => {
    setAgents((prev) => prev.map((a, i) => (i === index ? { ...a, [field]: value } : a)));
  };

  const addAgent = () => setAgents((prev) => [...prev, emptyAgent()]);

  const removeAgent = (index: number) => {
    if (agents.length <= 1) return;
    setAgents((prev) => prev.filter((_, i) => i !== index));
  };

  const moveAgent = (from: number, direction: "up" | "down") => {
    const to = direction === "up" ? from - 1 : from + 1;
    if (to < 0 || to >= agents.length) return;
    setAgents((prev) => {
      const next = [...prev];
      [next[from], next[to]] = [next[to], next[from]];
      return next;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    setSubmitting(true);
    setError(null);

    try {
      const payload: Record<string, unknown> = {
        name: name.trim(),
        description: description.trim() || undefined,
        execution_config: {
          mode: executionMode,
          ...(isAutonomous && {
            max_agent_invocations: maxInvocations,
            budget_limit_usd: budgetLimit,
          }),
        },
      };

      if (isAutonomous) {
        payload.agents = [];
      } else {
        payload.agents = agents.map((a, i) => ({
          agent_id: `agent-${i}`,
          role: a.role || "custom",
          name: a.name.trim(),
          instructions: a.instructions.trim(),
          order: i,
        }));
      }

      if (isEdit && editCrew) {
        await crewsApi.update(editCrew.crew_id, payload);
      } else {
        await crewsApi.create(payload);
      }
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save crew");
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-3xl max-h-[90vh] bg-white dark:bg-neutral-900 rounded-2xl shadow-2xl border border-neutral-200 dark:border-neutral-700 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-800">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary-50 dark:bg-primary-500/10">
              <Users className="w-5 h-5 text-primary-500" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
                {isEdit ? "Edit Crew" : "Create New Crew"}
              </h2>
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                Configure a multi-agent team with roles and instructions
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
          >
            <X className="w-5 h-5 text-neutral-500" />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 text-sm">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          {/* Name & Description */}
          <div className="bg-neutral-50 dark:bg-neutral-800/50 rounded-xl border border-neutral-200 dark:border-neutral-700 p-5 space-y-4">
            <h3 className="text-sm font-medium text-neutral-900 dark:text-white flex items-center gap-2">
              <Users className="w-4 h-4 text-primary-500" />
              Crew Details
            </h3>
            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Crew Name <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g., Research & Analysis Team"
                maxLength={200}
                className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none transition-colors"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Description
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What does this crew do?"
                rows={2}
                maxLength={2000}
                className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none transition-colors resize-none"
              />
            </div>
          </div>

          {/* Execution Mode */}
          <div className="bg-neutral-50 dark:bg-neutral-800/50 rounded-xl border border-neutral-200 dark:border-neutral-700 p-5 space-y-4">
            <h3 className="text-sm font-medium text-neutral-900 dark:text-white flex items-center gap-2">
              <Layers className="w-4 h-4 text-primary-500" />
              Execution Mode
            </h3>
            <div className="grid grid-cols-2 gap-3">
              {EXECUTION_MODES.map(({ mode, label, description: desc, icon: Icon }) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setExecutionMode(mode)}
                  className={cn(
                    "relative p-4 rounded-xl border-2 text-left transition-all",
                    executionMode === mode
                      ? "border-primary-500 bg-primary-50 dark:bg-primary-500/5"
                      : "border-neutral-200 dark:border-neutral-700 hover:border-neutral-300 dark:hover:border-neutral-600"
                  )}
                >
                  <div className="flex items-center gap-2 mb-1.5">
                    <Icon
                      className={cn(
                        "w-4 h-4",
                        executionMode === mode ? "text-primary-500" : "text-neutral-400"
                      )}
                    />
                    <span
                      className={cn(
                        "text-sm font-medium",
                        executionMode === mode
                          ? "text-primary-500"
                          : "text-neutral-900 dark:text-white"
                      )}
                    >
                      {label}
                    </span>
                  </div>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400">{desc}</p>
                  {executionMode === mode && (
                    <div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-primary-500" />
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Autonomous Safety Limits */}
          {isAutonomous && (
            <div className="bg-neutral-50 dark:bg-neutral-800/50 rounded-xl border border-neutral-200 dark:border-neutral-700 p-5 space-y-4">
              <h3 className="text-sm font-medium text-neutral-900 dark:text-white flex items-center gap-2">
                <Shield className="w-4 h-4 text-primary-500" />
                Autonomous Safety Limits
              </h3>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 -mt-2">
                The coordinator agent will dynamically discover and invoke specialist agents.
                These limits prevent runaway costs.
              </p>
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <label className="flex items-center gap-1.5 text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                    <Brain className="w-3.5 h-3.5" />
                    Max Agent Invocations
                  </label>
                  <input
                    type="number"
                    value={maxInvocations}
                    onChange={(e) =>
                      setMaxInvocations(
                        Math.max(1, Math.min(50, parseInt(e.target.value) || 1))
                      )
                    }
                    min={1}
                    max={50}
                    className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none transition-colors"
                  />
                  <p className="text-xs text-neutral-400 mt-1">1-50 agents per run</p>
                </div>
                <div>
                  <label className="flex items-center gap-1.5 text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                    <DollarSign className="w-3.5 h-3.5" />
                    Budget Limit (USD)
                  </label>
                  <input
                    type="number"
                    value={budgetLimit}
                    onChange={(e) =>
                      setBudgetLimit(
                        Math.max(0.01, Math.min(100, parseFloat(e.target.value) || 0.01))
                      )
                    }
                    min={0.01}
                    max={100}
                    step={0.01}
                    className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none transition-colors"
                  />
                  <p className="text-xs text-neutral-400 mt-1">$0.01 - $100.00 per run</p>
                </div>
              </div>
            </div>
          )}

          {/* Agents (non-autonomous) */}
          {!isAutonomous && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium text-neutral-900 dark:text-white flex items-center gap-2">
                  <Brain className="w-4 h-4 text-primary-500" />
                  Agent Pipeline ({agents.length})
                </h3>
                <button
                  type="button"
                  onClick={addAgent}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-primary-500 hover:bg-primary-50 dark:hover:bg-primary-500/10 transition-colors"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Add Agent
                </button>
              </div>

              {/* Pipeline visualization */}
              <div className="flex items-center gap-1 px-2 py-2 overflow-x-auto">
                {agents.map((agent, i) => (
                  <div key={i} className="flex items-center gap-1 flex-shrink-0">
                    <div
                      className={cn(
                        "px-3 py-1.5 rounded-lg text-xs font-medium border",
                        agent.name.trim()
                          ? "border-primary-200 dark:border-primary-800 bg-primary-50 dark:bg-primary-500/10 text-primary-700 dark:text-primary-400"
                          : "border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-neutral-400"
                      )}
                    >
                      {agent.name.trim() || `Agent ${i + 1}`}
                    </div>
                    {i < agents.length - 1 && (
                      <ArrowRight className="w-3.5 h-3.5 text-neutral-300 dark:text-neutral-600 flex-shrink-0" />
                    )}
                  </div>
                ))}
              </div>

              {/* Agent cards */}
              {agents.map((agent, index) => (
                <div
                  key={index}
                  className="bg-neutral-50 dark:bg-neutral-800/50 rounded-xl border border-neutral-200 dark:border-neutral-700 p-5 space-y-4"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <GripVertical className="w-4 h-4 text-neutral-300 dark:text-neutral-600" />
                      <span className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
                        Agent {index + 1}
                      </span>
                      <div className="flex gap-1">
                        <button
                          type="button"
                          onClick={() => moveAgent(index, "up")}
                          disabled={index === 0}
                          className="p-1 rounded text-neutral-400 hover:text-neutral-600 disabled:opacity-30 transition-colors text-xs"
                          title="Move up"
                        >
                          &#9650;
                        </button>
                        <button
                          type="button"
                          onClick={() => moveAgent(index, "down")}
                          disabled={index === agents.length - 1}
                          className="p-1 rounded text-neutral-400 hover:text-neutral-600 disabled:opacity-30 transition-colors text-xs"
                          title="Move down"
                        >
                          &#9660;
                        </button>
                      </div>
                    </div>
                    {agents.length > 1 && (
                      <button
                        type="button"
                        onClick={() => removeAgent(index)}
                        className="p-1.5 rounded-lg text-neutral-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                        Agent Name <span className="text-red-500">*</span>
                      </label>
                      <input
                        type="text"
                        value={agent.name}
                        onChange={(e) => updateAgent(index, "name", e.target.value)}
                        placeholder="e.g., Researcher"
                        maxLength={100}
                        className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none transition-colors"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                        Role
                      </label>
                      <select
                        value={agent.role}
                        onChange={(e) => updateAgent(index, "role", e.target.value)}
                        className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none transition-colors"
                      >
                        {ROLE_OPTIONS.map((r) => (
                          <option key={r} value={r}>
                            {r.charAt(0).toUpperCase() + r.slice(1)}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                      Instructions <span className="text-red-500">*</span>
                    </label>
                    <textarea
                      value={agent.instructions}
                      onChange={(e) => updateAgent(index, "instructions", e.target.value)}
                      placeholder="What should this agent do? Provide clear instructions..."
                      rows={3}
                      className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none transition-colors resize-none"
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </form>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-neutral-200 dark:border-neutral-800">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit as unknown as React.MouseEventHandler}
            disabled={!canSubmit || submitting}
            className="flex items-center gap-2 px-5 py-2 rounded-lg bg-primary-500 text-white hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm font-medium"
          >
            {submitting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            {isEdit ? "Save Changes" : "Create Crew"}
          </button>
        </div>
      </div>
    </div>
  );
}
