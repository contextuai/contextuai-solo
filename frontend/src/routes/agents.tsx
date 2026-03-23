import { useState, useEffect, useMemo } from "react";
import { cn } from "@/lib/utils";
import { workspaceApi, type WorkspaceAgent } from "@/lib/api/workspace-client";
import { AgentDetail } from "@/components/workspace/agent-detail";
import { AgentCreate } from "@/components/workspace/agent-create";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bot,
  Plus,
  Search,
  AlertCircle,
  RefreshCw,
  BookOpen,
  Wrench,
  Calendar,
  Globe,
  Lock,
  X,
} from "lucide-react";

const ROLE_FILTERS = ["All", "Researcher", "Writer", "Analyst", "Designer", "Developer", "Reviewer", "Planner", "Custom"];

const ROLE_COLORS: Record<string, { text: string; bg: string }> = {
  Researcher: { text: "text-blue-700 dark:text-blue-300", bg: "bg-blue-100 dark:bg-blue-900/30" },
  Writer: { text: "text-purple-700 dark:text-purple-300", bg: "bg-purple-100 dark:bg-purple-900/30" },
  Analyst: { text: "text-emerald-700 dark:text-emerald-300", bg: "bg-emerald-100 dark:bg-emerald-900/30" },
  Designer: { text: "text-pink-700 dark:text-pink-300", bg: "bg-pink-100 dark:bg-pink-900/30" },
  Developer: { text: "text-amber-700 dark:text-amber-300", bg: "bg-amber-100 dark:bg-amber-900/30" },
  Reviewer: { text: "text-cyan-700 dark:text-cyan-300", bg: "bg-cyan-100 dark:bg-cyan-900/30" },
  Planner: { text: "text-indigo-700 dark:text-indigo-300", bg: "bg-indigo-100 dark:bg-indigo-900/30" },
  Custom: { text: "text-neutral-700 dark:text-neutral-300", bg: "bg-neutral-100 dark:bg-neutral-800" },
};

function getRoleColor(role: string) {
  return ROLE_COLORS[role] || ROLE_COLORS.Custom;
}

function formatDate(dateStr: string) {
  try {
    return new Date(dateStr).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return dateStr;
  }
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<WorkspaceAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState("All");

  // Detail panel
  const [selectedAgent, setSelectedAgent] = useState<WorkspaceAgent | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  // Create dialog
  const [createOpen, setCreateOpen] = useState(false);

  const loadAgents = async (retries = 3) => {
    try {
      setLoading(true);
      setError(null);
      const data = await workspaceApi.listAgents();
      setAgents(data);
    } catch (err) {
      console.error("Failed to load agents:", err);
      if (retries > 0) {
        // Backend may still be starting — retry after a short delay
        setTimeout(() => loadAgents(retries - 1), 2000);
        return;
      }
      setError(err instanceof Error ? err.message : "Failed to load agents");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAgents();
  }, []);

  const filteredAgents = useMemo(() => {
    let result = agents;

    // Filter by role
    if (activeFilter !== "All") {
      result = result.filter((a) => a.role === activeFilter);
    }

    // Filter by search
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (a) =>
          a.name.toLowerCase().includes(q) ||
          a.role.toLowerCase().includes(q) ||
          a.description.toLowerCase().includes(q) ||
          (a.category && a.category.toLowerCase().includes(q))
      );
    }

    return result;
  }, [agents, activeFilter, searchQuery]);

  // Count per role for badges
  const roleCounts = useMemo(() => {
    const counts: Record<string, number> = { All: agents.length };
    for (const agent of agents) {
      counts[agent.role] = (counts[agent.role] || 0) + 1;
    }
    return counts;
  }, [agents]);

  const handleOpenDetail = async (agent: WorkspaceAgent) => {
    setSelectedAgent(agent);
    setDetailOpen(true);
    // Fetch full agent (with system_prompt) for the detail panel
    try {
      const full = await workspaceApi.getAgent(agent.agent_id ?? agent.id);
      setSelectedAgent(full);
    } catch {
      // Keep the summary version if full fetch fails
    }
  };

  const handleDetailSaved = () => {
    setDetailOpen(false);
    setSelectedAgent(null);
    loadAgents();
  };

  const handleDetailDeleted = () => {
    setDetailOpen(false);
    setSelectedAgent(null);
    loadAgents();
  };

  const handleAgentCreated = () => {
    setCreateOpen(false);
    loadAgents();
  };

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* Page Header */}
      <div className="flex-shrink-0 px-6 pt-6 pb-0">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h1 className="text-2xl font-bold text-neutral-900 dark:text-white flex items-center gap-2.5">
              <BookOpen className="w-7 h-7 text-primary-500" />
              Agent Library
            </h1>
            <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
              Browse, create, and manage AI agents for your workspace
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-neutral-400 tabular-nums">
              {agents.length} agent{agents.length !== 1 ? "s" : ""}
            </span>
            <button
              onClick={() => loadAgents()}
              disabled={loading}
              className="p-2 rounded-lg text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
              title="Refresh"
            >
              <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
            </button>
            <button
              onClick={() => setCreateOpen(true)}
              className={cn(
                "flex items-center gap-1.5 px-4 py-2.5 rounded-lg text-sm font-medium text-white transition-colors",
                "bg-primary-500 hover:bg-primary-600 shadow-sm"
              )}
            >
              <Plus className="w-4 h-4" />
              Create Agent
            </button>
          </div>
        </div>

        {/* Search Bar */}
        <div className="relative mb-4">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search agents by name, role, or description..."
            className={cn(
              "w-full pl-10 pr-10 py-2.5 rounded-lg border text-sm transition-colors",
              "bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white placeholder-neutral-400",
              "border-neutral-300 dark:border-neutral-700",
              "focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none"
            )}
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Role Filter Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-4 scrollbar-hide">
          {ROLE_FILTERS.map((filter) => {
            const count = roleCounts[filter] || 0;
            // Don't show roles with 0 count (except "All")
            if (filter !== "All" && count === 0) return null;
            return (
              <button
                key={filter}
                onClick={() => setActiveFilter(filter)}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors",
                  activeFilter === filter
                    ? "bg-primary-500 text-white"
                    : "bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 hover:bg-neutral-200 dark:hover:bg-neutral-700"
                )}
              >
                {filter}
                {count > 0 && (
                  <span
                    className={cn(
                      "px-1.5 py-0.5 rounded-full text-[10px] tabular-nums",
                      activeFilter === filter
                        ? "bg-white/20 text-white"
                        : "bg-neutral-200 dark:bg-neutral-700 text-neutral-500 dark:text-neutral-400"
                    )}
                  >
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Scrollable Content Area */}
      <div className="flex-1 overflow-y-auto px-6 pb-6">
        {/* Error State */}
        {error && (
          <div className="mb-4 p-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
            <div className="flex items-center gap-2 text-red-700 dark:text-red-300 text-sm">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <p>{error}</p>
            </div>
          </div>
        )}

        {/* Loading State */}
        {loading && agents.length === 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-5 animate-pulse"
              >
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-lg bg-neutral-200 dark:bg-neutral-700" />
                  <div className="flex-1">
                    <div className="h-4 w-32 bg-neutral-200 dark:bg-neutral-700 rounded mb-1.5" />
                    <div className="h-3 w-20 bg-neutral-100 dark:bg-neutral-700 rounded" />
                  </div>
                </div>
                <div className="h-3 w-full bg-neutral-100 dark:bg-neutral-700 rounded mb-2" />
                <div className="h-3 w-3/4 bg-neutral-100 dark:bg-neutral-700 rounded mb-4" />
                <div className="flex gap-2">
                  <div className="h-6 w-16 bg-neutral-100 dark:bg-neutral-700 rounded" />
                  <div className="h-6 w-16 bg-neutral-100 dark:bg-neutral-700 rounded" />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Empty State */}
        {!loading && filteredAgents.length === 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col items-center justify-center py-16"
          >
            <div className="w-16 h-16 mb-4 bg-neutral-100 dark:bg-neutral-800 rounded-2xl flex items-center justify-center">
              <Bot className="w-8 h-8 text-neutral-400" />
            </div>
            <h3 className="text-lg font-semibold text-neutral-900 dark:text-white mb-1">
              {searchQuery || activeFilter !== "All" ? "No agents found" : "No agents yet"}
            </h3>
            <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-6 text-center max-w-sm">
              {searchQuery
                ? `No agents match "${searchQuery}". Try a different search.`
                : activeFilter !== "All"
                  ? `No ${activeFilter} agents found. Try a different filter.`
                  : "Create your first AI agent to get started with automated workflows."}
            </p>
            {!searchQuery && activeFilter === "All" ? (
              <button
                onClick={() => setCreateOpen(true)}
                className="flex items-center gap-1.5 px-5 py-2.5 bg-primary-500 hover:bg-primary-600 text-white rounded-lg text-sm font-medium transition-colors"
              >
                <Plus className="w-4 h-4" />
                Create Your First Agent
              </button>
            ) : (
              <button
                onClick={() => { setSearchQuery(""); setActiveFilter("All"); }}
                className="px-4 py-2 text-sm font-medium text-primary-500 hover:text-primary-600 transition-colors"
              >
                Clear Filters
              </button>
            )}
          </motion.div>
        )}

        {/* Agent Cards Grid */}
        {filteredAgents.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            <AnimatePresence mode="popLayout">
              {filteredAgents.map((agent, index) => {
                const roleColor = getRoleColor(agent.role);
                return (
                  <motion.div
                    key={agent.id}
                    layout
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    transition={{ delay: index * 0.03 }}
                    onClick={() => handleOpenDetail(agent)}
                    className={cn(
                      "bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700",
                      "p-5 cursor-pointer group flex flex-col transition-all duration-200",
                      "hover:shadow-md hover:border-neutral-300 dark:hover:border-neutral-600",
                      "hover:-translate-y-0.5"
                    )}
                  >
                    {/* Card Header */}
                    <div className="flex items-start gap-3 mb-3">
                      <div className={cn(
                        "flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center",
                        roleColor.bg
                      )}>
                        <Bot className={cn("w-5 h-5", roleColor.text)} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="text-sm font-semibold text-neutral-900 dark:text-white truncate group-hover:text-primary-500 transition-colors">
                          {agent.name}
                        </h3>
                        <span className={cn(
                          "inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium mt-0.5",
                          roleColor.text, roleColor.bg
                        )}>
                          {agent.role}
                        </span>
                      </div>
                      {agent.is_public ? (
                        <span title="Public"><Globe className="w-3.5 h-3.5 text-primary-400 flex-shrink-0 mt-0.5" /></span>
                      ) : (
                        <span title="Private"><Lock className="w-3.5 h-3.5 text-neutral-400 flex-shrink-0 mt-0.5" /></span>
                      )}
                    </div>

                    {/* Description */}
                    <p className="text-xs text-neutral-500 dark:text-neutral-400 leading-relaxed mb-3 line-clamp-3 flex-1">
                      {agent.description || "No description provided."}
                    </p>

                    {/* Tools */}
                    {agent.tools && agent.tools.length > 0 && (
                      <div className="flex items-center gap-1.5 mb-3">
                        <Wrench className="w-3 h-3 text-neutral-400 flex-shrink-0" />
                        <div className="flex flex-wrap gap-1">
                          {agent.tools.slice(0, 3).map((tool) => (
                            <span
                              key={tool}
                              className="px-1.5 py-0.5 bg-neutral-100 dark:bg-neutral-700 text-neutral-500 dark:text-neutral-400 text-[10px] rounded font-medium"
                            >
                              {tool.replace(/_/g, " ")}
                            </span>
                          ))}
                          {agent.tools.length > 3 && (
                            <span className="text-[10px] text-neutral-400">
                              +{agent.tools.length - 3}
                            </span>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Footer */}
                    <div className="pt-3 border-t border-neutral-100 dark:border-neutral-700 flex items-center justify-between">
                      <div className="flex items-center gap-1 text-neutral-400">
                        <Calendar className="w-3 h-3" />
                        <span className="text-[11px]">{formatDate(agent.created_at)}</span>
                      </div>
                      {agent.category && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-neutral-100 dark:bg-neutral-700 text-neutral-500 dark:text-neutral-400 font-medium">
                          {agent.category}
                        </span>
                      )}
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>
        )}

        {/* Results count */}
        {!loading && filteredAgents.length > 0 && filteredAgents.length !== agents.length && (
          <div className="text-center text-xs text-neutral-400 pt-4">
            Showing {filteredAgents.length} of {agents.length} agents
          </div>
        )}
      </div>

      {/* Agent Detail Slide-over */}
      <AgentDetail
        agent={selectedAgent}
        isOpen={detailOpen}
        onClose={() => { setDetailOpen(false); setSelectedAgent(null); }}
        onSaved={handleDetailSaved}
        onDeleted={handleDetailDeleted}
      />

      {/* Create Agent Dialog */}
      <AgentCreate
        isOpen={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={handleAgentCreated}
      />
    </div>
  );
}
