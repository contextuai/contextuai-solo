import { useState, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import {
  Sparkles,
  Plus,
  Search,
  Pencil,
  Trash2,
  X,
  MessageSquare,
  Code,
  Database,
  Globe,
  FileText,
  Bot,
  Plug,
  RefreshCw,
} from "lucide-react";
import {
  getPersonas,
  getPersonaTypes,
  createPersona,
  updatePersona,
  deletePersona,
  type Persona,
  type PersonaType,
  type CreatePersonaRequest,
} from "@/lib/api/personas-client";

const PERSONA_ICONS: Record<string, React.ElementType> = {
  chat: MessageSquare,
  code: Code,
  database: Database,
  web: Globe,
  document: FileText,
  api: Plug,
  default: Bot,
};

const PERSONA_CATEGORIES = ["All", "General", "Technical", "Creative", "Business", "Custom"];

function getPersonaIcon(type: string) {
  return PERSONA_ICONS[type] || PERSONA_ICONS.default;
}

interface PersonaFormData {
  name: string;
  description: string;
  type: string;
  system_prompt: string;
  category: string;
}

const emptyForm: PersonaFormData = {
  name: "",
  description: "",
  type: "generic",
  system_prompt: "",
  category: "General",
};

export default function PersonasPage() {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState("All");
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<PersonaFormData>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [personaTypes, setPersonaTypes] = useState<PersonaType[]>([]);

  const loadPersonas = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getPersonas();
      setPersonas(data);
      return data;
    } catch (err) {
      console.warn("Failed to load personas:", err);
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPersonas();
    getPersonaTypes()
      .then(setPersonaTypes)
      .catch((err) => console.warn("Failed to load persona types:", err));
  }, [loadPersonas]);

  const filtered = personas.filter((p) => {
    const matchesSearch =
      !search ||
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.description?.toLowerCase().includes(search.toLowerCase());
    const matchesCategory =
      activeCategory === "All" ||
      (p.category || "General").toLowerCase() === activeCategory.toLowerCase();
    return matchesSearch && matchesCategory;
  });

  function openCreate() {
    setForm(emptyForm);
    setEditingId(null);
    setShowForm(true);
  }

  function openEdit(persona: Persona) {
    setForm({
      name: persona.name,
      description: persona.description || "",
      type: persona.type || "chat",
      system_prompt: persona.system_prompt || "",
      category: persona.category || "General",
    });
    setEditingId(persona.id);
    setShowForm(true);
  }

  async function handleSave() {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      const payload: CreatePersonaRequest = {
        name: form.name,
        description: form.description,
        type: form.type,
        system_prompt: form.system_prompt || undefined,
        category: form.category,
      };

      if (editingId) {
        await updatePersona(editingId, payload);
      } else {
        await createPersona(payload);
      }
      setShowForm(false);
      await loadPersonas();
    } catch (err) {
      console.error("Failed to save persona:", err);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await deletePersona(id);
      setDeleteConfirm(null);
      await loadPersonas();
    } catch (err) {
      console.error("Failed to delete persona:", err);
    }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary-100 dark:bg-primary-900/20 rounded-lg">
            <Sparkles className="w-6 h-6 text-primary-500" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
              Personas
            </h1>
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              {personas.length} persona{personas.length !== 1 ? "s" : ""} &middot; Custom AI behaviors and system prompts
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadPersonas}
            disabled={loading}
            className="p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500 transition-colors"
          >
            <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
          </button>
          <button
            onClick={openCreate}
            className="flex items-center gap-2 px-4 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg text-sm font-medium transition-colors"
          >
            <Plus className="w-4 h-4" />
            Create Persona
          </button>
        </div>
      </div>

      {/* Search + categories */}
      <div className="flex items-center gap-3 mb-6">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search personas..."
            className="w-full pl-10 pr-4 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-sm text-neutral-900 dark:text-neutral-100 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
          />
        </div>
        <div className="flex items-center gap-1">
          {PERSONA_CATEGORIES.map((cat) => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
                activeCategory === cat
                  ? "bg-primary-500 text-white"
                  : "bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 hover:bg-neutral-200 dark:hover:bg-neutral-700"
              )}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Persona grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-40 rounded-xl bg-neutral-100 dark:bg-neutral-800 animate-pulse"
            />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16">
          <Sparkles className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-neutral-700 dark:text-neutral-300 mb-1">
            {personas.length === 0 ? "No personas yet" : "No matches"}
          </h3>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-4">
            {personas.length === 0
              ? "Create your first persona to customize AI behavior."
              : "Try a different search or category."}
          </p>
          {personas.length === 0 && (
            <button
              onClick={openCreate}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg text-sm font-medium transition-colors"
            >
              <Plus className="w-4 h-4" />
              Create Persona
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((persona) => {
            const Icon = getPersonaIcon(persona.type);
            return (
              <div
                key={persona.id}
                className="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 p-5 hover:shadow-md transition-shadow group"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-primary-50 dark:bg-primary-500/10">
                      <Icon className="w-5 h-5 text-primary-500" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-neutral-900 dark:text-neutral-100 text-sm">
                        {persona.name}
                      </h3>
                      <span className="text-xs text-neutral-400 capitalize">
                        {persona.category || persona.type}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() => openEdit(persona)}
                      className="p-1.5 rounded-md hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => setDeleteConfirm(persona.id)}
                      className="p-1.5 rounded-md hover:bg-red-50 dark:hover:bg-red-500/10 text-neutral-400 hover:text-red-500 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
                <p className="text-sm text-neutral-600 dark:text-neutral-400 line-clamp-2 mb-3">
                  {persona.description || "No description"}
                </p>
                {persona.system_prompt && (
                  <div className="text-xs text-neutral-400 dark:text-neutral-500 bg-neutral-50 dark:bg-neutral-900 rounded-lg px-3 py-2 line-clamp-2 font-mono">
                    {persona.system_prompt}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Delete confirmation */}
      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white dark:bg-neutral-800 rounded-xl p-6 max-w-sm mx-4 shadow-xl">
            <h3 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mb-2">
              Delete persona?
            </h3>
            <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-4">
              This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-neutral-100 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-600 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deleteConfirm)}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-red-500 text-white hover:bg-red-600 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create/Edit modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white dark:bg-neutral-800 rounded-xl w-full max-w-lg mx-4 shadow-xl">
            <div className="flex items-center justify-between p-5 border-b border-neutral-200 dark:border-neutral-700">
              <h3 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
                {editingId ? "Edit Persona" : "Create Persona"}
              </h3>
              <button
                onClick={() => setShowForm(false)}
                className="p-1 rounded-md hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-400 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  Name
                </label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="e.g., Code Reviewer"
                  className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  Description
                </label>
                <input
                  type="text"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="A short description of what this persona does"
                  className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                    Type
                  </label>
                  <select
                    value={form.type}
                    onChange={(e) => setForm({ ...form, type: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                  >
                    {personaTypes.length > 0 ? (
                      personaTypes.map((pt) => (
                        <option key={pt.id} value={pt.id}>
                          {pt.icon ? `${pt.icon} ` : ""}{pt.name}
                        </option>
                      ))
                    ) : (
                      <>
                        <option value="generic">Nexus Agent</option>
                        <option value="web_search">Web Researcher</option>
                        <option value="postgresql">PostgreSQL</option>
                        <option value="mysql">MySQL</option>
                        <option value="github">GitHub</option>
                        <option value="api_integration">API Connector</option>
                      </>
                    )}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                    Category
                  </label>
                  <select
                    value={form.category}
                    onChange={(e) => setForm({ ...form, category: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                  >
                    {PERSONA_CATEGORIES.filter((c) => c !== "All").map((cat) => (
                      <option key={cat} value={cat}>
                        {cat}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                  System Prompt
                </label>
                <textarea
                  value={form.system_prompt}
                  onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
                  rows={5}
                  placeholder="Instructions that define how this persona behaves. E.g., 'You are an expert code reviewer. Focus on security, performance, and readability...'"
                  className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-sm text-neutral-900 dark:text-neutral-100 font-mono focus:outline-none focus:ring-2 focus:ring-primary-500/50 resize-none"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 p-5 border-t border-neutral-200 dark:border-neutral-700">
              <button
                onClick={() => setShowForm(false)}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-neutral-100 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-600 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={!form.name.trim() || saving}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-primary-500 text-white hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {saving ? "Saving..." : editingId ? "Update" : "Create"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
