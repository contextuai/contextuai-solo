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
  Loader2,
  Check,
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Cloud,
  Server,
} from "lucide-react";
import {
  getPersonas,
  getPersonaTypes,
  createPersona,
  updatePersona,
  deletePersona,
  testConnection,
  type Persona,
  type PersonaType,
  type CredentialField,
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

// Icon mapping for persona type cards (Step 1 grid)
const PERSONA_TYPE_ICONS: Record<string, React.ElementType> = {
  generic: Bot,
  nexus_agent: Bot,
  web_search: Globe,
  web_researcher: Globe,
  postgresql: Database,
  mysql: Database,
  mssql: Database,
  snowflake: Cloud,
  mongodb: Database,
  mcp: Server,
  mcp_server: Server,
  api_integration: Plug,
  api_connector: Plug,
  file_operations: FileText,
  default: Bot,
};

function getPersonaTypeIcon(typeId: string) {
  return PERSONA_TYPE_ICONS[typeId] || PERSONA_TYPE_ICONS.default;
}

// Color mapping for type cards
const TYPE_COLORS: Record<string, { bg: string; text: string }> = {
  generic: { bg: "bg-sky-50 dark:bg-sky-500/10", text: "text-sky-600 dark:text-sky-400" },
  nexus_agent: { bg: "bg-sky-50 dark:bg-sky-500/10", text: "text-sky-600 dark:text-sky-400" },
  web_search: { bg: "bg-emerald-50 dark:bg-emerald-500/10", text: "text-emerald-600 dark:text-emerald-400" },
  web_researcher: { bg: "bg-emerald-50 dark:bg-emerald-500/10", text: "text-emerald-600 dark:text-emerald-400" },
  postgresql: { bg: "bg-blue-50 dark:bg-blue-500/10", text: "text-blue-600 dark:text-blue-400" },
  mysql: { bg: "bg-orange-50 dark:bg-orange-500/10", text: "text-orange-600 dark:text-orange-400" },
  mssql: { bg: "bg-red-50 dark:bg-red-500/10", text: "text-red-600 dark:text-red-400" },
  snowflake: { bg: "bg-cyan-50 dark:bg-cyan-500/10", text: "text-cyan-600 dark:text-cyan-400" },
  mongodb: { bg: "bg-green-50 dark:bg-green-500/10", text: "text-green-600 dark:text-green-400" },
  mcp: { bg: "bg-purple-50 dark:bg-purple-500/10", text: "text-purple-600 dark:text-purple-400" },
  mcp_server: { bg: "bg-purple-50 dark:bg-purple-500/10", text: "text-purple-600 dark:text-purple-400" },
  api_integration: { bg: "bg-indigo-50 dark:bg-indigo-500/10", text: "text-indigo-600 dark:text-indigo-400" },
  api_connector: { bg: "bg-indigo-50 dark:bg-indigo-500/10", text: "text-indigo-600 dark:text-indigo-400" },
  file_operations: { bg: "bg-amber-50 dark:bg-amber-500/10", text: "text-amber-600 dark:text-amber-400" },
};

function getTypeColors(typeId: string) {
  return TYPE_COLORS[typeId] ?? { bg: "bg-neutral-50 dark:bg-neutral-800", text: "text-neutral-600 dark:text-neutral-400" };
}

interface PersonaFormData {
  name: string;
  description: string;
  type: string;
  system_prompt: string;
  category: string;
  credentials: Record<string, string>;
}

const emptyForm: PersonaFormData = {
  name: "",
  description: "",
  type: "generic",
  system_prompt: "",
  category: "General",
  credentials: {},
};

export default function PersonasPage() {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState("All");
  const [wizardOpen, setWizardOpen] = useState(false);
  const [wizardStep, setWizardStep] = useState<1 | 2>(1);
  const [typeSearch, setTypeSearch] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<PersonaFormData>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [personaTypes, setPersonaTypes] = useState<PersonaType[]>([]);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

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
    setWizardStep(1);
    setTypeSearch("");
    setTestResult(null);
    setWizardOpen(true);
  }

  function openEdit(persona: Persona) {
    setForm({
      name: persona.name,
      description: persona.description || "",
      type: persona.type || "generic",
      system_prompt: persona.system_prompt || "",
      category: persona.category || "General",
      credentials: ((persona as unknown as Record<string, unknown>).credentials as Record<string, string>) || {},
    });
    setEditingId(persona.id);
    setWizardStep(2); // Edit opens directly on step 2
    setTestResult(null);
    setWizardOpen(true);
  }

  async function handleSave() {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      const payload: CreatePersonaRequest = {
        name: form.name,
        description: form.description,
        persona_type_id: form.type,
        type: form.type,
        system_prompt: form.system_prompt || undefined,
        category: form.category,
        credentials: form.credentials,
      };

      if (editingId) {
        await updatePersona(editingId, payload);
      } else {
        await createPersona(payload);
      }
      setWizardOpen(false);
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

      {/* Create/Edit Wizard */}
      {wizardOpen && (() => {
        const selectedType = personaTypes.find((pt) => pt.id === form.type);
        const credFields = selectedType?.credentialFields ?? [];
        const isEdit = !!editingId;

        const filteredTypes = personaTypes.filter(
          (pt) =>
            !typeSearch ||
            pt.name.toLowerCase().includes(typeSearch.toLowerCase()) ||
            pt.description?.toLowerCase().includes(typeSearch.toLowerCase())
        );

        function selectType(typeId: string) {
          setForm((prev) => ({ ...prev, type: typeId, credentials: {} }));
          setTestResult(null);
          setWizardStep(2);
        }

        function updateCredential(fieldName: string, value: string) {
          setForm((prev) => ({
            ...prev,
            credentials: { ...prev.credentials, [fieldName]: value },
          }));
        }

        function renderCredentialField(field: CredentialField) {
          const inputClass = "w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50";
          const val = form.credentials[field.name] ?? "";

          if (field.type === "textarea") {
            return <textarea value={val} onChange={(e) => updateCredential(field.name, e.target.value)} rows={4} placeholder={field.placeholder} className={cn(inputClass, "resize-none font-mono")} />;
          }
          if (field.type === "select" && field.options) {
            return (
              <select value={val} onChange={(e) => updateCredential(field.name, e.target.value)} className={inputClass}>
                <option value="">Select...</option>
                {field.options.map((opt) => (<option key={opt} value={opt}>{opt}</option>))}
              </select>
            );
          }
          if (field.type === "boolean") {
            return (
              <label className="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
                <input type="checkbox" checked={val === "true"} onChange={(e) => updateCredential(field.name, e.target.checked ? "true" : "false")} className="rounded border-neutral-300 dark:border-neutral-600 text-primary-500 focus:ring-primary-500/50" />
                {field.label}
              </label>
            );
          }
          const inputType = field.type === "number" ? "number" : field.type === "password" ? "password" : field.type === "email" ? "email" : field.type === "url" ? "url" : "text";
          return <input type={inputType} value={val} onChange={(e) => updateCredential(field.name, e.target.value)} placeholder={field.placeholder} className={inputClass} />;
        }

        return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-white dark:bg-neutral-900 rounded-2xl w-full max-w-4xl mx-4 shadow-2xl border border-neutral-200 dark:border-neutral-700 max-h-[90vh] flex flex-col overflow-hidden">
            {/* Header with step indicator */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-800 shrink-0">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-primary-50 dark:bg-primary-500/10">
                  <Sparkles className="w-5 h-5 text-primary-500" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
                    {isEdit ? "Edit Persona" : "Add New Persona"}
                  </h2>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400">
                    {wizardStep === 1 ? "Choose the type of persona you want to create" : `Configure your ${selectedType?.name ?? "persona"}`}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                {/* Step indicator */}
                <div className="flex items-center gap-2">
                  <div className={cn("w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors", wizardStep >= 1 ? "bg-primary-500 text-white" : "bg-neutral-200 dark:bg-neutral-700 text-neutral-500")}>
                    {wizardStep > 1 ? <Check className="w-3.5 h-3.5" /> : "1"}
                  </div>
                  <div className="w-8 h-0.5 bg-neutral-200 dark:bg-neutral-700">
                    <div className={cn("h-full transition-all", wizardStep >= 2 ? "w-full bg-primary-500" : "w-0")} />
                  </div>
                  <div className={cn("w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors", wizardStep >= 2 ? "bg-primary-500 text-white" : "bg-neutral-200 dark:bg-neutral-700 text-neutral-500")}>
                    2
                  </div>
                </div>
                <button onClick={() => setWizardOpen(false)} className="p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors">
                  <X className="w-5 h-5 text-neutral-500" />
                </button>
              </div>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto">
              {/* ─── Step 1: Select Persona Type ─── */}
              {wizardStep === 1 && (
                <div className="p-6 space-y-4">
                  <div>
                    <h3 className="text-lg font-semibold text-neutral-900 dark:text-white mb-1">
                      Select Persona Type
                    </h3>
                    <p className="text-sm text-neutral-500 dark:text-neutral-400">
                      Choose the type of persona you want to create
                    </p>
                  </div>

                  {/* Search */}
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
                    <input
                      type="text"
                      value={typeSearch}
                      onChange={(e) => setTypeSearch(e.target.value)}
                      placeholder="Search persona types..."
                      className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-sm text-neutral-900 dark:text-neutral-100 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
                    />
                  </div>

                  {/* Type grid */}
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                    {filteredTypes.map((pt) => {
                      const Icon = getPersonaTypeIcon(pt.id);
                      const colors = getTypeColors(pt.id);
                      return (
                        <button
                          key={pt.id}
                          type="button"
                          onClick={() => selectType(pt.id)}
                          className={cn(
                            "flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-all hover:shadow-md text-center group",
                            form.type === pt.id
                              ? "border-primary-500 bg-primary-50 dark:bg-primary-500/10 shadow-md"
                              : "border-neutral-200 dark:border-neutral-700 hover:border-primary-300 dark:hover:border-primary-700"
                          )}
                        >
                          <div className={cn("w-10 h-10 rounded-lg flex items-center justify-center transition-colors", form.type === pt.id ? "bg-primary-100 dark:bg-primary-500/20" : colors.bg)}>
                            <Icon className={cn("w-5 h-5 transition-colors", form.type === pt.id ? "text-primary-500" : colors.text)} />
                          </div>
                          <div>
                            <p className="text-sm font-medium text-neutral-900 dark:text-white leading-tight">
                              {pt.name}
                            </p>
                            <p className="text-[11px] text-neutral-500 dark:text-neutral-400 line-clamp-2 mt-0.5">
                              {pt.description}
                            </p>
                          </div>
                        </button>
                      );
                    })}
                  </div>

                  {filteredTypes.length === 0 && (
                    <div className="text-center py-8 text-sm text-neutral-400">No persona types match your search</div>
                  )}
                </div>
              )}

              {/* ─── Step 2: Configure Details ─── */}
              {wizardStep === 2 && (
                <div className="p-6 space-y-4">
                  {/* Selected type badge */}
                  {selectedType && !isEdit && (
                    <div className="flex items-center gap-2 mb-2">
                      <button type="button" onClick={() => setWizardStep(1)} className="flex items-center gap-1.5 text-xs font-medium text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 transition-colors">
                        <ArrowLeft className="w-3.5 h-3.5" />
                        Change type
                      </button>
                      <span className="text-neutral-300 dark:text-neutral-600">|</span>
                      <span className="text-xs font-medium text-neutral-500 dark:text-neutral-400">
                        {selectedType.icon ? `${selectedType.icon} ` : ""}{selectedType.name}
                      </span>
                    </div>
                  )}

                  {/* Name + Category */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                        Name <span className="text-red-500">*</span>
                      </label>
                      <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g., My Production DB" className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">Category</label>
                      <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50">
                        {PERSONA_CATEGORIES.filter((c) => c !== "All").map((cat) => (<option key={cat} value={cat}>{cat}</option>))}
                      </select>
                    </div>
                  </div>

                  {/* Description */}
                  <div>
                    <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">Description</label>
                    <input type="text" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="A short description of what this persona does" className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-sm text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-primary-500/50" />
                  </div>

                  {/* Type-specific credential fields */}
                  {credFields.length > 0 && (() => {
                    const testableTypes = ["postgresql", "mysql", "mssql", "snowflake", "mongodb", "mcp"];
                    const canTest = testableTypes.includes(form.type);

                    async function handleTestConnection() {
                      setTesting(true);
                      setTestResult(null);
                      try {
                        const result = await testConnection(form.type, form.credentials);
                        setTestResult({ success: result.success, message: result.success ? result.message || "Connection successful" : result.error || "Connection failed" });
                      } catch {
                        setTestResult({ success: false, message: "Connection test failed" });
                      } finally {
                        setTesting(false);
                      }
                    }

                    return (
                    <div className="space-y-3 pt-2 border-t border-neutral-200 dark:border-neutral-700">
                      <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">{selectedType?.name} Configuration</p>
                      {credFields.map((field) => (
                        <div key={field.name}>
                          {field.type !== "boolean" && (
                            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                              {field.label}{field.required && <span className="text-red-500 ml-0.5">*</span>}
                            </label>
                          )}
                          {renderCredentialField(field)}
                        </div>
                      ))}
                      {canTest && (
                        <div className="flex items-center gap-3 pt-1">
                          <button type="button" onClick={handleTestConnection} disabled={testing} className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 disabled:opacity-50 transition-colors">
                            {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plug className="w-3.5 h-3.5" />}
                            {testing ? "Testing..." : "Test Connection"}
                          </button>
                          {testResult && (
                            <span className={cn("flex items-center gap-1 text-xs font-medium", testResult.success ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400")}>
                              {testResult.success ? <Check className="w-3.5 h-3.5" /> : <AlertCircle className="w-3.5 h-3.5" />}
                              {testResult.message}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                    );
                  })()}

                  {/* System prompt */}
                  <div>
                    <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">System Prompt</label>
                    <textarea value={form.system_prompt} onChange={(e) => setForm({ ...form, system_prompt: e.target.value })} rows={4} placeholder="Optional instructions that define how this persona behaves..." className="w-full px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-sm text-neutral-900 dark:text-neutral-100 font-mono focus:outline-none focus:ring-2 focus:ring-primary-500/50 resize-none" />
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between px-6 py-4 border-t border-neutral-200 dark:border-neutral-800 shrink-0">
              <div>
                {wizardStep === 2 && !isEdit && (
                  <button type="button" onClick={() => setWizardStep(1)} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors">
                    <ArrowLeft className="w-4 h-4" />
                    Back
                  </button>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => setWizardOpen(false)} className="px-4 py-2 rounded-lg text-sm font-medium bg-neutral-100 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-600 transition-colors">
                  Cancel
                </button>
                {wizardStep === 1 && (
                  <button onClick={() => setWizardStep(2)} className="flex items-center gap-2 px-5 py-2 rounded-lg bg-primary-500 text-white hover:bg-primary-600 transition-colors text-sm font-medium">
                    Next <ArrowRight className="w-4 h-4" />
                  </button>
                )}
                {wizardStep === 2 && (
                  <button onClick={handleSave} disabled={!form.name.trim() || saving} className="flex items-center gap-2 px-5 py-2 rounded-lg bg-primary-500 text-white hover:bg-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm font-medium">
                    {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                    {saving ? "Saving..." : isEdit ? "Update" : "Create"}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
        );
      })()}
    </div>
  );
}
