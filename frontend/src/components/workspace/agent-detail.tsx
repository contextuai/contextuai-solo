import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import {
  type WorkspaceAgent,
  type UpdateAgentPayload,
  workspaceApi,
} from "@/lib/api/workspace-client";
import { getModels, type ModelConfig } from "@/lib/api/models-client";
import {
  X,
  Save,
  Trash2,
  Loader2,
  Bot,
  Wrench,
  Cpu,
  FileText,
  ChevronDown,
  AlertCircle,
  Globe,
  Lock,
} from "lucide-react";

const ROLE_OPTIONS = [
  "Researcher",
  "Writer",
  "Analyst",
  "Designer",
  "Developer",
  "Reviewer",
  "Planner",
  "Custom",
];

const TOOL_OPTIONS = [
  { id: "web_search", label: "Web Search", description: "Search the internet for information" },
  { id: "database", label: "Database", description: "Query and manage databases" },
  { id: "files", label: "Files", description: "Read, write, and manage files" },
  { id: "calculator", label: "Calculator", description: "Perform mathematical calculations" },
  { id: "code_interpreter", label: "Code Interpreter", description: "Execute and analyze code" },
];

interface AgentDetailProps {
  agent: WorkspaceAgent | null;
  isOpen: boolean;
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
}

export function AgentDetail({ agent, isOpen, onClose, onSaved, onDeleted }: AgentDetailProps) {
  const [form, setForm] = useState({
    name: "",
    role: "",
    description: "",
    system_prompt: "",
    tools: [] as string[],
    model_id: "",
    category: "",
    is_public: false,
  });
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (agent) {
      setForm({
        name: agent.name,
        role: agent.role,
        description: agent.description,
        system_prompt: agent.system_prompt,
        tools: agent.tools || [],
        model_id: agent.model_id || "",
        category: agent.category || "",
        is_public: agent.is_public,
      });
      setError(null);
      setConfirmDelete(false);
    }
  }, [agent]);

  useEffect(() => {
    if (isOpen) {
      getModels()
        .then(setModels)
        .catch(() => setModels([]));
    }
  }, [isOpen]);

  const handleSave = async () => {
    if (!agent) return;
    if (!form.name.trim()) {
      setError("Agent name is required");
      return;
    }
    try {
      setSaving(true);
      setError(null);
      const payload: UpdateAgentPayload = {
        name: form.name.trim(),
        role: form.role,
        description: form.description.trim(),
        system_prompt: form.system_prompt.trim(),
        tools: form.tools,
        model_id: form.model_id || undefined,
        category: form.category.trim() || undefined,
        is_public: form.is_public,
      };
      await workspaceApi.updateAgent(agent.id, payload);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save agent");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!agent) return;
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    try {
      setDeleting(true);
      setError(null);
      await workspaceApi.deleteAgent(agent.id);
      onDeleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete agent");
    } finally {
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  const toggleTool = (toolId: string) => {
    setForm((prev) => ({
      ...prev,
      tools: prev.tools.includes(toolId)
        ? prev.tools.filter((t) => t !== toolId)
        : [...prev.tools, toolId],
    }));
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

          {/* Slide-over Panel */}
          <motion.div
            initial={{ opacity: 0, x: 480 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 480 }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            className="fixed right-0 top-0 h-full w-full max-w-lg bg-white dark:bg-neutral-900 shadow-2xl z-50 flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-800">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-primary-500 rounded-lg">
                  <Bot className="w-5 h-5 text-white" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
                    Edit Agent
                  </h2>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400">
                    Modify agent configuration
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
                  Agent Name
                </label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                  className={cn(
                    "w-full px-3 py-2.5 rounded-lg border text-sm transition-colors",
                    "bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white",
                    "border-neutral-300 dark:border-neutral-700",
                    "focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none"
                  )}
                  placeholder="e.g. Market Research Agent"
                />
              </div>

              {/* Role */}
              <div>
                <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                  Role
                </label>
                <div className="relative">
                  <select
                    value={form.role}
                    onChange={(e) => setForm((p) => ({ ...p, role: e.target.value }))}
                    className={cn(
                      "w-full px-3 py-2.5 rounded-lg border text-sm appearance-none transition-colors",
                      "bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white",
                      "border-neutral-300 dark:border-neutral-700",
                      "focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none"
                    )}
                  >
                    <option value="">Select a role...</option>
                    {ROLE_OPTIONS.map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400 pointer-events-none" />
                </div>
              </div>

              {/* Description */}
              <div>
                <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                  Description
                </label>
                <textarea
                  value={form.description}
                  onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
                  rows={3}
                  className={cn(
                    "w-full px-3 py-2.5 rounded-lg border text-sm resize-none transition-colors",
                    "bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white",
                    "border-neutral-300 dark:border-neutral-700",
                    "focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none"
                  )}
                  placeholder="What does this agent do?"
                />
              </div>

              {/* System Prompt */}
              <div>
                <label className="flex items-center gap-1.5 text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                  <FileText className="w-3.5 h-3.5" />
                  System Prompt
                </label>
                <textarea
                  value={form.system_prompt}
                  onChange={(e) => setForm((p) => ({ ...p, system_prompt: e.target.value }))}
                  rows={6}
                  className={cn(
                    "w-full px-3 py-2.5 rounded-lg border text-sm font-mono resize-none transition-colors",
                    "bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white",
                    "border-neutral-300 dark:border-neutral-700",
                    "focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none"
                  )}
                  placeholder="You are a helpful AI assistant that..."
                />
                <p className="mt-1 text-xs text-neutral-400">
                  Instructions that define the agent's behavior and expertise.
                </p>
              </div>

              {/* Tools */}
              <div>
                <label className="flex items-center gap-1.5 text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                  <Wrench className="w-3.5 h-3.5" />
                  Tools
                </label>
                <div className="space-y-2">
                  {TOOL_OPTIONS.map((tool) => (
                    <label
                      key={tool.id}
                      className={cn(
                        "flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors",
                        form.tools.includes(tool.id)
                          ? "border-primary-300 dark:border-primary-700 bg-primary-50 dark:bg-primary-500/10"
                          : "border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-800"
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={form.tools.includes(tool.id)}
                        onChange={() => toggleTool(tool.id)}
                        className="sr-only"
                      />
                      <div
                        className={cn(
                          "w-4 h-4 rounded border-2 flex items-center justify-center flex-shrink-0 transition-colors",
                          form.tools.includes(tool.id)
                            ? "bg-primary-500 border-primary-500"
                            : "border-neutral-300 dark:border-neutral-600"
                        )}
                      >
                        {form.tools.includes(tool.id) && (
                          <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-neutral-900 dark:text-white">{tool.label}</p>
                        <p className="text-xs text-neutral-500 dark:text-neutral-400">{tool.description}</p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              {/* Model */}
              <div>
                <label className="flex items-center gap-1.5 text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                  <Cpu className="w-3.5 h-3.5" />
                  Model
                </label>
                <div className="relative">
                  <select
                    value={form.model_id}
                    onChange={(e) => setForm((p) => ({ ...p, model_id: e.target.value }))}
                    className={cn(
                      "w-full px-3 py-2.5 rounded-lg border text-sm appearance-none transition-colors",
                      "bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white",
                      "border-neutral-300 dark:border-neutral-700",
                      "focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none"
                    )}
                  >
                    <option value="">Default model</option>
                    {models.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name} ({m.provider})
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400 pointer-events-none" />
                </div>
              </div>

              {/* Category */}
              <div>
                <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                  Category
                </label>
                <input
                  type="text"
                  value={form.category}
                  onChange={(e) => setForm((p) => ({ ...p, category: e.target.value }))}
                  className={cn(
                    "w-full px-3 py-2.5 rounded-lg border text-sm transition-colors",
                    "bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white",
                    "border-neutral-300 dark:border-neutral-700",
                    "focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none"
                  )}
                  placeholder="e.g. Research, Marketing, Engineering"
                />
              </div>

              {/* Visibility */}
              <div className="flex items-center justify-between p-3 rounded-lg border border-neutral-200 dark:border-neutral-700">
                <div className="flex items-center gap-3">
                  {form.is_public ? (
                    <Globe className="w-4 h-4 text-primary-500" />
                  ) : (
                    <Lock className="w-4 h-4 text-neutral-400" />
                  )}
                  <div>
                    <p className="text-sm font-medium text-neutral-900 dark:text-white">
                      {form.is_public ? "Public" : "Private"}
                    </p>
                    <p className="text-xs text-neutral-500 dark:text-neutral-400">
                      {form.is_public ? "Visible to all users" : "Only visible to you"}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setForm((p) => ({ ...p, is_public: !p.is_public }))}
                  className={cn(
                    "relative w-10 h-6 rounded-full transition-colors",
                    form.is_public ? "bg-primary-500" : "bg-neutral-300 dark:bg-neutral-600"
                  )}
                >
                  <span
                    className={cn(
                      "absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform",
                      form.is_public && "translate-x-4"
                    )}
                  />
                </button>
              </div>
            </div>

            {/* Footer Actions */}
            <div className="px-6 py-4 border-t border-neutral-200 dark:border-neutral-800 flex items-center justify-between">
              <button
                onClick={handleDelete}
                disabled={deleting}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                  confirmDelete
                    ? "bg-red-600 hover:bg-red-700 text-white"
                    : "text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
                )}
              >
                {deleting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Trash2 className="w-4 h-4" />
                )}
                {confirmDelete ? "Confirm Delete" : "Delete"}
              </button>
              <div className="flex items-center gap-2">
                <button
                  onClick={onClose}
                  className="px-4 py-2 text-sm font-medium text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className={cn(
                    "flex items-center gap-1.5 px-5 py-2 rounded-lg text-sm font-medium text-white transition-colors",
                    "bg-primary-500 hover:bg-primary-600 disabled:opacity-50"
                  )}
                >
                  {saving ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Save className="w-4 h-4" />
                  )}
                  Save Changes
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
