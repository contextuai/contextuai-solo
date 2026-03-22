import { useState, useEffect, useCallback, useRef } from "react";
import { cn } from "@/lib/utils";
import { crewsApi, type CrewAgent, type LibraryAgent } from "@/lib/api/crews-client";
import {
  BlueprintSelector,
  type BlueprintSelection,
} from "@/components/blueprints/blueprint-selector";
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
  ArrowLeft,
  BookOpen,
  Search,
  ChevronDown,
  Check,
  Eye,
} from "lucide-react";

type ExecutionMode = "sequential" | "parallel" | "pipeline" | "autonomous";
type WizardStep = 1 | 2 | 3 | 4;

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

// ---------------------------------------------------------------------------
// Category colors for badges
// ---------------------------------------------------------------------------
const CATEGORY_COLORS: Record<string, string> = {
  marketing: "bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-400",
  sales: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  finance: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  engineering: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  operations: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  hr: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  legal: "bg-slate-100 text-slate-700 dark:bg-slate-900/30 dark:text-slate-400",
  support: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400",
  product: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400",
  data: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
};

function categoryBadgeClass(category: string) {
  return CATEGORY_COLORS[category] ?? "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400";
}

// ---------------------------------------------------------------------------
// Library Panel (overlay inside crew builder)
// ---------------------------------------------------------------------------
function LibraryPanel({
  open,
  onClose,
  onSelect,
}: {
  open: boolean;
  onClose: () => void;
  onSelect: (agent: LibraryAgent) => void;
}) {
  const [agents, setAgents] = useState<LibraryAgent[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [categories, setCategories] = useState<string[]>([]);
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const pageSize = 20;
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);

  const fetchAgents = useCallback(
    async (p: number, searchTerm: string, cat: string) => {
      setLoading(true);
      try {
        const res = await crewsApi.listLibraryAgents({
          page: p,
          page_size: pageSize,
          search: searchTerm || undefined,
          category: cat || undefined,
        });
        setAgents(res.agents);
        setTotalCount(res.total_count);
        if (!cat && !searchTerm && p === 1 && res.agents.length > 0) {
          setCategories((prev) => {
            const cats = new Set(prev);
            res.agents.forEach((a) => cats.add(a.category));
            return Array.from(cats).sort();
          });
        }
      } catch {
        // silent
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    if (open) {
      setPage(1);
      fetchAgents(1, search, category);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (open && categories.length === 0) {
      crewsApi
        .listLibraryAgents({ page: 1, page_size: 100 })
        .then((res) => {
          const cats = Array.from(new Set(res.agents.map((a) => a.category))).sort();
          setCategories(cats);
        })
        .catch(() => {});
    }
  }, [open, categories.length]);

  const handleSearch = (value: string) => {
    setSearch(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setPage(1);
      fetchAgents(1, value, category);
    }, 300);
  };

  const handleCategory = (cat: string) => {
    setCategory(cat);
    setPage(1);
    fetchAgents(1, search, cat);
  };

  const handlePage = (p: number) => {
    setPage(p);
    fetchAgents(p, search, category);
  };

  const totalPages = Math.ceil(totalCount / pageSize);

  if (!open) return null;

  return (
    <div className="absolute inset-0 z-10 flex flex-col bg-white dark:bg-neutral-900 rounded-2xl overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-neutral-200 dark:border-neutral-800">
        <div className="flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-primary-500" />
          <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">
            Agent Library
          </h3>
          <span className="text-xs text-neutral-400">({totalCount} agents)</span>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
        >
          <X className="w-4 h-4 text-neutral-500" />
        </button>
      </div>

      <div className="flex items-center gap-2 px-5 py-3 border-b border-neutral-100 dark:border-neutral-800">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-neutral-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="Search agents..."
            className="w-full pl-8 pr-3 py-1.5 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none transition-colors"
          />
        </div>
        <div className="relative">
          <select
            value={category}
            onChange={(e) => handleCategory(e.target.value)}
            className="appearance-none pl-3 pr-7 py-1.5 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none transition-colors"
          >
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c.charAt(0).toUpperCase() + c.slice(1)}
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-neutral-400 pointer-events-none" />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
        {loading && agents.length === 0 ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-5 h-5 animate-spin text-neutral-400" />
          </div>
        ) : agents.length === 0 ? (
          <div className="text-center py-12 text-sm text-neutral-400">
            No agents found
          </div>
        ) : (
          agents.map((agent) => (
            <button
              key={agent.agent_id}
              type="button"
              onClick={() => onSelect(agent)}
              className="w-full text-left px-4 py-3 rounded-xl border border-transparent hover:border-primary-200 dark:hover:border-primary-800 hover:bg-primary-50/50 dark:hover:bg-primary-500/5 transition-all group"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-neutral-900 dark:text-white group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">
                  {agent.name}
                </span>
                <span
                  className={cn(
                    "px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wide",
                    categoryBadgeClass(agent.category)
                  )}
                >
                  {agent.category}
                </span>
              </div>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 line-clamp-2">
                {agent.description}
              </p>
            </button>
          ))
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 px-5 py-3 border-t border-neutral-200 dark:border-neutral-800">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => handlePage(page - 1)}
            className="px-3 py-1 rounded-lg text-xs font-medium text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800 disabled:opacity-30 transition-colors"
          >
            Previous
          </button>
          <span className="text-xs text-neutral-500">
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => handlePage(page + 1)}
            className="px-3 py-1 rounded-lg text-xs font-medium text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800 disabled:opacity-30 transition-colors"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step indicator component
// ---------------------------------------------------------------------------
function StepIndicator({ currentStep, totalSteps }: { currentStep: number; totalSteps: number }) {
  return (
    <div className="flex items-center gap-2">
      {Array.from({ length: totalSteps }, (_, i) => {
        const stepNum = i + 1;
        return (
          <div key={stepNum} className="flex items-center gap-2">
            <div
              className={cn(
                "w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors",
                stepNum <= currentStep
                  ? "bg-primary-500 text-white"
                  : "bg-neutral-200 dark:bg-neutral-700 text-neutral-500"
              )}
            >
              {stepNum < currentStep ? (
                <Check className="w-3.5 h-3.5" />
              ) : (
                stepNum
              )}
            </div>
            {i < totalSteps - 1 && (
              <div className="w-8 h-0.5 bg-neutral-200 dark:bg-neutral-700">
                <div
                  className={cn(
                    "h-full transition-all",
                    stepNum < currentStep ? "w-full bg-primary-500" : "w-0"
                  )}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step titles
// ---------------------------------------------------------------------------
const STEP_TITLES: Record<WizardStep, { title: string; subtitle: string }> = {
  1: { title: "Crew Details", subtitle: "Name your crew and describe its purpose" },
  2: { title: "Execution Mode", subtitle: "Choose how agents collaborate" },
  3: { title: "Agent Team", subtitle: "Build your agent pipeline" },
  4: { title: "Review & Create", subtitle: "Review your crew configuration" },
};

// ---------------------------------------------------------------------------
// CrewBuilder — Wizard-style
// ---------------------------------------------------------------------------

interface CrewBuilderProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
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

  const [step, setStep] = useState<WizardStep>(1);
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
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [blueprintSelectorOpen, setBlueprintSelectorOpen] = useState(false);
  const [selectedBlueprint, setSelectedBlueprint] = useState<BlueprintSelection | null>(null);

  // Reset on open
  useEffect(() => {
    if (open) {
      setStep(1);
      if (!isEdit) {
        setName("");
        setDescription("");
        setExecutionMode("sequential");
        setAgents([emptyAgent()]);
        setMaxInvocations(10);
        setBudgetLimit(1.0);
        setSelectedBlueprint(null);
        setError(null);
      }
    }
  }, [open, isEdit]);

  const handleLibrarySelect = (agent: LibraryAgent) => {
    setAgents((prev) => [
      ...prev,
      {
        name: agent.name,
        role: ROLE_OPTIONS.includes(agent.suggested_role) ? agent.suggested_role : "custom",
        instructions: agent.description,
      },
    ]);
    setLibraryOpen(false);
  };

  const isAutonomous = executionMode === "autonomous";

  const canSubmit = isAutonomous
    ? !!name.trim()
    : name.trim() && agents.every((a) => a.name.trim() && a.instructions.trim());

  // Step validation
  const canProceed = (s: WizardStep): boolean => {
    switch (s) {
      case 1: return !!name.trim();
      case 2: return true; // always valid, mode has a default
      case 3: return isAutonomous || agents.every((a) => a.name.trim() && a.instructions.trim());
      case 4: return !!canSubmit;
      default: return false;
    }
  };

  const totalSteps = isAutonomous ? 3 : 4; // Skip agent step for autonomous
  const maxStep = (isAutonomous ? 3 : 4) as WizardStep;

  function nextStep() {
    if (step === 2 && isAutonomous) {
      setStep(4); // Skip agent step
    } else if (step < maxStep) {
      setStep((step + 1) as WizardStep);
    }
  }

  function prevStep() {
    if (step === 4 && isAutonomous) {
      setStep(2); // Skip back over agent step
    } else if (step > 1) {
      setStep((step - 1) as WizardStep);
    }
  }

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

  const handleSubmit = async () => {
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

  // For step indicator display: map to visual step number
  const visualStep = step === 4 && isAutonomous ? 3 : step;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="relative w-full max-w-3xl max-h-[90vh] bg-white dark:bg-neutral-900 rounded-2xl shadow-2xl border border-neutral-200 dark:border-neutral-700 flex flex-col overflow-hidden">
        {/* Library Agent Browser */}
        <LibraryPanel
          open={libraryOpen}
          onClose={() => setLibraryOpen(false)}
          onSelect={handleLibrarySelect}
        />

        {/* Blueprint Selector */}
        <BlueprintSelector
          open={blueprintSelectorOpen}
          onClose={() => setBlueprintSelectorOpen(false)}
          onSelect={(bp) => {
            setSelectedBlueprint(bp);
            setDescription(bp.content);
            setBlueprintSelectorOpen(false);
          }}
        />

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
                {STEP_TITLES[step].subtitle}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <StepIndicator currentStep={visualStep} totalSteps={totalSteps} />
            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
            >
              <X className="w-5 h-5 text-neutral-500" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 text-sm">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          {/* ─── Step 1: Crew Details ─── */}
          {step === 1 && (
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
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
                    Description
                  </label>
                  <button
                    type="button"
                    onClick={() => setBlueprintSelectorOpen(true)}
                    className="flex items-center gap-1.5 text-xs font-medium text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 transition-colors"
                  >
                    <BookOpen className="w-3.5 h-3.5" />
                    Use Blueprint
                  </button>
                </div>
                {selectedBlueprint && (
                  <div className="flex items-center gap-2 mb-2 px-3 py-1.5 rounded-lg bg-primary-50 dark:bg-primary-500/10 border border-primary-200 dark:border-primary-800">
                    <BookOpen className="w-3.5 h-3.5 text-primary-500 flex-shrink-0" />
                    <span className="text-xs text-primary-700 dark:text-primary-300 font-medium truncate">
                      {selectedBlueprint.name}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedBlueprint(null);
                        setDescription("");
                      }}
                      className="ml-auto p-0.5 rounded hover:bg-primary-100 dark:hover:bg-primary-500/20 transition-colors"
                    >
                      <X className="w-3 h-3 text-primary-500" />
                    </button>
                  </div>
                )}
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="What does this crew do?"
                  rows={3}
                  maxLength={2000}
                  className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none transition-colors resize-none"
                />
              </div>
            </div>
          )}

          {/* ─── Step 2: Execution Mode ─── */}
          {step === 2 && (
            <>
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
            </>
          )}

          {/* ─── Step 3: Agent Team ─── */}
          {step === 3 && !isAutonomous && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium text-neutral-900 dark:text-white flex items-center gap-2">
                  <Brain className="w-4 h-4 text-primary-500" />
                  Agent Pipeline ({agents.length})
                </h3>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setLibraryOpen(true)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-500/10 border border-amber-200 dark:border-amber-800 transition-colors"
                  >
                    <BookOpen className="w-3.5 h-3.5" />
                    Browse Library
                  </button>
                  <button
                    type="button"
                    onClick={addAgent}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-primary-500 hover:bg-primary-50 dark:hover:bg-primary-500/10 transition-colors"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Add Agent
                  </button>
                </div>
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

          {/* ─── Step 4: Review ─── */}
          {step === 4 && (
            <div className="space-y-4">
              <div className="bg-neutral-50 dark:bg-neutral-800/50 rounded-xl border border-neutral-200 dark:border-neutral-700 p-5 space-y-3">
                <h3 className="text-sm font-medium text-neutral-900 dark:text-white flex items-center gap-2">
                  <Eye className="w-4 h-4 text-primary-500" />
                  Review Configuration
                </h3>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-1">
                      Crew Name
                    </p>
                    <p className="text-sm text-neutral-900 dark:text-white font-medium">
                      {name}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-1">
                      Execution Mode
                    </p>
                    <p className="text-sm text-neutral-900 dark:text-white font-medium capitalize">
                      {executionMode}
                    </p>
                  </div>
                </div>

                {description && (
                  <div>
                    <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-1">
                      Description
                    </p>
                    <p className="text-sm text-neutral-700 dark:text-neutral-300 line-clamp-3">
                      {description}
                    </p>
                  </div>
                )}

                {isAutonomous && (
                  <div className="grid grid-cols-2 gap-4 pt-2 border-t border-neutral-200 dark:border-neutral-700">
                    <div>
                      <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-1">
                        Max Invocations
                      </p>
                      <p className="text-sm text-neutral-900 dark:text-white font-medium">
                        {maxInvocations}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-1">
                        Budget Limit
                      </p>
                      <p className="text-sm text-neutral-900 dark:text-white font-medium">
                        ${budgetLimit.toFixed(2)}
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* Agent summary */}
              {!isAutonomous && agents.length > 0 && (
                <div className="bg-neutral-50 dark:bg-neutral-800/50 rounded-xl border border-neutral-200 dark:border-neutral-700 p-5 space-y-3">
                  <h3 className="text-sm font-medium text-neutral-900 dark:text-white flex items-center gap-2">
                    <Brain className="w-4 h-4 text-primary-500" />
                    Agent Team ({agents.length} agent{agents.length !== 1 ? "s" : ""})
                  </h3>

                  {/* Pipeline visualization */}
                  <div className="flex items-center gap-1 overflow-x-auto">
                    {agents.map((agent, i) => (
                      <div key={i} className="flex items-center gap-1 flex-shrink-0">
                        <div className="px-3 py-1.5 rounded-lg text-xs font-medium border border-primary-200 dark:border-primary-800 bg-primary-50 dark:bg-primary-500/10 text-primary-700 dark:text-primary-400">
                          {agent.name}
                        </div>
                        {i < agents.length - 1 && (
                          <ArrowRight className="w-3.5 h-3.5 text-neutral-300 dark:text-neutral-600 flex-shrink-0" />
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Agent details */}
                  <div className="space-y-2">
                    {agents.map((agent, i) => (
                      <div
                        key={i}
                        className="flex items-start gap-3 p-3 rounded-lg bg-white dark:bg-neutral-800 border border-neutral-100 dark:border-neutral-700"
                      >
                        <span className="text-xs font-bold text-primary-500 mt-0.5">
                          {i + 1}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-neutral-900 dark:text-white">
                              {agent.name}
                            </span>
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-700 text-neutral-500 dark:text-neutral-400 capitalize">
                              {agent.role}
                            </span>
                          </div>
                          <p className="text-xs text-neutral-500 dark:text-neutral-400 line-clamp-1 mt-0.5">
                            {agent.instructions}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-neutral-200 dark:border-neutral-800">
          <div>
            {step > 1 && (
              <button
                type="button"
                onClick={prevStep}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
              >
                <ArrowLeft className="w-4 h-4" />
                Back
              </button>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
            >
              Cancel
            </button>
            {step < maxStep ? (
              <button
                type="button"
                onClick={nextStep}
                disabled={!canProceed(step)}
                className="flex items-center gap-2 px-5 py-2 rounded-lg bg-primary-500 text-white hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm font-medium"
              >
                Next
                <ArrowRight className="w-4 h-4" />
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={!canSubmit || submitting}
                className="flex items-center gap-2 px-5 py-2 rounded-lg bg-primary-500 text-white hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm font-medium"
              >
                {submitting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Check className="w-4 h-4" />
                )}
                {isEdit ? "Save Changes" : "Create Crew"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
