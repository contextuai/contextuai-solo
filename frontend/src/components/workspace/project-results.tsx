import { useState, useEffect, useMemo, useCallback } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import {
  workspaceProjectsApi,
  type WorkspaceProject,
  type ProjectExecution,
  type AgentContribution,
} from "@/lib/api/workspace-projects-client";
import {
  ArrowLeft,
  MessageSquare,
  FileOutput,
  Users,
  Hash,
  Loader2,
  AlertCircle,
  CheckCircle,
  XCircle,
  Copy,
  Download,
  RefreshCw,
  DollarSign,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getAgentColor(agentId: string): string {
  const colors = [
    "bg-blue-500", "bg-green-500", "bg-purple-500", "bg-pink-500",
    "bg-teal-500", "bg-orange-500", "bg-indigo-500", "bg-rose-500",
    "bg-cyan-500", "bg-amber-500",
  ];
  let hash = 0;
  for (let i = 0; i < agentId.length; i++) {
    hash = agentId.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
}

function getInitials(name: string): string {
  return name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

function renderContent(content: string): string {
  return content
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(
      /`(.+?)`/g,
      '<code class="px-1.5 py-0.5 bg-neutral-100 dark:bg-neutral-700 rounded text-sm font-mono">$1</code>'
    )
    .replace(/^### (.+)$/gm, '<h3 class="text-lg font-semibold mt-4 mb-2">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-xl font-semibold mt-4 mb-2">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-2xl font-bold mt-4 mb-2">$1</h1>')
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    .replace(/\n/g, "<br />");
}

const STATUS_ICON: Record<string, typeof CheckCircle> = {
  completed: CheckCircle,
  failed: XCircle,
  running: Loader2,
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface ProjectResultsProps {
  projectId: string;
  onBack: () => void;
}

export function ProjectResults({ projectId, onBack }: ProjectResultsProps) {
  const [project, setProject] = useState<WorkspaceProject | null>(null);
  const [execution, setExecution] = useState<ProjectExecution | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"discussion" | "compiled">("discussion");
  const [copied, setCopied] = useState(false);

  const loadProject = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [proj, exec] = await Promise.allSettled([
        workspaceProjectsApi.get(projectId),
        workspaceProjectsApi.getExecution(projectId),
      ]);
      if (proj.status === "fulfilled") setProject(proj.value);
      else setError("Failed to load project");
      if (exec.status === "fulfilled") setExecution(exec.value);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load project");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadProject();
  }, [loadProject]);

  // Auto-refresh while running
  useEffect(() => {
    if (execution?.status !== "running") return;
    const timer = setInterval(loadProject, 5000);
    return () => clearInterval(timer);
  }, [execution?.status, loadProject]);

  const contributions: AgentContribution[] = execution?.contributions ?? [];

  const contributionsByRound = useMemo(() => {
    const grouped = new Map<number, AgentContribution[]>();
    for (const c of contributions) {
      const round = c.round_number;
      if (!grouped.has(round)) grouped.set(round, []);
      grouped.get(round)!.push(c);
    }
    return grouped;
  }, [contributions]);

  const maxRound = useMemo(() => {
    if (contributions.length === 0) return 0;
    return Math.max(...contributions.map((c) => c.round_number));
  }, [contributions]);

  const handleCopyCompiled = async () => {
    if (!execution?.compiled_output) return;
    await navigator.clipboard.writeText(execution.compiled_output);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadMarkdown = () => {
    if (!execution?.compiled_output || !project) return;
    const blob = new Blob([execution.compiled_output], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${project.title.replace(/\s+/g, "-").toLowerCase()}-output.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Loading state
  if (loading && !project) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
      </div>
    );
  }

  // Error state
  if (error && !project) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <div className="flex items-center gap-2 text-red-500">
          <AlertCircle className="w-6 h-6" />
          <p className="text-sm">{error}</p>
        </div>
        <Button variant="secondary" size="sm" onClick={onBack}>
          <ArrowLeft className="w-4 h-4" />
          Back to Projects
        </Button>
      </div>
    );
  }

  if (!project) return null;

  const StatusIcon = STATUS_ICON[project.status] ?? AlertCircle;
  const isComplete = project.status === "completed";
  const isRunning = project.status === "running";

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-neutral-200 dark:border-neutral-800">
        <div className="flex items-center gap-3 mb-3">
          <button
            onClick={onBack}
            className="p-1.5 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-neutral-500" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-semibold text-neutral-900 dark:text-white truncate">
              {project.title}
            </h1>
            <p className="text-sm text-neutral-500 dark:text-neutral-400 truncate">
              {project.description}
            </p>
          </div>
          <button
            onClick={loadProject}
            className="p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
            title="Refresh"
          >
            <RefreshCw className={cn("w-4 h-4 text-neutral-500", loading && "animate-spin")} />
          </button>
        </div>

        {/* Stats bar */}
        <div className="flex items-center gap-4 text-sm">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium",
              isComplete
                ? "bg-green-50 text-green-600 dark:bg-green-900/20 dark:text-green-400"
                : isRunning
                ? "bg-primary-50 text-primary-600 dark:bg-primary-900/20 dark:text-primary-400"
                : project.status === "failed"
                ? "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400"
                : "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400"
            )}
          >
            <StatusIcon className={cn("w-3.5 h-3.5", isRunning && "animate-spin")} />
            {project.status.charAt(0).toUpperCase() + project.status.slice(1)}
          </span>
          <span className="flex items-center gap-1 text-neutral-500 dark:text-neutral-400">
            <Users className="w-4 h-4" />
            {project.selected_agents?.length ?? 0} agents
          </span>
          {execution?.total_tokens != null && (
            <span className="flex items-center gap-1 text-neutral-500 dark:text-neutral-400">
              <Zap className="w-4 h-4" />
              {execution.total_tokens.toLocaleString()} tokens
            </span>
          )}
          {execution?.total_cost != null && (
            <span className="flex items-center gap-1 text-primary-500">
              <DollarSign className="w-4 h-4" />
              ${execution.total_cost.toFixed(4)}
            </span>
          )}
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex-shrink-0 px-6 pt-4">
        <div className="flex items-center gap-1 bg-neutral-100 dark:bg-neutral-900 rounded-lg p-1">
          {[
            { id: "discussion" as const, label: "Discussion", icon: MessageSquare },
            { id: "compiled" as const, label: "Compiled Output", icon: FileOutput },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  "flex items-center gap-2 px-4 py-2.5 rounded-md text-sm font-medium transition-all flex-1 justify-center",
                  isActive
                    ? "bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white shadow-sm"
                    : "text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300"
                )}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Content area */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        {/* Discussion Tab */}
        {activeTab === "discussion" && (
          <div className="space-y-8">
            {contributions.length === 0 ? (
              <div className="text-center py-12">
                <Users className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-4" />
                <p className="text-neutral-500 dark:text-neutral-400">
                  {isRunning
                    ? "Agents are working... contributions will appear here."
                    : "No contributions yet. Execute the project to begin the workshop."}
                </p>
                {isRunning && (
                  <Loader2 className="w-6 h-6 animate-spin text-primary-500 mx-auto mt-4" />
                )}
              </div>
            ) : (
              Array.from(contributionsByRound.entries())
                .sort(([a], [b]) => a - b)
                .map(([round, roundContributions]) => (
                  <div key={round} className="space-y-4">
                    {/* Round header */}
                    {maxRound > 1 && (
                      <div className="flex items-center gap-3">
                        <div className="flex items-center gap-2 px-3 py-1.5 bg-primary-50 dark:bg-primary-900/20 rounded-full">
                          <Hash className="w-4 h-4 text-primary-500" />
                          <span className="text-sm font-semibold text-primary-600 dark:text-primary-400">
                            Round {round}
                          </span>
                        </div>
                        <div className="h-px flex-1 bg-neutral-200 dark:bg-neutral-700" />
                      </div>
                    )}

                    {/* Agent contributions */}
                    {roundContributions.map((contribution, index) => (
                      <motion.div
                        key={`${contribution.agent_id}-${round}-${index}`}
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: index * 0.05 }}
                        className="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-5"
                      >
                        {/* Agent header */}
                        <div className="flex items-center gap-3 mb-4">
                          <div
                            className={cn(
                              "w-10 h-10 rounded-full flex items-center justify-center text-white text-sm font-bold",
                              getAgentColor(contribution.agent_id)
                            )}
                          >
                            {getInitials(contribution.agent_name)}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-neutral-900 dark:text-white truncate">
                                {contribution.agent_name}
                              </span>
                              <span className="flex-shrink-0 px-2 py-0.5 bg-neutral-100 dark:bg-neutral-700 text-neutral-500 dark:text-neutral-400 text-xs rounded-full">
                                Round {contribution.round_number}
                              </span>
                            </div>
                            {contribution.timestamp && (
                              <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-0.5">
                                {new Date(contribution.timestamp).toLocaleString()}
                              </p>
                            )}
                          </div>
                        </div>

                        {/* Content */}
                        <div
                          className="prose prose-sm dark:prose-invert max-w-none text-neutral-700 dark:text-neutral-300 leading-relaxed"
                          dangerouslySetInnerHTML={{
                            __html: renderContent(contribution.content),
                          }}
                        />
                      </motion.div>
                    ))}
                  </div>
                ))
            )}
          </div>
        )}

        {/* Compiled Output Tab */}
        {activeTab === "compiled" && (
          <div className="space-y-4">
            {/* Export buttons */}
            {(isComplete || execution?.compiled_output) && (
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleCopyCompiled}
                  disabled={!execution?.compiled_output}
                >
                  <Copy className="w-4 h-4" />
                  {copied ? "Copied!" : "Copy to Clipboard"}
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleDownloadMarkdown}
                  disabled={!execution?.compiled_output}
                >
                  <Download className="w-4 h-4" />
                  Download Markdown
                </Button>
              </div>
            )}

            {/* Compiled document */}
            {execution?.compiled_output ? (
              <div className="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-6">
                <div
                  className="prose prose-sm dark:prose-invert max-w-none text-neutral-700 dark:text-neutral-300 leading-relaxed"
                  dangerouslySetInnerHTML={{
                    __html: renderContent(execution.compiled_output),
                  }}
                />
              </div>
            ) : (
              <div className="text-center py-12 bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700">
                <FileOutput className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-4" />
                <p className="text-neutral-500 dark:text-neutral-400">
                  {isComplete
                    ? "No compiled output available for this workshop."
                    : isRunning
                    ? "Compiled output will appear here once the workshop is complete."
                    : "Execute the project to generate compiled output."}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
