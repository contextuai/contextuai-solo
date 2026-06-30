import { useState, useCallback, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useTheme } from "@/components/providers/theme-provider";
import { useSettings } from "@/hooks/use-settings";
import { useAiMode } from "@/contexts/ai-mode-context";
import { Tabs, Button, Input, Textarea, Select, Badge, Dialog, TagInput } from "@/components/ui";
import { PROVIDER_GUIDES } from "@/data/provider-guides";
import { ProviderCard } from "@/components/settings/provider-card";
import {
  listCloudProviders,
  saveCloudProvider,
  deleteCloudProvider,
  testCloudProvider,
  testSavedCloudProvider,
  type CloudProvider,
  type CloudProviderType,
  type TestResult,
} from "@/lib/api/cloud-providers-client";
import {
  Settings,
  Cpu,
  Palette,
  MessageSquareText,
  Database,
  Info,
  Cloud,
  Check,
  Loader2,
  ExternalLink,
  Sun,
  Moon,
  Monitor as MonitorIcon,
  Download,
  Upload,
  Trash2,
  HardDrive,
  RefreshCw,
  AlertCircle,
} from "lucide-react";

// PROVIDER_DEFS removed — replaced by PROVIDER_GUIDES in data/provider-guides.ts

const INDUSTRIES = [
  { value: "technology", label: "Technology" },
  { value: "marketing", label: "Marketing & Advertising" },
  { value: "finance", label: "Finance & Banking" },
  { value: "healthcare", label: "Healthcare" },
  { value: "education", label: "Education" },
  { value: "ecommerce", label: "E-commerce & Retail" },
  { value: "creative", label: "Creative & Design" },
  { value: "consulting", label: "Consulting" },
  { value: "legal", label: "Legal" },
  { value: "real_estate", label: "Real Estate" },
  { value: "manufacturing", label: "Manufacturing" },
  { value: "other", label: "Other" },
];

const SETTINGS_TABS = [
  { id: "providers", label: "AI Providers", icon: <Cpu className="w-4 h-4" /> },
  { id: "brand", label: "Brand Voice", icon: <MessageSquareText className="w-4 h-4" /> },
  { id: "appearance", label: "Appearance", icon: <Palette className="w-4 h-4" /> },
  { id: "data", label: "Data & Export", icon: <Database className="w-4 h-4" /> },
  { id: "about", label: "About", icon: <Info className="w-4 h-4" /> },
];

// ─── Local AI Config (inline) ────────────────────────────────────────────────

interface LocalModelInfo {
  id: string;
  name: string;
  file: string;
  downloaded: boolean;
  size_bytes: number;
  tier: string;
  ram_required_gb?: number;
}

function LocalAIConfig() {
  const [models, setModels] = useState<LocalModelInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState<string | null>(null);

  const loadModels = async () => {
    try {
      const baseUrl = import.meta.env.VITE_API_URL || "http://127.0.0.1:18741/api/v1";
      const res = await fetch(`${baseUrl}/local-models/catalog`);
      if (res.ok) {
        const data = await res.json();
        const mapped: LocalModelInfo[] = (data.models || []).map((m: Record<string, unknown>) => ({
          id: m.id as string,
          name: m.name as string,
          file: (m.id as string) + ".gguf",
          downloaded: !!m.installed,
          size_bytes: ((m.size_gb as number) || 0) * 1e9,
          tier: m.parameter_size as string || "",
          ram_required_gb: m.ram_required_gb as number,
        }));
        setModels(mapped);
      }
    } catch {
      // ignore
    }
    setLoading(false);
  };

  useEffect(() => { loadModels(); }, []);

  const handleDownload = async (modelId: string) => {
    setDownloading(modelId);
    try {
      const baseUrl = import.meta.env.VITE_API_URL || "http://127.0.0.1:18741/api/v1";
      await fetch(`${baseUrl}/local-models/download`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: modelId }),
      });

      // Poll progress
      const poll = setInterval(async () => {
        try {
          const res = await fetch(`${baseUrl}/local-models/catalog`);
          if (res.ok) {
            const catalog = await res.json();
            const catalogModel = (catalog.models || []).find((x: Record<string, unknown>) => x.id === modelId);
            if (catalogModel?.installed) {
              clearInterval(poll);
              setDownloading(null);
              loadModels();
              // Sync to DB so model appears in chat dropdown
              fetch(`${baseUrl}/local-models/sync`, { method: "POST" }).catch(() => {});
            }
          }
        } catch { /* ignore */ }
      }, 2000);
    } catch {
      setDownloading(null);
    }
  };

  const handleDelete = async (modelId: string) => {
    try {
      const baseUrl = import.meta.env.VITE_API_URL || "http://127.0.0.1:18741/api/v1";
      await fetch(`${baseUrl}/local-models/${modelId}`, { method: "DELETE" });
      loadModels();
    } catch { /* ignore */ }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-3 text-xs text-neutral-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading local models...
      </div>
    );
  }

  const downloadedCount = models.filter((m) => m.downloaded).length;

  return (
    <div className="space-y-3">
      <p className="text-xs text-neutral-500 dark:text-neutral-400">
        {downloadedCount} of {models.length} models downloaded. Models run entirely on your CPU.
      </p>
      {models.map((m) => (
        <div
          key={m.id}
          className={cn(
            "flex items-center justify-between p-3 rounded-xl border",
            m.downloaded
              ? "border-emerald-200 dark:border-emerald-500/20 bg-emerald-50/50 dark:bg-emerald-500/5"
              : "border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900"
          )}
        >
          <div>
            <p className="text-sm font-medium text-neutral-900 dark:text-white">{m.name}</p>
            <p className="text-xs text-neutral-500 mt-0.5">
              {(m.size_bytes / 1e9).toFixed(1)} GB
              {m.ram_required_gb != null && <span className="ml-2">RAM: {m.ram_required_gb} GB</span>}
              {m.tier && <span className="ml-2 text-neutral-400">({m.tier})</span>}
            </p>
          </div>
          {m.downloaded ? (
            <div className="flex items-center gap-2">
              <Badge variant="success" dot>Downloaded</Badge>
              <Button variant="ghost" size="sm" onClick={() => handleDelete(m.id)}>
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            </div>
          ) : downloading === m.id ? (
            <div className="flex items-center gap-2 text-xs text-neutral-500">
              <Loader2 className="w-4 h-4 animate-spin" /> Downloading...
            </div>
          ) : (
            <Button variant="secondary" size="sm" onClick={() => handleDownload(m.id)}>
              <Download className="w-3.5 h-3.5" /> Download
            </Button>
          )}
        </div>
      ))}
    </div>
  );
}

// ─── AI Mode Card ───────────────────────────────────────────────────────────

function AiModeCard() {
  const { aiMode, setAiMode } = useAiMode();

  return (
    <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 mb-6">
      <h3 className="text-sm font-semibold text-neutral-900 dark:text-white mb-1">AI Mode</h3>
      <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-4">
        Choose where your AI runs. This applies globally across Chat, Workspace, and Crews.
      </p>
      <div className="grid grid-cols-2 gap-3">
        <button
          onClick={() => setAiMode("local")}
          className={cn(
            "relative p-4 rounded-xl border-2 text-left transition-all",
            aiMode === "local"
              ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-500/5"
              : "border-neutral-200 dark:border-neutral-700 hover:border-neutral-300 dark:hover:border-neutral-600"
          )}
        >
          <div className="flex items-center gap-2 mb-1.5">
            <MonitorIcon className={cn("w-4 h-4", aiMode === "local" ? "text-emerald-500" : "text-neutral-400")} />
            <span className={cn("text-sm font-medium", aiMode === "local" ? "text-emerald-600 dark:text-emerald-400" : "text-neutral-900 dark:text-white")}>
              Local AI
            </span>
          </div>
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Free, private, offline. Smaller models, slower on CPU.
          </p>
          {aiMode === "local" && <div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-emerald-500" />}
        </button>
        <button
          onClick={() => setAiMode("cloud")}
          className={cn(
            "relative p-4 rounded-xl border-2 text-left transition-all",
            aiMode === "cloud"
              ? "border-sky-500 bg-sky-50 dark:bg-sky-500/5"
              : "border-neutral-200 dark:border-neutral-700 hover:border-neutral-300 dark:hover:border-neutral-600"
          )}
        >
          <div className="flex items-center gap-2 mb-1.5">
            <Cloud className={cn("w-4 h-4", aiMode === "cloud" ? "text-sky-500" : "text-neutral-400")} />
            <span className={cn("text-sm font-medium", aiMode === "cloud" ? "text-sky-600 dark:text-sky-400" : "text-neutral-900 dark:text-white")}>
              Cloud
            </span>
          </div>
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Requires API keys. Larger models, faster inference.
          </p>
          {aiMode === "cloud" && <div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-sky-500" />}
        </button>
      </div>
    </div>
  );
}

// ─── AI Providers Tab ───────────────────────────────────────────────────────

function AIProvidersTab() {
  const [savedProviders, setSavedProviders] = useState<CloudProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await listCloudProviders();
      setSavedProviders(list);
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to load providers");
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    listCloudProviders()
      .then((list) => {
        if (mounted) { setSavedProviders(list); setLoadError(null); }
      })
      .catch((err) => {
        if (mounted) setLoadError(err instanceof Error ? err.message : "Failed to load providers");
      })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, []);

  // Index saved rows by provider_type for O(1) lookup
  const savedByType = savedProviders.reduce<Partial<Record<CloudProviderType, CloudProvider>>>(
    (acc, p) => ({ ...acc, [p.provider_type]: p }),
    {},
  );

  const handleSave = useCallback(
    async (providerType: string, config: Record<string, string>) => {
      // Ollama and OpenAI-compatible are now first-class provider rows too, so
      // a typed base_url persists (was previously dropped for Ollama).
      await saveCloudProvider({ provider_type: providerType as CloudProviderType, config });
      await refresh();
    },
    [refresh],
  );

  const handleRemove = useCallback(
    async (providerId: string) => {
      await deleteCloudProvider(providerId);
      await refresh();
    },
    [refresh],
  );

  const handleTest = useCallback(
    async (
      providerType: string,
      config: Record<string, string> | undefined,
      savedId?: string,
    ): Promise<TestResult> => {
      if (config === undefined && savedId) {
        const result = await testSavedCloudProvider(savedId);
        await refresh();
        return result;
      }
      // Ollama: test by fetching the local tags endpoint directly
      if (providerType === "ollama") {
        const baseUrl = config?.base_url || "http://localhost:11434";
        try {
          const res = await fetch(`${baseUrl}/api/tags`, { signal: AbortSignal.timeout(5000) });
          if (res.ok) return { ok: true, latency_ms: 0 };
          return { ok: false, latency_ms: 0, error: `Ollama returned ${res.status}` };
        } catch (err) {
          return { ok: false, latency_ms: 0, error: "Ollama not reachable" };
        }
      }
      return testCloudProvider({ provider_type: providerType as CloudProviderType, config: config ?? {} });
    },
    [refresh],
  );

  return (
    <div className="space-y-4">
      <AiModeCard />

      <div>
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-white">AI Providers</h3>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
          Set up API keys for cloud providers, or connect Ollama for local inference. Keys are stored locally and never leave your machine.
        </p>
      </div>

      {loadError && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-800/50 text-xs text-red-600 dark:text-red-400">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {loadError}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-primary-500" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {/* Local AI Built-in — always at top, accordion only */}
          <div
            data-testid="provider-card-local-ai"
            className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 overflow-hidden"
          >
            <button
              data-testid="steps-toggle-local-ai"
              onClick={() => {
                const el = document.getElementById("local-ai-expand");
                if (el) el.classList.toggle("hidden");
              }}
              className="w-full flex items-center gap-4 p-4 text-left"
            >
              <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-green-600 shrink-0">
                <MonitorIcon className="w-5 h-5 text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <span className="text-sm font-semibold text-neutral-900 dark:text-white">
                  Local AI (Built-in)
                </span>
                <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                  Downloaded GGUF models running on your CPU — free, private, offline
                </p>
              </div>
              <Badge variant="success" dot>Always available</Badge>
            </button>
            <div id="local-ai-expand" className="hidden px-4 pb-4 pt-1 border-t border-neutral-100 dark:border-neutral-800">
              <LocalAIConfig />
            </div>
          </div>

          {/* Cloud + Ollama provider cards */}
          {PROVIDER_GUIDES.map((guide) => {
            // Ollama is now a first-class provider row too, so its saved /
            // connected state is tracked the same way as the cloud providers.
            const saved = savedByType[guide.id as CloudProviderType];
            return (
              <ProviderCard
                key={guide.id}
                guide={guide}
                saved={saved}
                onSave={handleSave}
                onTest={(type, config) => handleTest(type, config, saved?.provider_id)}
                onRemove={async () => {
                  if (saved) await handleRemove(saved.provider_id);
                }}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Brand Voice Tab ────────────────────────────────────────────────────────

function BrandVoiceTab() {
  const { settings, updateBrandVoice, saveBrandVoice, saving } = useSettings();
  const bv = settings.brand_voice;
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    await saveBrandVoice();
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  // Generate preview sentence
  const previewSentence = useCallback(() => {
    const name = bv.business_name || "your business";
    const audience = bv.target_audience || "your audience";
    const voice = bv.voice
      ? bv.voice.toLowerCase().includes("professional")
        ? "a professional and authoritative"
        : bv.voice.toLowerCase().includes("friendly")
          ? "a warm and approachable"
          : bv.voice.toLowerCase().includes("casual")
            ? "a relaxed and conversational"
            : "a tailored"
      : "a natural";
    return `I'll communicate on behalf of ${name} using ${voice} tone, crafted to resonate with ${audience}.`;
  }, [bv.business_name, bv.target_audience, bv.voice]);

  return (
    <div className="space-y-6">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-white">Brand Voice</h3>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
          Define your brand identity so AI responses match your tone and audience.
        </p>
      </div>

      <div className="bg-white dark:bg-neutral-900 rounded-2xl border border-neutral-200 dark:border-neutral-800 p-6 space-y-5">
        <Input
          label="Business Name"
          value={bv.business_name}
          onChange={(e) => updateBrandVoice({ business_name: e.target.value })}
          placeholder="e.g. Acme Corp"
        />

        <Select
          label="Industry"
          value={bv.industry}
          onChange={(e) => updateBrandVoice({ industry: e.target.value })}
          placeholder="Select your industry"
          options={INDUSTRIES}
        />

        <Textarea
          label="Brand Description"
          value={bv.description}
          onChange={(e) => updateBrandVoice({ description: e.target.value })}
          placeholder="Briefly describe what your business does and what makes it unique..."
          rows={3}
        />

        <Textarea
          label="Brand Voice"
          value={bv.voice}
          onChange={(e) => updateBrandVoice({ voice: e.target.value })}
          placeholder="Describe how your brand should sound. e.g. Professional yet approachable, data-driven, concise..."
          rows={3}
          helperText="This guides the AI's tone in all generated content"
        />

        <Input
          label="Target Audience"
          value={bv.target_audience}
          onChange={(e) => updateBrandVoice({ target_audience: e.target.value })}
          placeholder="e.g. Small business owners, marketing professionals, enterprise IT teams"
        />

        <TagInput
          label="Content Topics"
          tags={bv.topics}
          onChange={(topics) => updateBrandVoice({ topics })}
          placeholder="Type a topic and press Enter"
          helperText="Add topics you frequently create content about"
        />
      </div>

      {/* Brand Voice Preview */}
      {(bv.business_name || bv.voice || bv.target_audience) && (
        <div className="bg-primary-50 dark:bg-primary-500/5 rounded-2xl border border-primary-200 dark:border-primary-500/20 p-5">
          <p className="text-xs font-semibold text-primary-600 dark:text-primary-400 uppercase tracking-wider mb-2">
            Brand Voice Preview
          </p>
          <p className="text-sm text-neutral-700 dark:text-neutral-300 italic leading-relaxed">
            &ldquo;{previewSentence()}&rdquo;
          </p>
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Saving...
            </>
          ) : saved ? (
            <>
              <Check className="w-4 h-4" />
              Saved
            </>
          ) : (
            "Save Brand Voice"
          )}
        </Button>
      </div>
    </div>
  );
}

// ─── Appearance Tab ─────────────────────────────────────────────────────────

function AppearanceTab() {
  const { theme, setTheme } = useTheme();
  const { settings, updateSettings } = useSettings();

  const themeOptions: { id: "light" | "dark" | "system"; label: string; icon: typeof Sun; desc: string }[] = [
    { id: "light", label: "Light", icon: Sun, desc: "Always use light theme" },
    { id: "dark", label: "Dark", icon: Moon, desc: "Always use dark theme" },
    { id: "system", label: "System", icon: MonitorIcon, desc: "Follow system preference" },
  ];

  const fontSizes: { id: "small" | "medium" | "large"; label: string; sample: string }[] = [
    { id: "small", label: "Small", sample: "text-xs" },
    { id: "medium", label: "Medium", sample: "text-sm" },
    { id: "large", label: "Large", sample: "text-base" },
  ];

  return (
    <div className="space-y-8">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-white">Appearance</h3>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
          Customize the look and feel of your workspace.
        </p>
      </div>

      {/* Theme Selection */}
      <div>
        <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-3">
          Theme
        </label>
        <div className="grid grid-cols-3 gap-3">
          {themeOptions.map((opt) => {
            const Icon = opt.icon;
            const isSelected = theme === opt.id;
            return (
              <button
                key={opt.id}
                onClick={() => {
                  setTheme(opt.id);
                  updateSettings({ theme: opt.id });
                }}
                className={cn(
                  "flex flex-col items-center gap-2.5 p-5 rounded-2xl border-2 transition-all",
                  isSelected
                    ? "border-primary-500 bg-primary-50 dark:bg-primary-500/5"
                    : "border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 hover:border-neutral-300 dark:hover:border-neutral-700"
                )}
              >
                <div
                  className={cn(
                    "flex items-center justify-center w-10 h-10 rounded-xl",
                    isSelected
                      ? "bg-primary-500 text-white"
                      : "bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400"
                  )}
                >
                  <Icon className="w-5 h-5" />
                </div>
                <span className="text-sm font-medium text-neutral-900 dark:text-white">
                  {opt.label}
                </span>
                <span className="text-xs text-neutral-500 dark:text-neutral-400 text-center">
                  {opt.desc}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Font Size */}
      <div>
        <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-3">
          Font Size
        </label>
        <div className="flex gap-3">
          {fontSizes.map((fs) => (
            <button
              key={fs.id}
              onClick={() => updateSettings({ font_size: fs.id })}
              className={cn(
                "flex-1 flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-all",
                settings.font_size === fs.id
                  ? "border-primary-500 bg-primary-50 dark:bg-primary-500/5"
                  : "border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 hover:border-neutral-300 dark:hover:border-neutral-700"
              )}
            >
              <span className={cn("font-medium text-neutral-900 dark:text-white", fs.sample)}>
                Aa
              </span>
              <span className="text-xs text-neutral-500 dark:text-neutral-400">{fs.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Sidebar Default */}
      <div>
        <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-3">
          Sidebar Default State
        </label>
        <div className="flex gap-3">
          {(["expanded", "collapsed"] as const).map((state) => (
            <button
              key={state}
              onClick={() => updateSettings({ sidebar_default: state })}
              className={cn(
                "flex-1 px-4 py-3 rounded-xl border-2 text-sm font-medium capitalize transition-all",
                settings.sidebar_default === state
                  ? "border-primary-500 bg-primary-50 dark:bg-primary-500/5 text-primary-600 dark:text-primary-400"
                  : "border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 text-neutral-600 dark:text-neutral-400 hover:border-neutral-300 dark:hover:border-neutral-700"
              )}
            >
              {state}
            </button>
          ))}
        </div>
      </div>

      {/* Accent Color (disabled) */}
      <div>
        <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-3">
          Accent Color
        </label>
        <div className="flex items-center gap-3 p-4 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900">
          <div className="w-8 h-8 rounded-lg bg-primary-500 ring-2 ring-primary-500/20" />
          <div>
            <p className="text-sm font-medium text-neutral-900 dark:text-white">Brand Orange</p>
            <p className="text-xs text-neutral-500 dark:text-neutral-400">#FF4700</p>
          </div>
          <Badge variant="default" className="ml-auto">Coming soon</Badge>
        </div>
      </div>
    </div>
  );
}

// ─── Data & Export Tab ──────────────────────────────────────────────────────

function DataExportTab() {
  const [showClearDialog, setShowClearDialog] = useState(false);
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    setExporting(true);
    try {
      const data: Record<string, string | null> = {};
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && key.startsWith("contextuai-solo")) {
          data[key] = localStorage.getItem(key);
        }
      }
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `contextuai-solo-backup-${new Date().toISOString().split("T")[0]}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Export failed:", err);
    }
    setExporting(false);
  };

  const handleImport = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json";
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      try {
        const text = await file.text();
        const data = JSON.parse(text) as Record<string, string>;
        Object.entries(data).forEach(([key, value]) => {
          if (key.startsWith("contextuai-solo")) {
            localStorage.setItem(key, value);
          }
        });
        window.location.reload();
      } catch (err) {
        console.error("Import failed:", err);
      }
    };
    input.click();
  };

  const handleClearAll = () => {
    const keys: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith("contextuai-solo")) {
        keys.push(key);
      }
    }
    keys.forEach((key) => localStorage.removeItem(key));
    setShowClearDialog(false);
    window.location.reload();
  };

  return (
    <div className="space-y-6">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-white">Data & Export</h3>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
          Manage your data, create backups, and restore from previous exports.
        </p>
      </div>

      {/* Export */}
      <div className="bg-white dark:bg-neutral-900 rounded-2xl border border-neutral-200 dark:border-neutral-800 p-5">
        <div className="flex items-start gap-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-500/10 shrink-0">
            <Download className="w-5 h-5 text-blue-500" />
          </div>
          <div className="flex-1">
            <h4 className="text-sm font-semibold text-neutral-900 dark:text-white">Export Data</h4>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1 mb-3">
              Download all your settings, brand voice, and provider configurations as a JSON backup file.
            </p>
            <Button variant="secondary" size="sm" onClick={handleExport} disabled={exporting}>
              {exporting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Download className="w-4 h-4" />
              )}
              Export as JSON
            </Button>
          </div>
        </div>
      </div>

      {/* Import */}
      <div className="bg-white dark:bg-neutral-900 rounded-2xl border border-neutral-200 dark:border-neutral-800 p-5">
        <div className="flex items-start gap-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 shrink-0">
            <Upload className="w-5 h-5 text-emerald-500" />
          </div>
          <div className="flex-1">
            <h4 className="text-sm font-semibold text-neutral-900 dark:text-white">Import Data</h4>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1 mb-3">
              Restore settings from a previously exported JSON backup file.
            </p>
            <Button variant="secondary" size="sm" onClick={handleImport}>
              <Upload className="w-4 h-4" />
              Import from File
            </Button>
          </div>
        </div>
      </div>

      {/* Storage Info */}
      <div className="bg-white dark:bg-neutral-900 rounded-2xl border border-neutral-200 dark:border-neutral-800 p-5">
        <div className="flex items-start gap-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-neutral-100 dark:bg-neutral-800 shrink-0">
            <HardDrive className="w-5 h-5 text-neutral-500" />
          </div>
          <div className="flex-1 space-y-2">
            <h4 className="text-sm font-semibold text-neutral-900 dark:text-white">Storage</h4>
            <div className="text-xs text-neutral-500 dark:text-neutral-400 space-y-1">
              <p>
                <span className="text-neutral-700 dark:text-neutral-300 font-medium">Database: </span>
                <code className="px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 text-xs">
                  ~/.contextuai-solo/data/contextuai.db
                </code>
              </p>
              <p>
                <span className="text-neutral-700 dark:text-neutral-300 font-medium">Settings: </span>
                localStorage (browser)
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Clear All Data */}
      <div className="bg-white dark:bg-neutral-900 rounded-2xl border border-red-200 dark:border-red-500/20 p-5">
        <div className="flex items-start gap-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-red-50 dark:bg-red-500/10 shrink-0">
            <Trash2 className="w-5 h-5 text-red-500" />
          </div>
          <div className="flex-1">
            <h4 className="text-sm font-semibold text-neutral-900 dark:text-white">Clear All Data</h4>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1 mb-3">
              Delete all local settings, brand voice, and provider configurations. This cannot be undone.
            </p>
            <Button variant="danger" size="sm" onClick={() => setShowClearDialog(true)}>
              <Trash2 className="w-4 h-4" />
              Clear All Data
            </Button>
          </div>
        </div>
      </div>

      <Dialog
        open={showClearDialog}
        onClose={() => setShowClearDialog(false)}
        title="Clear All Data?"
        actions={
          <>
            <Button variant="ghost" onClick={() => setShowClearDialog(false)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={handleClearAll}>
              <Trash2 className="w-4 h-4" />
              Delete Everything
            </Button>
          </>
        }
      >
        <p>
          This will permanently delete all your settings, brand voice configuration, API keys, and provider configs.
          This action cannot be undone.
        </p>
        <p className="mt-2 font-medium text-neutral-900 dark:text-white">
          Are you sure you want to continue?
        </p>
      </Dialog>
    </div>
  );
}

// ─── About Tab ──────────────────────────────────────────────────────────────

function AboutTab() {
  const [checking, setChecking] = useState(false);
  const [upToDate, setUpToDate] = useState(false);

  const handleCheckUpdates = async () => {
    setChecking(true);
    await new Promise((r) => setTimeout(r, 1500));
    setUpToDate(true);
    setChecking(false);
    setTimeout(() => setUpToDate(false), 4000);
  };

  return (
    <div className="space-y-6">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-white">About</h3>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
          Application information and resources.
        </p>
      </div>

      {/* App Info */}
      <div className="bg-white dark:bg-neutral-900 rounded-2xl border border-neutral-200 dark:border-neutral-800 p-6 text-center">
        <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-primary-500 to-primary-600 mx-auto mb-4">
          <Settings className="w-7 h-7 text-white" />
        </div>
        <h4 className="text-xl font-bold text-neutral-900 dark:text-white">
          ContextuAI <span className="text-primary-500">Solo</span>
        </h4>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">Version 1.0.0</p>
        <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-0.5">
          Your personal AI business assistant
        </p>
      </div>

      {/* Check for Updates */}
      <div className="bg-white dark:bg-neutral-900 rounded-2xl border border-neutral-200 dark:border-neutral-800 p-5">
        <div className="flex items-center gap-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-primary-50 dark:bg-primary-500/10 shrink-0">
            <RefreshCw className="w-5 h-5 text-primary-500" />
          </div>
          <div className="flex-1">
            <h4 className="text-sm font-semibold text-neutral-900 dark:text-white">Updates</h4>
            {upToDate ? (
              <p className="text-xs text-success mt-0.5">You are running the latest version.</p>
            ) : (
              <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                Check if a newer version is available.
              </p>
            )}
          </div>
          <Button variant="secondary" size="sm" onClick={handleCheckUpdates} disabled={checking}>
            {checking ? <Loader2 className="w-4 h-4 animate-spin" /> : "Check for Updates"}
          </Button>
        </div>
      </div>

      {/* Links */}
      <div className="bg-white dark:bg-neutral-900 rounded-2xl border border-neutral-200 dark:border-neutral-800 divide-y divide-neutral-100 dark:divide-neutral-800">
        {[
          { label: "Changelog", href: "#", desc: "View recent changes and improvements" },
          { label: "Documentation", href: "#", desc: "Read the user guide and API reference" },
          { label: "Support", href: "#", desc: "Get help or report an issue" },
        ].map((link) => (
          <a
            key={link.label}
            href={link.href}
            className="flex items-center justify-between px-5 py-4 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors first:rounded-t-2xl last:rounded-b-2xl"
          >
            <div>
              <p className="text-sm font-medium text-neutral-900 dark:text-white">{link.label}</p>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">{link.desc}</p>
            </div>
            <ExternalLink className="w-4 h-4 text-neutral-400 shrink-0" />
          </a>
        ))}
      </div>

      {/* Built With */}
      <div className="bg-white dark:bg-neutral-900 rounded-2xl border border-neutral-200 dark:border-neutral-800 p-5">
        <h4 className="text-sm font-semibold text-neutral-900 dark:text-white mb-3">Built with</h4>
        <div className="flex flex-wrap gap-2">
          {["Tauri", "React", "FastAPI", "SQLite", "Tailwind CSS", "TypeScript"].map((tech) => (
            <Badge key={tech} variant="default">{tech}</Badge>
          ))}
        </div>
      </div>

      {/* License */}
      <p className="text-xs text-neutral-400 dark:text-neutral-500 text-center">
        ContextuAI Solo is proprietary software. All rights reserved.
      </p>
    </div>
  );
}

// ─── Deep-link tab mapping ───────────────────────────────────────────────────
// Maps ?tab=<slug> query param → internal tab id
const TAB_SLUG_MAP: Record<string, string> = {
  "ai-providers": "providers",
  "brand-voice": "brand",
  "appearance": "appearance",
  "data": "data",
  "about": "about",
};

// ─── Main Settings Page ─────────────────────────────────────────────────────

export default function SettingsPage() {
  const [searchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState(() => {
    const slug = searchParams.get("tab");
    return (slug && TAB_SLUG_MAP[slug]) || "providers";
  });

  // Honor deep-link changes if the URL param changes after mount
  useEffect(() => {
    const slug = searchParams.get("tab");
    const tabId = (slug && TAB_SLUG_MAP[slug]) || null;
    if (tabId && tabId !== activeTab) {
      setActiveTab(tabId);
    }
    // Only react to searchParams changes; activeTab changes are intentional
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  return (
    <div className="min-h-full">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-neutral-50/80 dark:bg-[#242523]/80 backdrop-blur-xl border-b border-neutral-200 dark:border-neutral-800">
        <div className="max-w-4xl mx-auto px-6 pt-6 pb-4">
          <div className="flex items-center gap-3 mb-5">
            <div
              className={cn(
                "flex items-center justify-center w-10 h-10 rounded-xl",
                "bg-primary-50 dark:bg-primary-500/10"
              )}
            >
              <Settings className="w-5 h-5 text-primary-500" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-neutral-900 dark:text-white">Settings</h1>
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                Configure providers, brand voice, and preferences
              </p>
            </div>
          </div>

          <Tabs
            tabs={SETTINGS_TABS}
            activeTab={activeTab}
            onChange={setActiveTab}
          />
        </div>
      </div>

      {/* Tab Content */}
      <div className="max-w-4xl mx-auto px-6 py-8">
        {activeTab === "providers" && <AIProvidersTab />}

        {activeTab === "brand" && <BrandVoiceTab />}
        {activeTab === "appearance" && <AppearanceTab />}
        {activeTab === "data" && <DataExportTab />}
        {activeTab === "about" && <AboutTab />}
      </div>
    </div>
  );
}
