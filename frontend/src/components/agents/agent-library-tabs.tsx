import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  Bot,
  Database,
  FileText,
  Globe,
  Loader2,
  PlugZap,
  Search,
  Server,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  AGENT_KINDS,
  type AgentKind,
  type WorkspaceAgent,
  workspaceApi,
} from "@/lib/api/workspace-client";

export type AgentRow = WorkspaceAgent;

interface AgentLibraryTabsProps {
  selectedAgentId?: string;
  onSelect?: (agent: AgentRow) => void;
  storageKey?: string;
  variant?: "page" | "compact";
  /**
   * Restrict the visible kind tabs. Defaults to all kinds (Crew builder
   * picker uses this). The /agents page passes ["prompt"] now that the
   * other kinds live under /personas (Connectors).
   */
  kindsToShow?: readonly AgentKind[];
}

interface TabMeta {
  id: AgentKind;
  label: string;
  icon: typeof Bot;
  emptyTitle: string;
  emptyBody: string;
  emptyCtaLabel?: string;
  emptyCtaHref?: string;
}

const TABS: TabMeta[] = [
  {
    id: "prompt",
    label: "Prompt",
    icon: Bot,
    emptyTitle: "No prompt agents yet",
    emptyBody:
      "Create a custom prompt agent or browse the built-in business agent library.",
  },
  {
    id: "database",
    label: "Database",
    icon: Database,
    emptyTitle: "No database agents yet",
    emptyBody:
      "Add a Postgres / MySQL / MSSQL / Snowflake / MongoDB connector — it becomes a database agent here.",
    emptyCtaLabel: "Open Connectors",
    emptyCtaHref: "/personas",
  },
  {
    id: "web",
    label: "Web",
    icon: Globe,
    emptyTitle: "No web agents yet",
    emptyBody:
      "Add a Web Researcher connector to enable web search and fetch capabilities.",
    emptyCtaLabel: "Open Connectors",
    emptyCtaHref: "/personas",
  },
  {
    id: "mcp",
    label: "MCP",
    icon: Server,
    emptyTitle: "No MCP agents yet",
    emptyBody:
      "Wire up an MCP server connector to expose model-context-protocol tools as an agent.",
    emptyCtaLabel: "Open Connectors",
    emptyCtaHref: "/personas",
  },
  {
    id: "api",
    label: "API",
    icon: PlugZap,
    emptyTitle: "No API agents yet",
    emptyBody:
      "Configure an API connector to call external HTTP services from an agent.",
    emptyCtaLabel: "Open Connectors",
    emptyCtaHref: "/personas",
  },
  {
    id: "file",
    label: "File",
    icon: FileText,
    emptyTitle: "No file agents yet",
    emptyBody:
      "Add a File Operations connector to read and write local files from an agent.",
    emptyCtaLabel: "Open Connectors",
    emptyCtaHref: "/personas",
  },
];

const KIND_ICON_STYLES: Record<AgentKind, { bg: string; fg: string }> = {
  prompt: {
    bg: "bg-violet-100 dark:bg-violet-500/15",
    fg: "text-violet-600 dark:text-violet-400",
  },
  database: {
    bg: "bg-emerald-100 dark:bg-emerald-500/15",
    fg: "text-emerald-600 dark:text-emerald-400",
  },
  web: {
    bg: "bg-sky-100 dark:bg-sky-500/15",
    fg: "text-sky-600 dark:text-sky-400",
  },
  mcp: {
    bg: "bg-orange-100 dark:bg-orange-500/15",
    fg: "text-orange-600 dark:text-orange-400",
  },
  api: {
    bg: "bg-cyan-100 dark:bg-cyan-500/15",
    fg: "text-cyan-600 dark:text-cyan-400",
  },
  file: {
    bg: "bg-amber-100 dark:bg-amber-500/15",
    fg: "text-amber-600 dark:text-amber-400",
  },
};

function isAgentKind(value: string | null): value is AgentKind {
  return !!value && (AGENT_KINDS as string[]).includes(value);
}

export function AgentLibraryTabs({
  selectedAgentId,
  onSelect,
  storageKey = "solo.agents.tab",
  variant = "page",
  kindsToShow,
}: AgentLibraryTabsProps) {
  const visibleTabs = useMemo(
    () => (kindsToShow ? TABS.filter((t) => kindsToShow.includes(t.id)) : TABS),
    [kindsToShow],
  );
  const fallbackKind = visibleTabs[0]?.id ?? "prompt";
  const [activeKind, setActiveKind] = useState<AgentKind>(() => {
    if (typeof window === "undefined") return fallbackKind;
    const stored = window.localStorage.getItem(storageKey);
    if (isAgentKind(stored) && visibleTabs.some((t) => t.id === stored)) {
      return stored;
    }
    return fallbackKind;
  });
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  // Persist active tab
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(storageKey, activeKind);
  }, [storageKey, activeKind]);

  // Load counts once on mount; refresh when agents reload too
  const loadCounts = useCallback(async () => {
    try {
      const c = await workspaceApi.getAgentKindCounts();
      setCounts(c);
    } catch (err) {
      // Counts are non-fatal
      console.warn("Failed to load agent kind counts:", err);
    }
  }, []);

  useEffect(() => {
    loadCounts();
  }, [loadCounts]);

  // Load agents whenever active kind changes
  const loadAgents = useCallback(async (kind: AgentKind) => {
    setLoading(true);
    setError(null);
    try {
      const data = await workspaceApi.listAgents({ kind, pageSize: 100 });
      setAgents(data);
    } catch (err) {
      console.error("Failed to load agents:", err);
      setError(err instanceof Error ? err.message : "Failed to load agents");
      setAgents([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAgents(activeKind);
  }, [activeKind, loadAgents]);

  // Reset search when switching tabs to avoid stale empty states
  useEffect(() => {
    setSearch("");
  }, [activeKind]);

  const filteredAgents = useMemo(() => {
    if (!search.trim()) return agents;
    const q = search.toLowerCase();
    return agents.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q) ||
        (a.category && a.category.toLowerCase().includes(q)) ||
        a.role.toLowerCase().includes(q),
    );
  }, [agents, search]);

  const activeTab = visibleTabs.find((t) => t.id === activeKind) ?? visibleTabs[0] ?? TABS[0];
  const isInteractive = !!onSelect;
  const isCompact = variant === "compact";
  // Hide the tab strip entirely when there's only one kind to show — keeping
  // it would just be a row with a single useless pill.
  const showTabStrip = visibleTabs.length > 1;

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Tab bar */}
      {showTabStrip && (
      <div
        className={cn(
          "flex items-center gap-1 overflow-x-auto border-b border-neutral-200 dark:border-neutral-800",
          isCompact ? "px-1" : "px-1",
        )}
      >
        {visibleTabs.map((t) => {
          const Icon = t.icon;
          const count = counts[t.id] ?? 0;
          const active = t.id === activeKind;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setActiveKind(t.id)}
              className={cn(
                "flex items-center gap-2 whitespace-nowrap rounded-t-lg text-sm font-medium transition-colors",
                isCompact ? "px-3 py-2" : "px-4 py-2.5",
                active
                  ? "text-primary-600 dark:text-primary-400 border-b-2 border-primary-500 -mb-px"
                  : "text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300",
              )}
            >
              <Icon className="w-4 h-4" />
              <span>{t.label}</span>
              <span
                className={cn(
                  "px-1.5 py-0.5 rounded-full text-[10px] tabular-nums font-semibold",
                  active
                    ? "bg-primary-500/15 text-primary-600 dark:text-primary-300"
                    : "bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400",
                )}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>
      )}

      {/* Search */}
      <div className={cn("flex-shrink-0", isCompact ? "px-1 pt-3" : "px-1 pt-4")}>
        <div className="relative">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={`Search ${activeTab.label.toLowerCase()} agents…`}
            className={cn(
              "w-full pl-10 pr-10 rounded-lg border text-sm transition-colors",
              isCompact ? "py-2" : "py-2.5",
              "bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white placeholder-neutral-400",
              "border-neutral-300 dark:border-neutral-700",
              "focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none",
            )}
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div
        className={cn(
          "flex-1 overflow-y-auto",
          isCompact ? "pt-3 pb-1" : "pt-5 pb-2",
        )}
      >
        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 flex items-center gap-2 text-sm text-red-700 dark:text-red-300">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {loading && (
          <div className="flex flex-col items-center justify-center py-16 text-neutral-500 dark:text-neutral-400">
            <Loader2 className="w-6 h-6 animate-spin mb-2" />
            <p className="text-sm">Loading {activeTab.label.toLowerCase()} agents…</p>
          </div>
        )}

        {!loading && !error && filteredAgents.length === 0 && (
          <EmptyState
            tab={activeTab}
            search={search}
            onClearSearch={() => setSearch("")}
          />
        )}

        {!loading && !error && filteredAgents.length > 0 && (
          <div
            className={cn(
              "grid gap-3",
              isCompact
                ? "grid-cols-1 sm:grid-cols-2"
                : "grid-cols-1 md:grid-cols-2 xl:grid-cols-3",
            )}
          >
            {filteredAgents.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                selected={agent.id === selectedAgentId}
                interactive={isInteractive}
                compact={isCompact}
                onClick={onSelect ? () => onSelect(agent) : undefined}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function EmptyState({
  tab,
  search,
  onClearSearch,
}: {
  tab: TabMeta;
  search: string;
  onClearSearch: () => void;
}) {
  const Icon = tab.icon;

  if (search.trim()) {
    return (
      <div className="flex flex-col items-center justify-center py-14 text-center">
        <div className="w-14 h-14 mb-3 rounded-2xl bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center">
          <Search className="w-6 h-6 text-neutral-400" />
        </div>
        <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">
          No matches
        </h3>
        <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400 max-w-xs">
          No {tab.label.toLowerCase()} agents match{" "}
          <span className="font-mono">"{search}"</span>.
        </p>
        <button
          type="button"
          onClick={onClearSearch}
          className="mt-3 text-xs font-medium text-primary-500 hover:text-primary-600"
        >
          Clear search
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-14 text-center">
      <div className="w-14 h-14 mb-3 rounded-2xl bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center">
        <Icon className="w-6 h-6 text-neutral-400" />
      </div>
      <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">
        {tab.emptyTitle}
      </h3>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400 max-w-sm">
        {tab.emptyBody}
      </p>
      {tab.emptyCtaHref && tab.emptyCtaLabel && (
        <Link to={tab.emptyCtaHref} className="mt-4">
          <Button variant="secondary" size="sm">
            {tab.emptyCtaLabel}
          </Button>
        </Link>
      )}
    </div>
  );
}

function AgentCard({
  agent,
  selected,
  interactive,
  compact,
  onClick,
}: {
  agent: AgentRow;
  selected: boolean;
  interactive: boolean;
  compact: boolean;
  onClick?: () => void;
}) {
  const kind: AgentKind = agent.kind ?? "prompt";
  const styles = KIND_ICON_STYLES[kind];
  const tab = TABS.find((t) => t.id === kind) ?? TABS[0];
  const Icon = tab.icon;

  const Tag = onClick ? "button" : "div";

  return (
    <Tag
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className={cn(
        "text-left bg-white dark:bg-neutral-800 rounded-xl border transition-all flex flex-col",
        compact ? "p-3.5" : "p-4",
        selected
          ? "border-primary-500 ring-2 ring-primary-500/30"
          : "border-neutral-200 dark:border-neutral-700",
        interactive &&
          !selected &&
          "hover:border-neutral-300 dark:hover:border-neutral-600 hover:shadow-sm cursor-pointer",
        interactive && "focus:outline-none focus:ring-2 focus:ring-primary-500/40",
      )}
    >
      <div className="flex items-start gap-3 mb-2">
        <div
          className={cn(
            "flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center",
            styles.bg,
          )}
        >
          <Icon className={cn("w-4 h-4", styles.fg)} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-neutral-900 dark:text-white truncate">
            {agent.name}
          </h3>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span
              className={cn(
                "inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide",
                styles.bg,
                styles.fg,
              )}
            >
              {kind}
            </span>
            {agent.category && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-700 text-neutral-500 dark:text-neutral-400 font-medium truncate max-w-[140px]">
                {agent.category}
              </span>
            )}
          </div>
        </div>
      </div>
      <p className="text-xs text-neutral-500 dark:text-neutral-400 leading-relaxed line-clamp-2">
        {agent.description || "No description provided."}
      </p>
    </Tag>
  );
}
