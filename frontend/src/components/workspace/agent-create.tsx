import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { type CreateAgentPayload, workspaceApi } from "@/lib/api/workspace-client";
import { getModels, type ModelConfig } from "@/lib/api/models-client";
import {
  X,
  Loader2,
  Wrench,
  Cpu,
  FileText,
  ChevronDown,
  AlertCircle,
  Sparkles,
  Plus,
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

const PROMPT_TEMPLATES: Record<string, string> = {
  Researcher: "You are a thorough research agent. Gather comprehensive information from multiple sources, cross-reference facts, and provide well-cited summaries. Always prioritize accuracy and present findings in a structured format.",
  Writer: "You are a skilled writing agent. Create clear, engaging, and well-structured content tailored to the audience. Maintain consistent tone and style, and proofread for grammar and clarity.",
  Analyst: "You are a data-driven analyst agent. Examine data carefully, identify patterns and trends, and provide actionable insights. Use quantitative reasoning and present findings with supporting evidence.",
  Designer: "You are a creative design agent. Focus on user experience, visual hierarchy, and accessibility. Provide design recommendations with clear rationale and consider both aesthetics and functionality.",
  Developer: "You are a proficient software development agent. Write clean, maintainable code following best practices. Consider edge cases, performance, and security. Document your approach clearly.",
  Reviewer: "You are a meticulous review agent. Evaluate work thoroughly, provide constructive feedback, and suggest specific improvements. Balance critique with recognition of strengths.",
  Planner: "You are a strategic planning agent. Break down complex goals into actionable steps, identify dependencies and risks, and create realistic timelines. Adapt plans based on constraints and priorities.",
};

interface AgentCreateProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export function AgentCreate({ isOpen, onClose, onCreated }: AgentCreateProps) {
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
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setForm({
        name: "",
        role: "",
        description: "",
        system_prompt: "",
        tools: [],
        model_id: "",
        category: "",
        is_public: false,
      });
      setError(null);
      getModels()
        .then(setModels)
        .catch(() => setModels([]));
    }
  }, [isOpen]);

  const handleRoleChange = (role: string) => {
    setForm((prev) => ({
      ...prev,
      role,
      system_prompt: prev.system_prompt || PROMPT_TEMPLATES[role] || "",
    }));
  };

  const handleCreate = async () => {
    if (!form.name.trim()) {
      setError("Agent name is required");
      return;
    }
    if (!form.role) {
      setError("Please select a role");
      return;
    }
    try {
      setCreating(true);
      setError(null);
      const payload: CreateAgentPayload = {
        name: form.name.trim(),
        role: form.role,
        description: form.description.trim(),
        system_prompt: form.system_prompt.trim(),
        tools: form.tools,
        model_id: form.model_id || undefined,
        icon: undefined,
        category: form.category.trim() || undefined,
        is_public: form.is_public,
      };
      await workspaceApi.createAgent(payload);
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create agent");
    } finally {
      setCreating(false);
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

          {/* Dialog */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: "spring", damping: 25, stiffness: 300 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
          >
            <div className="w-full max-w-xl max-h-[90vh] bg-white dark:bg-neutral-900 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
              {/* Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-800">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-gradient-to-br from-primary-500 to-primary-600 rounded-lg">
                    <Sparkles className="w-5 h-5 text-white" />
                  </div>
                  <div>
                    <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
                      Create Agent
                    </h2>
                    <p className="text-xs text-neutral-500 dark:text-neutral-400">
                      Configure a new AI agent for your workspace
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

                {/* Name + Role row */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                      Agent Name *
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
                      placeholder="e.g. Market Researcher"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                      Role *
                    </label>
                    <div className="relative">
                      <select
                        value={form.role}
                        onChange={(e) => handleRoleChange(e.target.value)}
                        className={cn(
                          "w-full px-3 py-2.5 rounded-lg border text-sm appearance-none transition-colors",
                          "bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white",
                          "border-neutral-300 dark:border-neutral-700",
                          "focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none"
                        )}
                      >
                        <option value="">Select role...</option>
                        {ROLE_OPTIONS.map((r) => (
                          <option key={r} value={r}>{r}</option>
                        ))}
                      </select>
                      <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400 pointer-events-none" />
                    </div>
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
                    rows={2}
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
                    rows={5}
                    className={cn(
                      "w-full px-3 py-2.5 rounded-lg border text-sm font-mono resize-none transition-colors",
                      "bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white",
                      "border-neutral-300 dark:border-neutral-700",
                      "focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 outline-none"
                    )}
                    placeholder="You are a helpful AI assistant that..."
                  />
                  {form.role && PROMPT_TEMPLATES[form.role] && !form.system_prompt && (
                    <button
                      onClick={() => setForm((p) => ({ ...p, system_prompt: PROMPT_TEMPLATES[p.role] || "" }))}
                      className="mt-1.5 text-xs text-primary-500 hover:text-primary-600 font-medium"
                    >
                      Use suggested template for {form.role}
                    </button>
                  )}
                </div>

                {/* Tools */}
                <div>
                  <label className="flex items-center gap-1.5 text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                    <Wrench className="w-3.5 h-3.5" />
                    Tools
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    {TOOL_OPTIONS.map((tool) => (
                      <label
                        key={tool.id}
                        className={cn(
                          "flex items-center gap-2.5 p-2.5 rounded-lg border cursor-pointer transition-colors",
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
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-neutral-900 dark:text-white truncate">{tool.label}</p>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Model + Category row */}
                <div className="grid grid-cols-2 gap-4">
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
                            {m.name}
                          </option>
                        ))}
                      </select>
                      <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400 pointer-events-none" />
                    </div>
                  </div>
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
                      placeholder="e.g. Research"
                    />
                  </div>
                </div>
              </div>

              {/* Footer */}
              <div className="px-6 py-4 border-t border-neutral-200 dark:border-neutral-800 flex items-center justify-end gap-2">
                <button
                  onClick={onClose}
                  className="px-4 py-2.5 text-sm font-medium text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreate}
                  disabled={creating}
                  className={cn(
                    "flex items-center gap-1.5 px-5 py-2.5 rounded-lg text-sm font-medium text-white transition-colors",
                    "bg-primary-500 hover:bg-primary-600 disabled:opacity-50"
                  )}
                >
                  {creating ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Plus className="w-4 h-4" />
                  )}
                  Create Agent
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
