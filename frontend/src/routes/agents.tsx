import { useCallback, useEffect, useState } from "react";
import { BookOpen, Loader2, Plus, RefreshCw } from "lucide-react";

import { cn } from "@/lib/utils";
import { workspaceApi, type WorkspaceAgent } from "@/lib/api/workspace-client";
import { AgentDetail } from "@/components/workspace/agent-detail";
import { AgentCreate } from "@/components/workspace/agent-create";
import {
  AgentLibraryTabs,
  type AgentRow,
} from "@/components/agents/agent-library-tabs";
import { useBackendStatus } from "@/contexts/backend-status-context";
import { BackendWaiting } from "@/components/backend-waiting";

export default function AgentsPage() {
  const { status: backendStatus } = useBackendStatus();
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [countsLoading, setCountsLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  // Detail panel
  const [selectedAgent, setSelectedAgent] = useState<WorkspaceAgent | null>(
    null,
  );
  const [detailOpen, setDetailOpen] = useState(false);

  // Create dialog
  const [createOpen, setCreateOpen] = useState(false);

  const loadCounts = useCallback(async () => {
    setCountsLoading(true);
    try {
      const c = await workspaceApi.getAgentKindCounts();
      setCounts(c);
    } catch (err) {
      console.warn("Failed to load agent counts:", err);
    } finally {
      setCountsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCounts();
  }, [loadCounts, refreshKey]);

  const totalAgents = Object.values(counts).reduce((a, b) => a + b, 0);

  const handleSelectAgent = async (agent: AgentRow) => {
    setSelectedAgent(agent);
    setDetailOpen(true);
    try {
      const full = await workspaceApi.getAgent(agent.agent_id ?? agent.id);
      setSelectedAgent(full);
    } catch {
      // Fall back to summary
    }
  };

  const handleRefresh = () => {
    setRefreshKey((k) => k + 1);
  };

  const handleDetailSaved = () => {
    setDetailOpen(false);
    setSelectedAgent(null);
    handleRefresh();
  };

  const handleDetailDeleted = () => {
    setDetailOpen(false);
    setSelectedAgent(null);
    handleRefresh();
  };

  const handleAgentCreated = () => {
    setCreateOpen(false);
    handleRefresh();
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-neutral-50 dark:bg-neutral-950">
      {/* Page header */}
      <div className="flex-shrink-0 border-b border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 px-8 py-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="flex items-center gap-2.5 text-xl font-semibold text-neutral-900 dark:text-white">
              <BookOpen className="w-6 h-6 text-primary-500" />
              Agents
            </h1>
            <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
              Browse, create, and manage AI agents — grouped by what they
              connect to.
            </p>
            <p className="mt-2 text-xs text-neutral-500 dark:text-neutral-400 tabular-nums">
              {countsLoading ? (
                <span className="inline-flex items-center gap-1.5">
                  <Loader2 className="w-3 h-3 animate-spin" /> Loading…
                </span>
              ) : (
                <>
                  {totalAgents} agent{totalAgents === 1 ? "" : "s"} across{" "}
                  {Object.keys(counts).filter((k) => counts[k] > 0).length}{" "}
                  kind
                  {Object.keys(counts).filter((k) => counts[k] > 0).length === 1
                    ? ""
                    : "s"}
                </>
              )}
            </p>
          </div>
          <div className="flex flex-shrink-0 items-center gap-2">
            <button
              onClick={handleRefresh}
              disabled={countsLoading}
              className={cn(
                "p-2 rounded-lg text-neutral-500 transition-colors",
                "hover:text-neutral-700 dark:hover:text-neutral-200",
                "hover:bg-neutral-100 dark:hover:bg-neutral-800",
                "disabled:opacity-60",
              )}
              title="Refresh"
            >
              <RefreshCw
                className={cn("w-4 h-4", countsLoading && "animate-spin")}
              />
            </button>
            <button
              onClick={() => setCreateOpen(true)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg px-4 py-2.5 text-sm font-medium text-white transition-colors",
                "bg-primary-500 hover:bg-primary-600 shadow-sm",
              )}
            >
              <Plus className="w-4 h-4" />
              Create Agent
            </button>
          </div>
        </div>
      </div>

      {/* Tabbed picker */}
      <div className="flex-1 min-h-0 overflow-hidden px-8 py-6">
        {countsLoading && totalAgents === 0 && backendStatus !== "ready" ? (
          <BackendWaiting />
        ) : (
          <AgentLibraryTabs
            key={refreshKey}
            onSelect={handleSelectAgent}
            variant="page"
          />
        )}
      </div>

      {/* Slide-over detail panel */}
      <AgentDetail
        agent={selectedAgent}
        isOpen={detailOpen}
        onClose={() => {
          setDetailOpen(false);
          setSelectedAgent(null);
        }}
        onSaved={handleDetailSaved}
        onDeleted={handleDetailDeleted}
      />

      {/* Create agent dialog */}
      <AgentCreate
        isOpen={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={handleAgentCreated}
      />
    </div>
  );
}
