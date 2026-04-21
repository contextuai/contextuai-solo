import { useState, useEffect, useCallback, useRef } from "react";
import { cn } from "@/lib/utils";
import {
  crewsApi,
  type CrewAgent,
  type LibraryAgent,
  type ChannelBinding,
  type ConnectionBinding,
  type CrewTrigger,
} from "@/lib/api/crews-client";
import {
  connectionsApi,
  type ConnectionSummary,
} from "@/lib/api/connections-client";
import { getModels, type ModelConfig } from "@/lib/api/models-client";
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
  Cable,
  MessageSquare,
  Cpu,
  Bell,
  Zap,
  Calendar,
  ArrowDownToLine,
  ArrowUpFromLine,
} from "lucide-react";

type ExecutionMode = "sequential" | "parallel" | "pipeline" | "autonomous";
type WizardStep = 1 | 2 | 3 | 4 | 5 | 6 | 7;

type Direction = "inbound" | "outbound" | "both";

interface ReactiveTriggerDraft {
  id: string; // local-only, for list keying
  connection_id: string;
  keywords: string[];
  hashtags: string[];
  mentions: string[];
}

interface ScheduledTriggerDraft {
  id: string;
  mode: "cron" | "run_at";
  cron: string;
  run_at: string;
  connection_ids: string[];
  content_brief: string;
}

function _newId() {
  return Math.random().toString(36).slice(2, 10);
}

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
  4: { title: "Connections & Directions", subtitle: "Pick the tools this crew uses and what direction each goes" },
  5: { title: "Trigger", subtitle: "How should this crew fire — reactive, scheduled, or manual only?" },
  6: { title: "Approval", subtitle: "Review outbound before it's sent?" },
  7: { title: "Review & Create", subtitle: "Review your crew configuration" },
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
    channel_bindings?: ChannelBinding[];
    connection_bindings?: ConnectionBinding[];
    triggers?: CrewTrigger[];
    approval_required?: boolean;
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
  const [channelBindings, setChannelBindings] = useState<ChannelBinding[]>(
    editCrew?.channel_bindings ?? []
  );

  // Phase 3: connection_bindings, triggers, approval_required
  const [availableConnections, setAvailableConnections] = useState<ConnectionSummary[]>([]);
  const [connectionBindings, setConnectionBindings] = useState<ConnectionBinding[]>(
    editCrew?.connection_bindings ?? []
  );
  const [reactiveTriggers, setReactiveTriggers] = useState<ReactiveTriggerDraft[]>(
    (editCrew?.triggers ?? [])
      .filter((t): t is Extract<CrewTrigger, { type: "reactive" }> => t.type === "reactive")
      .map((t) => ({
        id: _newId(),
        connection_id: t.connection_id,
        keywords: t.keywords ?? [],
        hashtags: t.hashtags ?? [],
        mentions: t.mentions ?? [],
      }))
  );
  const [scheduledTriggers, setScheduledTriggers] = useState<ScheduledTriggerDraft[]>(
    (editCrew?.triggers ?? [])
      .filter((t): t is Extract<CrewTrigger, { type: "scheduled" }> => t.type === "scheduled")
      .map((t) => ({
        id: _newId(),
        mode: t.cron ? "cron" : "run_at",
        cron: t.cron ?? "",
        run_at: t.run_at ?? "",
        connection_ids: t.connection_ids ?? [],
        content_brief: t.content_brief ?? "",
      }))
  );
  const [approvalRequired, setApprovalRequired] = useState<boolean>(
    editCrew?.approval_required ?? false
  );
  const [capabilityModal, setCapabilityModal] = useState<{
    connection: ConnectionSummary;
    direction: Direction;
  } | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [blueprintSelectorOpen, setBlueprintSelectorOpen] = useState(false);
  const [selectedBlueprint, setSelectedBlueprint] = useState<BlueprintSelection | null>(null);
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [selectedModelId, setSelectedModelId] = useState<string | null>(
    editCrew?.agents?.[0]?.model_id ?? null
  );
  // Legacy OAuth-status polling is no longer needed — the unified
  // /api/v1/connections aggregator returns connection state directly.

  // Fetch available models when dialog opens
  useEffect(() => {
    if (open) {
      getModels()
        .then((list) => {
          setModels(list.filter((m) => m.enabled));
        })
        .catch(() => setModels([]));
    }
  }, [open]);

  // Fetch unified connections on open (Phase 3)
  const refreshConnections = useCallback(() => {
    connectionsApi
      .list()
      .then(setAvailableConnections)
      .catch(() => setAvailableConnections([]));
  }, []);

  useEffect(() => {
    if (open) refreshConnections();
  }, [open, refreshConnections]);

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
        setChannelBindings([]);
        setConnectionBindings([]);
        setReactiveTriggers([]);
        setScheduledTriggers([]);
        setApprovalRequired(false);
        setSelectedBlueprint(null);
        setSelectedModelId(null);
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
      case 4: return true; // connections are optional — manual-only is supported
      case 5: {
        // Reactive: each draft needs ≥1 keyword/hashtag/mention.
        for (const t of reactiveTriggers) {
          if (!t.connection_id) return false;
          if (t.keywords.length + t.hashtags.length + t.mentions.length === 0) return false;
        }
        // Scheduled: exactly one of cron/run_at.
        for (const t of scheduledTriggers) {
          if (t.mode === "cron" && !t.cron.trim()) return false;
          if (t.mode === "run_at" && !t.run_at.trim()) return false;
        }
        return true;
      }
      case 6: return true; // approval toggle always valid
      case 7: return !!canSubmit;
      default: return false;
    }
  };

  // Steps: 1-Details, 2-Mode, 3-Agents (skip if autonomous), 4-Connections,
  // 5-Trigger, 6-Approval, 7-Review. Autonomous collapses 7→6 visual steps.
  const totalSteps = isAutonomous ? 6 : 7;
  const maxStep = 7 as WizardStep;

  function nextStep() {
    if (step === 2 && isAutonomous) {
      setStep(4); // Skip agent step for autonomous
    } else if (step < maxStep) {
      setStep((step + 1) as WizardStep);
    }
  }

  function prevStep() {
    if (step === 4 && isAutonomous) {
      setStep(2); // Skip back over agent step for autonomous
    } else if (step > 1) {
      setStep((step - 1) as WizardStep);
    }
  }

  // --- Phase 3 connection binding helpers ---

  function hasBinding(connId: string) {
    return connectionBindings.some((b) => b.connection_id === connId);
  }

  function getBindingDirection(connId: string): Direction | null {
    return connectionBindings.find((b) => b.connection_id === connId)?.direction ?? null;
  }

  function addBinding(conn: ConnectionSummary, direction: Direction) {
    setConnectionBindings((prev) => {
      const filtered = prev.filter((b) => b.connection_id !== conn.id);
      return [
        ...filtered,
        { connection_id: conn.id, platform: conn.platform, direction },
      ];
    });
  }

  function removeBinding(connId: string) {
    setConnectionBindings((prev) => prev.filter((b) => b.connection_id !== connId));
    // Also drop any reactive triggers tied to this connection.
    setReactiveTriggers((prev) => prev.filter((t) => t.connection_id !== connId));
  }

  function handleDirectionPick(conn: ConnectionSummary, direction: Direction) {
    // Block directions the platform doesn't physically support.
    if (direction === "inbound" && !conn.inbound_supported) return;
    if (direction === "outbound" && !conn.outbound_supported) return;

    // If the user picked a direction that's disabled at the connection-level,
    // open the inline modal to offer enabling it.
    const capability = direction === "inbound"
      ? conn.inbound_enabled
      : direction === "outbound"
        ? conn.outbound_enabled
        : (conn.inbound_enabled && conn.outbound_enabled);
    if (!capability) {
      setCapabilityModal({ connection: conn, direction });
      return;
    }
    addBinding(conn, direction);
  }

  async function enableCapabilityAndContinue() {
    if (!capabilityModal) return;
    const { connection, direction } = capabilityModal;
    const update: { inbound_enabled?: boolean; outbound_enabled?: boolean } = {};
    if (direction === "inbound") update.inbound_enabled = true;
    else if (direction === "outbound") update.outbound_enabled = true;
    else {
      update.inbound_enabled = true;
      update.outbound_enabled = true;
    }
    try {
      await connectionsApi.updateCapabilities(connection.id, update);
      refreshConnections();
      addBinding(connection, direction);
    } catch (e) {
      console.error("Failed to enable capability", e);
    } finally {
      setCapabilityModal(null);
    }
  }

  // --- Reactive trigger helpers ---

  function addReactiveTrigger(connectionId: string) {
    setReactiveTriggers((prev) => [
      ...prev,
      { id: _newId(), connection_id: connectionId, keywords: [], hashtags: [], mentions: [] },
    ]);
  }

  function removeReactiveTrigger(id: string) {
    setReactiveTriggers((prev) => prev.filter((t) => t.id !== id));
  }

  function addRuleToReactive(
    id: string,
    field: "keywords" | "hashtags" | "mentions",
    value: string,
  ) {
    const v = value.trim();
    if (!v) return;
    setReactiveTriggers((prev) =>
      prev.map((t) => (t.id === id ? { ...t, [field]: Array.from(new Set([...t[field], v])) } : t))
    );
  }

  function removeRuleFromReactive(
    id: string,
    field: "keywords" | "hashtags" | "mentions",
    value: string,
  ) {
    setReactiveTriggers((prev) =>
      prev.map((t) => (t.id === id ? { ...t, [field]: t[field].filter((x) => x !== value) } : t))
    );
  }

  // --- Scheduled trigger helpers ---

  function addScheduledTrigger() {
    setScheduledTriggers((prev) => [
      ...prev,
      { id: _newId(), mode: "cron", cron: "0 9 * * *", run_at: "", connection_ids: [], content_brief: "" },
    ]);
  }

  function updateScheduledTrigger(id: string, patch: Partial<ScheduledTriggerDraft>) {
    setScheduledTriggers((prev) => prev.map((t) => (t.id === id ? { ...t, ...patch } : t)));
  }

  function removeScheduledTrigger(id: string) {
    setScheduledTriggers((prev) => prev.filter((t) => t.id !== id));
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
          ...(selectedModelId && { model_id: selectedModelId }),
        }));
      }

      if (channelBindings.length > 0) {
        payload.channel_bindings = channelBindings;
      }

      // Phase 3 additions
      if (connectionBindings.length > 0) {
        payload.connection_bindings = connectionBindings;
      }
      const triggers: CrewTrigger[] = [];
      for (const t of reactiveTriggers) {
        triggers.push({
          type: "reactive",
          connection_id: t.connection_id,
          keywords: t.keywords,
          hashtags: t.hashtags,
          mentions: t.mentions,
        });
      }
      for (const t of scheduledTriggers) {
        triggers.push(
          t.mode === "cron"
            ? {
                type: "scheduled",
                connection_ids: t.connection_ids,
                cron: t.cron,
                content_brief: t.content_brief || undefined,
              }
            : {
                type: "scheduled",
                connection_ids: t.connection_ids,
                run_at: t.run_at,
                content_brief: t.content_brief || undefined,
              }
        );
      }
      if (triggers.length > 0) {
        payload.triggers = triggers;
      }
      payload.approval_required = approvalRequired;

      if (isEdit && editCrew) {
        await crewsApi.update(editCrew.crew_id, payload);
      } else {
        await crewsApi.create(payload);
      }
      onCreated();
      onClose();
    } catch (err: unknown) {
      // Extract validation detail from 422 responses
      const axiosErr = err as { response?: { data?: { detail?: unknown } } };
      const detail = axiosErr?.response?.data?.detail;
      if (Array.isArray(detail)) {
        setError(detail.map((d: { msg?: string; loc?: string[] }) =>
          `${d.loc?.slice(-1)?.[0] ?? "field"}: ${d.msg}`).join("; "));
      } else {
        setError(err instanceof Error ? err.message : "Failed to save crew");
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  // For step indicator display: map to visual step number.
  // Autonomous skips step 3 (agents), so steps 4..7 each shift down by 1 visually.
  const visualStep = isAutonomous && step >= 4 ? step - 1 : step;

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
                  maxLength={10000}
                  className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none transition-colors resize-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  <span className="flex items-center gap-1.5">
                    <Cpu className="w-3.5 h-3.5" />
                    AI Model
                  </span>
                </label>
                <select
                  value={selectedModelId ?? ""}
                  onChange={(e) => setSelectedModelId(e.target.value || null)}
                  className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none transition-colors"
                >
                  <option value="">Auto (uses default model)</option>
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}{m.provider ? ` · ${m.provider}` : ""}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-neutral-400">
                  All agents in this crew will use the selected model.
                </p>
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

          {/* ─── Step 4: Connections & Directions ─── */}
          {step === 4 && (
            <div className="space-y-4">
              <div className="bg-neutral-50 dark:bg-neutral-800/50 rounded-xl border border-neutral-200 dark:border-neutral-700 p-5 space-y-3">
                <h3 className="text-sm font-medium text-neutral-900 dark:text-white flex items-center gap-2">
                  <Cable className="w-4 h-4 text-primary-500" />
                  Pick connections & direction
                </h3>
                <p className="text-xs text-neutral-500 dark:text-neutral-400">
                  Choose which tools this crew uses. For each, pick a direction: <b>Inbound</b> (listen for messages), <b>Outbound</b> (publish), or <b>Both</b>. Outbound-only platforms (Blog / Email / Slack webhook) are publish-only.
                </p>

                {availableConnections.length === 0 ? (
                  <p className="text-xs text-neutral-400 dark:text-neutral-500 italic">
                    No connections set up yet. Add one from <a href="/connections" className="underline text-primary-500">Connections</a> and come back.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {availableConnections.map((conn) => {
                      const current = getBindingDirection(conn.id);
                      const selected = hasBinding(conn.id);
                      return (
                        <div
                          key={conn.id}
                          className={cn(
                            "rounded-xl border-2 p-3 transition-colors",
                            selected
                              ? "border-primary-500 bg-primary-50/50 dark:bg-primary-500/5"
                              : "border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800/50"
                          )}
                        >
                          <div className="flex items-center justify-between gap-3 flex-wrap">
                            <div className="flex items-center gap-2 min-w-0">
                              <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-neutral-100 dark:bg-neutral-700">
                                <MessageSquare className="w-4 h-4 text-neutral-600 dark:text-neutral-300" />
                              </div>
                              <div className="min-w-0">
                                <p className="text-sm font-medium text-neutral-900 dark:text-white truncate">
                                  {conn.display_name ?? conn.platform}
                                </p>
                                <p className="text-[10px] text-neutral-500 dark:text-neutral-400">
                                  {conn.platform}
                                  {!conn.connected && <span className="ml-1 text-amber-500">• disconnected</span>}
                                </p>
                              </div>
                            </div>
                            <div className="flex items-center gap-1">
                              <DirectionChip
                                label="Inbound"
                                icon={ArrowDownToLine}
                                active={current === "inbound"}
                                disabled={!conn.inbound_supported}
                                onClick={() => handleDirectionPick(conn, "inbound")}
                              />
                              <DirectionChip
                                label="Outbound"
                                icon={ArrowUpFromLine}
                                active={current === "outbound"}
                                disabled={!conn.outbound_supported}
                                onClick={() => handleDirectionPick(conn, "outbound")}
                              />
                              <DirectionChip
                                label="Both"
                                icon={ArrowRightLeft}
                                active={current === "both"}
                                disabled={!conn.inbound_supported || !conn.outbound_supported}
                                onClick={() => handleDirectionPick(conn, "both")}
                              />
                              {selected && (
                                <button
                                  type="button"
                                  onClick={() => removeBinding(conn.id)}
                                  className="ml-1 p-1 rounded text-neutral-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
                                  title="Remove binding"
                                >
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {connectionBindings.length === 0 && (
                  <p className="text-xs text-neutral-400 dark:text-neutral-500 italic">
                    No connections selected. This crew will run manually only (the Run button on the crew card).
                  </p>
                )}
              </div>

              {/* Enable-capability inline modal */}
              {capabilityModal && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 backdrop-blur-sm">
                  <div className="bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-700 p-5 max-w-md mx-4 shadow-xl">
                    <div className="flex items-center gap-2 mb-3">
                      <AlertCircle className="w-5 h-5 text-amber-500" />
                      <h4 className="text-sm font-semibold text-neutral-900 dark:text-white">
                        Capability disabled
                      </h4>
                    </div>
                    <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-4">
                      <b className="capitalize">{capabilityModal.direction}</b> is currently disabled on{" "}
                      <b>{capabilityModal.connection.display_name ?? capabilityModal.connection.platform}</b>.
                      Enable it now so this crew can use it?
                    </p>
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => setCapabilityModal(null)}
                        className="px-3 py-1.5 rounded-lg text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={enableCapabilityAndContinue}
                        className="px-3 py-1.5 rounded-lg text-sm font-medium bg-primary-500 text-white hover:bg-primary-600"
                      >
                        Enable & continue
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ─── Step 5: Trigger ─── */}
          {step === 5 && (
            <div className="space-y-4">
              <div className="bg-neutral-50 dark:bg-neutral-800/50 rounded-xl border border-neutral-200 dark:border-neutral-700 p-5 space-y-4">
                <h3 className="text-sm font-medium text-neutral-900 dark:text-white flex items-center gap-2">
                  <Zap className="w-4 h-4 text-primary-500" />
                  Reactive triggers
                </h3>
                <p className="text-xs text-neutral-500 dark:text-neutral-400 -mt-2">
                  Fire this crew when an inbound message matches any keyword, hashtag, or @mention.
                </p>
                {reactiveTriggers.length === 0 && connectionBindings.filter((b) => b.direction === "inbound" || b.direction === "both").length === 0 && (
                  <p className="text-xs text-neutral-400 dark:text-neutral-500 italic">
                    To add a reactive trigger, go back to <b>Step 4</b> and pick a connection with direction <b>Inbound</b> or <b>Both</b>. Triggers are configured per inbound-bound connection.
                  </p>
                )}
                <div className="space-y-3">
                  {reactiveTriggers.map((trigger) => {
                    const conn = availableConnections.find((c) => c.id === trigger.connection_id);
                    return (
                      <div key={trigger.id} className="rounded-lg border border-neutral-200 dark:border-neutral-700 p-3 bg-white dark:bg-neutral-800 space-y-2">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <ArrowDownToLine className="w-3.5 h-3.5 text-primary-500" />
                            <span className="text-sm font-medium text-neutral-900 dark:text-white">
                              {conn?.display_name ?? conn?.platform ?? trigger.connection_id}
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={() => removeReactiveTrigger(trigger.id)}
                            className="text-neutral-400 hover:text-red-500"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                        <RuleChips
                          label="Keywords"
                          values={trigger.keywords}
                          onAdd={(v) => addRuleToReactive(trigger.id, "keywords", v)}
                          onRemove={(v) => removeRuleFromReactive(trigger.id, "keywords", v)}
                        />
                        <RuleChips
                          label="Hashtags"
                          values={trigger.hashtags}
                          placeholderPrefix="#"
                          onAdd={(v) => addRuleToReactive(trigger.id, "hashtags", v)}
                          onRemove={(v) => removeRuleFromReactive(trigger.id, "hashtags", v)}
                        />
                        <RuleChips
                          label="Mentions"
                          values={trigger.mentions}
                          placeholderPrefix="@"
                          onAdd={(v) => addRuleToReactive(trigger.id, "mentions", v)}
                          onRemove={(v) => removeRuleFromReactive(trigger.id, "mentions", v)}
                        />
                        {trigger.keywords.length + trigger.hashtags.length + trigger.mentions.length === 0 && (
                          <p className="text-[11px] text-red-500">
                            Add at least one keyword, hashtag, or mention.
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
                <div className="flex flex-wrap gap-2">
                  {connectionBindings
                    .filter((b) => b.direction === "inbound" || b.direction === "both")
                    .map((b) => {
                      const conn = availableConnections.find((c) => c.id === b.connection_id);
                      return (
                        <button
                          key={b.connection_id}
                          type="button"
                          onClick={() => addReactiveTrigger(b.connection_id)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border border-dashed border-neutral-300 dark:border-neutral-600 text-xs text-neutral-600 dark:text-neutral-300 hover:border-primary-500 hover:text-primary-500"
                        >
                          <Plus className="w-3 h-3" />
                          {conn?.display_name ?? conn?.platform ?? b.connection_id}
                        </button>
                      );
                    })}
                </div>
              </div>

              <div className="bg-neutral-50 dark:bg-neutral-800/50 rounded-xl border border-neutral-200 dark:border-neutral-700 p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium text-neutral-900 dark:text-white flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-primary-500" />
                    Scheduled triggers
                  </h3>
                  <button
                    type="button"
                    onClick={addScheduledTrigger}
                    className="inline-flex items-center gap-1 text-xs text-primary-500 hover:text-primary-600"
                  >
                    <Plus className="w-3 h-3" />
                    Add schedule
                  </button>
                </div>
                <p className="text-xs text-neutral-500 dark:text-neutral-400 -mt-1">
                  Fire on a cron schedule (recurring) or a specific datetime (one-shot).
                </p>
                {scheduledTriggers.length === 0 && (
                  <p className="text-xs text-neutral-400 dark:text-neutral-500 italic">
                    No schedules set. Add one if you want this crew to fire automatically on a timer.
                  </p>
                )}
                <div className="space-y-3">
                  {scheduledTriggers.map((trigger) => (
                    <div key={trigger.id} className="rounded-lg border border-neutral-200 dark:border-neutral-700 p-3 bg-white dark:bg-neutral-800 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs">
                          <label className="inline-flex items-center gap-1 cursor-pointer">
                            <input
                              type="radio"
                              name={`mode-${trigger.id}`}
                              checked={trigger.mode === "cron"}
                              onChange={() => updateScheduledTrigger(trigger.id, { mode: "cron" })}
                            />
                            Recurring (cron)
                          </label>
                          <label className="inline-flex items-center gap-1 cursor-pointer ml-2">
                            <input
                              type="radio"
                              name={`mode-${trigger.id}`}
                              checked={trigger.mode === "run_at"}
                              onChange={() => updateScheduledTrigger(trigger.id, { mode: "run_at" })}
                            />
                            One-shot
                          </label>
                        </div>
                        <button
                          type="button"
                          onClick={() => removeScheduledTrigger(trigger.id)}
                          className="text-neutral-400 hover:text-red-500"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                      {trigger.mode === "cron" ? (
                        <input
                          type="text"
                          value={trigger.cron}
                          onChange={(e) => updateScheduledTrigger(trigger.id, { cron: e.target.value })}
                          placeholder="0 9 * * *"
                          className="w-full px-2.5 py-1.5 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-xs font-mono"
                        />
                      ) : (
                        <input
                          type="datetime-local"
                          value={trigger.run_at}
                          onChange={(e) => updateScheduledTrigger(trigger.id, { run_at: e.target.value })}
                          className="w-full px-2.5 py-1.5 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-xs"
                        />
                      )}
                      <textarea
                        value={trigger.content_brief}
                        onChange={(e) => updateScheduledTrigger(trigger.id, { content_brief: e.target.value })}
                        placeholder="What should this crew produce? (optional)"
                        rows={2}
                        className="w-full px-2.5 py-1.5 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white text-xs resize-none"
                      />
                    </div>
                  ))}
                </div>
              </div>

              {reactiveTriggers.length === 0 && scheduledTriggers.length === 0 && (
                <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-xl p-3 text-xs text-amber-800 dark:text-amber-300">
                  No triggers configured — this crew will only fire when you click <b>Run</b> on its card.
                </div>
              )}
            </div>
          )}

          {/* ─── Step 6: Approval ─── */}
          {step === 6 && (
            <div className="space-y-4">
              <div className="bg-neutral-50 dark:bg-neutral-800/50 rounded-xl border border-neutral-200 dark:border-neutral-700 p-5 space-y-3">
                <h3 className="text-sm font-medium text-neutral-900 dark:text-white flex items-center gap-2">
                  <Bell className="w-4 h-4 text-primary-500" />
                  Approval
                </h3>
                <label className="flex items-start gap-3 cursor-pointer p-3 rounded-lg bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700">
                  <input
                    type="checkbox"
                    checked={approvalRequired}
                    onChange={(e) => setApprovalRequired(e.target.checked)}
                    className="mt-0.5 rounded border-neutral-300 dark:border-neutral-600 text-primary-500 focus:ring-primary-500/50 w-4 h-4"
                  />
                  <div>
                    <p className="text-sm font-medium text-neutral-900 dark:text-white">
                      Review outbound before sending
                    </p>
                    <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                      When on, this crew's output is queued in the <a href="/approvals" className="underline text-primary-500">Approvals</a> page instead of publishing immediately. You edit / approve / reject there before it goes out.
                    </p>
                  </div>
                </label>
              </div>
            </div>
          )}

          {/* ─── Step 7: Review ─── */}
          {step === 7 && (
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

                <div>
                  <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-1">
                    AI Model
                  </p>
                  <p className="text-sm text-neutral-900 dark:text-white font-medium flex items-center gap-1.5">
                    <Cpu className="w-3.5 h-3.5 text-primary-500" />
                    {selectedModelId
                      ? models.find((m) => m.id === selectedModelId)?.name ?? selectedModelId
                      : "Auto (default model)"}
                  </p>
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
                  <div className="space-y-2">
                    {agents.map((agent, i) => (
                      <div
                        key={i}
                        className="flex items-start gap-3 p-3 rounded-lg bg-white dark:bg-neutral-800 border border-neutral-100 dark:border-neutral-700"
                      >
                        <span className="text-xs font-bold text-primary-500 mt-0.5">{i + 1}</span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-neutral-900 dark:text-white">{agent.name}</span>
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-700 text-neutral-500 dark:text-neutral-400 capitalize">{agent.role}</span>
                          </div>
                          <p className="text-xs text-neutral-500 dark:text-neutral-400 line-clamp-1 mt-0.5">{agent.instructions}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Connections & Directions summary */}
              {connectionBindings.length > 0 && (
                <div className="bg-neutral-50 dark:bg-neutral-800/50 rounded-xl border border-neutral-200 dark:border-neutral-700 p-5 space-y-3">
                  <h3 className="text-sm font-medium text-neutral-900 dark:text-white flex items-center gap-2">
                    <Cable className="w-4 h-4 text-primary-500" />
                    Connections & Directions ({connectionBindings.length})
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {connectionBindings.map((b) => {
                      const conn = availableConnections.find((c) => c.id === b.connection_id);
                      const dirLabel = b.direction === "both" ? "Both" : b.direction === "inbound" ? "Inbound" : "Outbound";
                      const DirIcon = b.direction === "both" ? ArrowRightLeft : b.direction === "inbound" ? ArrowDownToLine : ArrowUpFromLine;
                      return (
                        <span
                          key={b.connection_id}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300"
                        >
                          {conn?.display_name ?? conn?.platform ?? b.platform}
                          <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-primary-100 dark:bg-primary-500/20 text-primary-700 dark:text-primary-300">
                            <DirIcon className="w-2.5 h-2.5" />
                            {dirLabel}
                          </span>
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Triggers summary */}
              <div className="bg-neutral-50 dark:bg-neutral-800/50 rounded-xl border border-neutral-200 dark:border-neutral-700 p-5 space-y-3">
                <h3 className="text-sm font-medium text-neutral-900 dark:text-white flex items-center gap-2">
                  <Zap className="w-4 h-4 text-primary-500" />
                  Triggers
                </h3>
                {reactiveTriggers.length === 0 && scheduledTriggers.length === 0 ? (
                  <p className="text-xs text-neutral-500 dark:text-neutral-400 italic">
                    Manual only — fires when you click Run on the crew card.
                  </p>
                ) : (
                  <div className="space-y-2 text-xs">
                    {reactiveTriggers.map((t) => {
                      const conn = availableConnections.find((c) => c.id === t.connection_id);
                      const rules = [...t.keywords, ...t.hashtags, ...t.mentions];
                      return (
                        <div key={t.id} className="flex items-start gap-2 p-2 rounded-lg bg-white dark:bg-neutral-800 border border-neutral-100 dark:border-neutral-700">
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-orange-100 dark:bg-orange-500/20 text-orange-700 dark:text-orange-400 text-[10px] font-medium">
                            <Zap className="w-2.5 h-2.5" /> Reactive
                          </span>
                          <span className="text-neutral-700 dark:text-neutral-300">
                            on <b>{conn?.display_name ?? t.connection_id}</b> matching <span className="text-neutral-500 dark:text-neutral-400">{rules.join(", ") || "(none)"}</span>
                          </span>
                        </div>
                      );
                    })}
                    {scheduledTriggers.map((t) => (
                      <div key={t.id} className="flex items-start gap-2 p-2 rounded-lg bg-white dark:bg-neutral-800 border border-neutral-100 dark:border-neutral-700">
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-400 text-[10px] font-medium">
                          <Calendar className="w-2.5 h-2.5" /> Scheduled
                        </span>
                        <span className="text-neutral-700 dark:text-neutral-300 font-mono">
                          {t.mode === "cron" ? t.cron : `at ${t.run_at}`}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Approval summary */}
              <div className={cn(
                "rounded-xl border p-4 text-xs",
                approvalRequired
                  ? "bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-300"
                  : "bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800 text-green-800 dark:text-green-300"
              )}>
                <div className="flex items-center gap-2">
                  {approvalRequired ? <Shield className="w-4 h-4" /> : <Check className="w-4 h-4" />}
                  <span className="font-medium">
                    {approvalRequired
                      ? "Review outbound before sending — output queued in Approvals."
                      : "Auto-publish — crew output goes out immediately."}
                  </span>
                </div>
              </div>
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

// ---------------------------------------------------------------------------
// Small UI helpers used inside the wizard
// ---------------------------------------------------------------------------

function DirectionChip({
  label,
  icon: Icon,
  active,
  disabled,
  onClick,
}: {
  label: string;
  icon: React.ElementType;
  active: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "inline-flex items-center gap-1 px-2 py-1 rounded-md border text-[11px] font-medium transition-colors",
        active
          ? "border-primary-500 bg-primary-500 text-white"
          : "border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-300 hover:border-primary-400",
        disabled && "opacity-40 cursor-not-allowed hover:border-neutral-200 dark:hover:border-neutral-700"
      )}
      title={disabled ? `${label} not supported on this platform` : undefined}
    >
      <Icon className="w-3 h-3" />
      {label}
    </button>
  );
}

function RuleChips({
  label,
  values,
  placeholderPrefix,
  onAdd,
  onRemove,
}: {
  label: string;
  values: string[];
  placeholderPrefix?: string;
  onAdd: (value: string) => void;
  onRemove: (value: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const submit = () => {
    const v = draft.trim();
    if (!v) return;
    onAdd(v);
    setDraft("");
  };
  return (
    <div className="space-y-1">
      <label className="text-[11px] font-medium text-neutral-500 dark:text-neutral-400">
        {label}
      </label>
      <div className="flex flex-wrap items-center gap-1.5">
        {values.map((v) => (
          <span
            key={v}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary-50 dark:bg-primary-500/10 text-primary-700 dark:text-primary-300 text-[11px] border border-primary-200 dark:border-primary-800"
          >
            {v}
            <button type="button" onClick={() => onRemove(v)} className="hover:text-red-500">
              <X className="w-2.5 h-2.5" />
            </button>
          </span>
        ))}
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submit();
            }
          }}
          onBlur={submit}
          placeholder={`+ ${placeholderPrefix ?? ""}${label.toLowerCase().slice(0, -1)}`}
          className="flex-1 min-w-[120px] px-2 py-0.5 text-[11px] rounded border border-transparent hover:border-neutral-200 dark:hover:border-neutral-700 focus:border-primary-500 bg-transparent outline-none"
        />
      </div>
    </div>
  );
}
