import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import {
  workspaceProjectsApi,
  type ProjectType,
  type WorkspaceProject,
  type CreateProjectPayload,
} from "@/lib/api/workspace-projects-client";
import { workspaceApi, type WorkspaceAgent } from "@/lib/api/workspace-client";
import {
  X,
  FlaskConical,
  Loader2,
  AlertCircle,
  ChevronDown,
  Users,
  Play,
} from "lucide-react";
import { Button } from "@/components/ui/button";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getAgentColor(agentId: string): string {
  const colors = [
    "bg-blue-500", "bg-green-500", "bg-purple-500", "bg-pink-500",
    "bg-teal-500", "bg-orange-500", "bg-indigo-500", "bg-rose-500",
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

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface NewProjectDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (project: WorkspaceProject) => void;
}

export function NewProjectDialog({ isOpen, onClose, onCreated }: NewProjectDialogProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [projectType, setProjectType] = useState("");
  const [selectedAgentIds, setSelectedAgentIds] = useState<string[]>([]);

  const [projectTypes, setProjectTypes] = useState<ProjectType[]>([]);
  const [agents, setAgents] = useState<WorkspaceAgent[]>([]);
  const [loadingTypes, setLoadingTypes] = useState(false);
  const [loadingAgents, setLoadingAgents] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load project types and agents when dialog opens
  useEffect(() => {
    if (!isOpen) return;

    setLoadingTypes(true);
    workspaceProjectsApi
      .listProjectTypes()
      .then((types) => {
        setProjectTypes(types);
        if (types.length > 0 && !projectType) {
          setProjectType(types[0].name);
        }
      })
      .catch(() => setProjectTypes([]))
      .finally(() => setLoadingTypes(false));

    setLoadingAgents(true);
    workspaceApi
      .listAgents()
      .then(setAgents)
      .catch(() => setAgents([]))
      .finally(() => setLoadingAgents(false));
  }, [isOpen]);

  // Reset form when dialog opens
  useEffect(() => {
    if (isOpen) {
      setName("");
      setDescription("");
      setProjectType("");
      setSelectedAgentIds([]);
      setError(null);
    }
  }, [isOpen]);

  const toggleAgent = (agentId: string) => {
    setSelectedAgentIds((prev) =>
      prev.includes(agentId)
        ? prev.filter((id) => id !== agentId)
        : [...prev, agentId]
    );
  };

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError("Project name is required");
      return;
    }
    if (selectedAgentIds.length === 0) {
      setError("Select at least one agent");
      return;
    }

    try {
      setSubmitting(true);
      setError(null);

      const payload: CreateProjectPayload = {
        title: name.trim(),
        description: description.trim(),
        project_type: projectType || "workshop",
        selected_agents: selectedAgentIds,
      };

      const project = await workspaceProjectsApi.create(payload);

      // Auto-execute after creation
      try {
        await workspaceProjectsApi.execute(project.project_id || project.id!);
      } catch {
        // Execution may fail; that is fine, we still created the project
      }

      onCreated(project);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/40 z-40"
            onClick={onClose}
          />

          {/* Dialog */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ type: "spring", damping: 25, stiffness: 300 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="bg-white dark:bg-neutral-900 rounded-2xl shadow-2xl w-full max-w-lg max-h-[85vh] flex flex-col">
              {/* Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-800">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-primary-500 rounded-lg">
                    <FlaskConical className="w-5 h-5 text-white" />
                  </div>
                  <div>
                    <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
                      New Brainstorm
                    </h2>
                    <p className="text-xs text-neutral-500 dark:text-neutral-400">
                      Create a multi-agent workshop
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

              {/* Scrollable form */}
              <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
                {error && (
                  <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm">
                    <AlertCircle className="w-4 h-4 flex-shrink-0" />
                    {error}
                  </div>
                )}

                {/* Name */}
                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                    Project Name
                  </label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className={cn(
                      "w-full px-3 py-2.5 rounded-lg border text-sm transition-colors",
                      "bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white",
                      "border-neutral-300 dark:border-neutral-700",
                      "focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none",
                      "placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
                    )}
                    placeholder="e.g. Q1 Market Analysis"
                  />
                </div>

                {/* Project Type */}
                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                    Project Type
                  </label>
                  {loadingTypes ? (
                    <div className="flex items-center gap-2 py-2.5 text-sm text-neutral-500">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Loading types...
                    </div>
                  ) : (
                    <div className="relative">
                      <select
                        value={projectType}
                        onChange={(e) => setProjectType(e.target.value)}
                        className={cn(
                          "w-full px-3 py-2.5 rounded-lg border text-sm appearance-none transition-colors",
                          "bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white",
                          "border-neutral-300 dark:border-neutral-700",
                          "focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none"
                        )}
                      >
                        <option value="">Select a type...</option>
                        {projectTypes.map((pt) => (
                          <option key={pt.id} value={pt.name}>
                            {pt.name}
                          </option>
                        ))}
                        {projectTypes.length === 0 && (
                          <option value="workshop">Workshop</option>
                        )}
                      </select>
                      <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400 pointer-events-none" />
                    </div>
                  )}
                  {projectTypes.find((pt) => pt.name === projectType)?.description && (
                    <p className="mt-1 text-xs text-neutral-400">
                      {projectTypes.find((pt) => pt.name === projectType)!.description}
                    </p>
                  )}
                </div>

                {/* Description */}
                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                    Description
                  </label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={3}
                    className={cn(
                      "w-full px-3 py-2.5 rounded-lg border text-sm resize-none transition-colors",
                      "bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white",
                      "border-neutral-300 dark:border-neutral-700",
                      "focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none",
                      "placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
                    )}
                    placeholder="Describe what you want your AI team to brainstorm..."
                  />
                </div>

                {/* Agent Selector */}
                <div>
                  <label className="flex items-center gap-1.5 text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                    <Users className="w-3.5 h-3.5" />
                    Select Agents
                    {selectedAgentIds.length > 0 && (
                      <span className="text-xs text-primary-500 font-normal">
                        ({selectedAgentIds.length} selected)
                      </span>
                    )}
                  </label>
                  {loadingAgents ? (
                    <div className="flex items-center gap-2 py-4 justify-center text-sm text-neutral-500">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Loading agents...
                    </div>
                  ) : agents.length === 0 ? (
                    <p className="text-sm text-neutral-500 dark:text-neutral-400 py-4 text-center">
                      No agents available. Create agents first in the Agent Library.
                    </p>
                  ) : (
                    <div className="space-y-2 max-h-48 overflow-y-auto">
                      {agents.map((agent) => {
                        const isSelected = selectedAgentIds.includes(agent.id);
                        return (
                          <label
                            key={agent.id}
                            className={cn(
                              "flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors",
                              isSelected
                                ? "border-primary-300 dark:border-primary-700 bg-primary-50 dark:bg-primary-500/10"
                                : "border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-800"
                            )}
                          >
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => toggleAgent(agent.id)}
                              className="sr-only"
                            />
                            <div
                              className={cn(
                                "w-4 h-4 rounded border-2 flex items-center justify-center flex-shrink-0 transition-colors",
                                isSelected
                                  ? "bg-primary-500 border-primary-500"
                                  : "border-neutral-300 dark:border-neutral-600"
                              )}
                            >
                              {isSelected && (
                                <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                </svg>
                              )}
                            </div>
                            <div
                              className={cn(
                                "w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold flex-shrink-0",
                                getAgentColor(agent.id)
                              )}
                            >
                              {getInitials(agent.name)}
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-neutral-900 dark:text-white truncate">
                                {agent.name}
                              </p>
                              <p className="text-xs text-neutral-500 dark:text-neutral-400 truncate">
                                {agent.role}
                                {agent.description ? ` - ${agent.description}` : ""}
                              </p>
                            </div>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              {/* Footer */}
              <div className="px-6 py-4 border-t border-neutral-200 dark:border-neutral-800 flex items-center justify-end gap-2">
                <button
                  onClick={onClose}
                  className="px-4 py-2 text-sm font-medium text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <Button
                  onClick={handleSubmit}
                  disabled={submitting || !name.trim() || selectedAgentIds.length === 0}
                >
                  {submitting ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Play className="w-4 h-4" />
                  )}
                  {submitting ? "Creating..." : "Create & Run"}
                </Button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
