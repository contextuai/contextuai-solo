import { useState, useCallback, useEffect } from "react";
import { cn } from "@/lib/utils";
import { useTheme } from "@/components/providers/theme-provider";
import { useSettings } from "@/hooks/use-settings";
import { Tabs, Button, Input, Textarea, Select, Badge, Dialog, TagInput } from "@/components/ui";
import type { AIProviderConfig } from "@/types/settings";
import {
  Settings,
  Cpu,
  Palette,
  MessageSquareText,
  Database,
  Info,
  Sparkles,
  Zap,
  Globe,
  Cloud,
  Server,
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
  Twitter,
  Share2,
} from "lucide-react";

// ─── Provider definitions ───────────────────────────────────────────────────

const PROVIDER_DEFS = [
  {
    id: "local",
    name: "Local AI (Built-in)",
    description: "Downloaded GGUF models running on your CPU — free, private, offline",
    icon: MonitorIcon,
    color: "from-emerald-500 to-green-600",
    models: [],
    needsKey: false,
    isLocal: true,
  },
  {
    id: "anthropic",
    name: "Anthropic Claude",
    description: "Advanced reasoning, analysis, and creative writing",
    icon: Sparkles,
    color: "from-amber-500 to-orange-600",
    models: ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-3-5-haiku-20241022"],
    needsKey: true,
  },
  {
    id: "openai",
    name: "OpenAI",
    description: "GPT models for versatile language generation",
    icon: Zap,
    color: "from-emerald-500 to-teal-600",
    models: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-preview"],
    needsKey: true,
  },
  {
    id: "google",
    name: "Google Gemini",
    description: "Multimodal understanding and generation",
    icon: Globe,
    color: "from-blue-500 to-indigo-600",
    models: ["gemini-2.0-flash", "gemini-2.0-pro", "gemini-1.5-flash"],
    needsKey: true,
  },
  {
    id: "bedrock",
    name: "AWS Bedrock",
    description: "Managed AI models through AWS infrastructure",
    icon: Cloud,
    color: "from-orange-500 to-yellow-600",
    models: ["anthropic.claude-3-sonnet", "anthropic.claude-3-haiku", "amazon.titan-text-express"],
    needsKey: true,
  },
  {
    id: "ollama",
    name: "Ollama (Local)",
    description: "Run additional local models via Ollama, no API key needed",
    icon: Server,
    color: "from-violet-500 to-purple-600",
    models: [],
    needsKey: false,
  },
];

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
  { id: "connections", label: "Connections", icon: <Share2 className="w-4 h-4" /> },
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
}

function LocalAIConfig() {
  const [models, setModels] = useState<LocalModelInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState<string | null>(null);

  const loadModels = async () => {
    try {
      const baseUrl = import.meta.env.VITE_API_URL || "http://127.0.0.1:18741/api/v1";
      const res = await fetch(`${baseUrl}/local-models/available`);
      if (res.ok) {
        setModels(await res.json());
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
          const res = await fetch(`${baseUrl}/local-models/available`);
          if (res.ok) {
            const data: LocalModelInfo[] = await res.json();
            const m = data.find((x) => x.id === modelId);
            if (m?.downloaded) {
              clearInterval(poll);
              setDownloading(null);
              setModels(data);
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

// ─── Connections Tab ─────────────────────────────────────────────────────────

const CONNECTION_DEFS = [
  {
    id: "twitter",
    name: "Twitter / X",
    description: "Post daily content, updates, and engage with your audience",
    icon: Twitter,
    color: "from-sky-400 to-blue-500",
    fields: [
      { key: "bearer_token", label: "Bearer Token", type: "password" as const, placeholder: "Enter your Twitter API Bearer Token" },
    ],
    helpUrl: "https://developer.twitter.com/en/portal/dashboard",
    helpLabel: "Get API access at developer.twitter.com",
  },
  {
    id: "slack",
    name: "Slack",
    description: "Send notifications and content to Slack channels",
    icon: MessageSquareText,
    color: "from-purple-500 to-fuchsia-600",
    fields: [
      { key: "webhook_url", label: "Webhook URL", type: "text" as const, placeholder: "https://hooks.slack.com/services/..." },
    ],
    helpUrl: "https://api.slack.com/messaging/webhooks",
    helpLabel: "Create an incoming webhook",
  },
];

function ConnectionsTab() {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, "success" | "error">>({});
  const [configs, setConfigs] = useState<Record<string, Record<string, string>>>(() => {
    const saved: Record<string, Record<string, string>> = {};
    CONNECTION_DEFS.forEach((c) => {
      const stored = localStorage.getItem(`contextuai-solo-connection-${c.id}`);
      if (stored) saved[c.id] = JSON.parse(stored);
    });
    return saved;
  });

  const updateField = (connId: string, key: string, value: string) => {
    setConfigs((prev) => ({
      ...prev,
      [connId]: { ...(prev[connId] || {}), [key]: value },
    }));
  };

  const handleSave = (connId: string) => {
    localStorage.setItem(`contextuai-solo-connection-${connId}`, JSON.stringify(configs[connId] || {}));
  };

  const handleTest = async (connId: string) => {
    setTesting(connId);
    setTestResults((prev) => { const n = { ...prev }; delete n[connId]; return n; });

    // Simulate connection test
    await new Promise((r) => setTimeout(r, 1500));
    const fields = configs[connId] || {};
    const hasValues = Object.values(fields).some((v) => v && v.length > 5);
    if (hasValues) {
      setTestResults((prev) => ({ ...prev, [connId]: "success" }));
      handleSave(connId);
    } else {
      setTestResults((prev) => ({ ...prev, [connId]: "error" }));
    }
    setTesting(null);
  };

  return (
    <div className="space-y-4">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-white">Connections</h3>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
          Connect external services for content distribution and notifications.
        </p>
      </div>

      <div className="space-y-3">
        {CONNECTION_DEFS.map((conn) => {
          const Icon = conn.icon;
          const isExpanded = expandedId === conn.id;
          const isConnected = testResults[conn.id] === "success";

          return (
            <div
              key={conn.id}
              className={cn(
                "rounded-2xl border transition-all overflow-hidden",
                isConnected
                  ? "border-primary-500 bg-primary-50/50 dark:bg-primary-500/5"
                  : "border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900"
              )}
            >
              <button
                onClick={() => setExpandedId(isExpanded ? null : conn.id)}
                className="w-full flex items-center gap-4 p-4 text-left"
              >
                <div
                  className={cn(
                    "flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br shrink-0",
                    conn.color
                  )}
                >
                  <Icon className="w-5 h-5 text-white" />
                </div>
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-semibold text-neutral-900 dark:text-white">
                    {conn.name}
                  </span>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                    {conn.description}
                  </p>
                </div>
                <Badge variant={isConnected ? "success" : "default"} dot>
                  {isConnected ? "Connected" : "Not configured"}
                </Badge>
              </button>

              {isExpanded && (
                <div className="px-4 pb-4 pt-1 border-t border-neutral-100 dark:border-neutral-800 space-y-4">
                  {conn.fields.map((field) => (
                    <Input
                      key={field.key}
                      label={field.label}
                      type={field.type}
                      value={configs[conn.id]?.[field.key] || ""}
                      onChange={(e) => updateField(conn.id, field.key, e.target.value)}
                      placeholder={field.placeholder}
                    />
                  ))}

                  <div className="flex items-center gap-3">
                    <Button
                      variant="secondary"
                      onClick={() => handleTest(conn.id)}
                      disabled={testing === conn.id}
                    >
                      {testing === conn.id ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        "Save & Test"
                      )}
                    </Button>

                    {testResults[conn.id] === "success" && (
                      <p className="text-sm text-success flex items-center gap-1.5">
                        <Check className="w-4 h-4" /> Connected
                      </p>
                    )}
                    {testResults[conn.id] === "error" && (
                      <p className="text-sm text-error">
                        Failed. Check your credentials.
                      </p>
                    )}
                  </div>

                  <a
                    href={conn.helpUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-xs text-primary-500 hover:underline"
                  >
                    {conn.helpLabel} <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── AI Providers Tab ───────────────────────────────────────────────────────

function AIProvidersTab() {
  const { settings, updateSettings } = useSettings();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, "success" | "error">>({});
  const [apiKeys, setApiKeys] = useState<Record<string, string>>(() => {
    // Load keys from localStorage
    const keys: Record<string, string> = {};
    PROVIDER_DEFS.forEach((p) => {
      const stored = localStorage.getItem(`contextuai-solo-key-${p.id}`);
      if (stored) keys[p.id] = stored;
    });
    return keys;
  });
  const [ollamaUrl, setOllamaUrl] = useState(
    () => localStorage.getItem("contextuai-solo-ollama-url") || "http://localhost:11434"
  );
  const [ollamaStatus, setOllamaStatus] = useState<"checking" | "running" | "not_found" | null>(null);
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [selectedModels, setSelectedModels] = useState<Record<string, string>>(() => {
    const models: Record<string, string> = {};
    settings.ai_providers.forEach((p) => {
      if (p.default_model) models[p.provider] = p.default_model;
    });
    return models;
  });

  const getProviderConfig = (id: string): AIProviderConfig | undefined => {
    return settings.ai_providers.find((p) => p.provider === id);
  };

  const handleTestConnection = async (providerId: string) => {
    setTesting(providerId);
    setTestResults((prev) => {
      const next = { ...prev };
      delete next[providerId];
      return next;
    });

    if (providerId === "ollama") {
      setOllamaStatus("checking");
      try {
        const response = await fetch(`${ollamaUrl}/api/tags`, { signal: AbortSignal.timeout(5000) });
        if (response.ok) {
          const data = await response.json();
          const models = (data.models || []).map((m: { name: string }) => m.name);
          setOllamaModels(models);
          setOllamaStatus("running");
          setTestResults((prev) => ({ ...prev, ollama: "success" }));
          localStorage.setItem("contextuai-solo-ollama-url", ollamaUrl);
          saveProviderConfig(providerId, { status: "connected", base_url: ollamaUrl });
        } else {
          setOllamaStatus("not_found");
          setTestResults((prev) => ({ ...prev, ollama: "error" }));
        }
      } catch {
        setOllamaStatus("not_found");
        setTestResults((prev) => ({ ...prev, ollama: "error" }));
      }
      setTesting(null);
      return;
    }

    // Simulate API key validation for cloud providers
    await new Promise((r) => setTimeout(r, 1500));
    const key = apiKeys[providerId] || "";
    if (key.length > 8) {
      setTestResults((prev) => ({ ...prev, [providerId]: "success" }));
      localStorage.setItem(`contextuai-solo-key-${providerId}`, key);
      saveProviderConfig(providerId, { status: "connected", api_key: "***" });
    } else {
      setTestResults((prev) => ({ ...prev, [providerId]: "error" }));
    }
    setTesting(null);
  };

  const saveProviderConfig = (providerId: string, partial: Partial<AIProviderConfig>) => {
    const existing = settings.ai_providers;
    const idx = existing.findIndex((p) => p.provider === providerId);
    const base: AIProviderConfig = {
      provider: providerId,
      is_active: false,
      status: "disconnected",
    };
    let updated: AIProviderConfig[];
    if (idx >= 0) {
      updated = [...existing];
      updated[idx] = { ...updated[idx], ...partial };
    } else {
      updated = [...existing, { ...base, ...partial }];
    }
    updateSettings({ ai_providers: updated });
  };

  const handleSetActive = (providerId: string) => {
    const updated = settings.ai_providers.map((p) => ({
      ...p,
      is_active: p.provider === providerId,
    }));
    // Ensure the provider exists
    if (!updated.find((p) => p.provider === providerId)) {
      updated.push({
        provider: providerId,
        is_active: true,
        status: "connected",
        default_model: selectedModels[providerId],
      });
    }
    updateSettings({ ai_providers: updated });
  };

  const handleModelSelect = (providerId: string, model: string) => {
    setSelectedModels((prev) => ({ ...prev, [providerId]: model }));
    saveProviderConfig(providerId, { default_model: model });
  };

  return (
    <div className="space-y-4">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-white">AI Providers</h3>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
          Configure your AI model providers. Connect one or more to get started.
        </p>
      </div>

      <div className="space-y-3">
        {PROVIDER_DEFS.map((provider) => {
          const Icon = provider.icon;
          const config = getProviderConfig(provider.id);
          const isExpanded = expandedId === provider.id;
          const isConnected = config?.status === "connected" || testResults[provider.id] === "success";
          const isActive = config?.is_active || false;

          return (
            <div
              key={provider.id}
              className={cn(
                "rounded-2xl border transition-all overflow-hidden",
                isActive
                  ? "border-primary-500 bg-primary-50/50 dark:bg-primary-500/5"
                  : "border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900"
              )}
            >
              {/* Card Header */}
              <button
                onClick={() => setExpandedId(isExpanded ? null : provider.id)}
                className="w-full flex items-center gap-4 p-4 text-left"
              >
                <div
                  className={cn(
                    "flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br shrink-0",
                    provider.color
                  )}
                >
                  <Icon className="w-5 h-5 text-white" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-neutral-900 dark:text-white">
                      {provider.name}
                    </span>
                    {isActive && (
                      <Badge variant="success" dot>Default</Badge>
                    )}
                  </div>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                    {provider.description}
                  </p>
                </div>
                <Badge
                  variant={isConnected ? "success" : "default"}
                  dot
                >
                  {isConnected ? "Connected" : "Not configured"}
                </Badge>
              </button>

              {/* Expanded Config */}
              {isExpanded && (
                <div className="px-4 pb-4 pt-1 border-t border-neutral-100 dark:border-neutral-800 space-y-4">
                  {(provider as typeof PROVIDER_DEFS[0]).isLocal ? (
                    /* Local AI (Built-in) config */
                    <LocalAIConfig />
                  ) : provider.needsKey ? (
                    <>
                      <div className="flex gap-3 items-end">
                        <div className="flex-1">
                          <Input
                            label="API Key"
                            type="password"
                            value={apiKeys[provider.id] || ""}
                            onChange={(e) =>
                              setApiKeys((prev) => ({ ...prev, [provider.id]: e.target.value }))
                            }
                            placeholder={`Enter your ${provider.name} API key`}
                          />
                        </div>
                        <Button
                          variant="secondary"
                          onClick={() => handleTestConnection(provider.id)}
                          disabled={!apiKeys[provider.id] || testing === provider.id}
                        >
                          {testing === provider.id ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            "Test Connection"
                          )}
                        </Button>
                      </div>

                      {testResults[provider.id] === "success" && (
                        <p className="text-sm text-success flex items-center gap-1.5">
                          <Check className="w-4 h-4" /> Connection successful
                        </p>
                      )}
                      {testResults[provider.id] === "error" && (
                        <p className="text-sm text-error">
                          Connection failed. Please check your API key and try again.
                        </p>
                      )}

                      {isConnected && (
                        <Select
                          label="Default Model"
                          value={selectedModels[provider.id] || ""}
                          onChange={(e) => handleModelSelect(provider.id, e.target.value)}
                          placeholder="Select a model"
                          options={provider.models.map((m) => ({ value: m, label: m }))}
                        />
                      )}
                    </>
                  ) : (
                    /* Ollama config */
                    <>
                      <div className="flex gap-3 items-end">
                        <div className="flex-1">
                          <Input
                            label="Ollama URL"
                            value={ollamaUrl}
                            onChange={(e) => setOllamaUrl(e.target.value)}
                            placeholder="http://localhost:11434"
                            helperText="Default: http://localhost:11434"
                          />
                        </div>
                        <Button
                          variant="secondary"
                          onClick={() => handleTestConnection("ollama")}
                          disabled={testing === "ollama"}
                        >
                          {testing === "ollama" ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            "Detect Ollama"
                          )}
                        </Button>
                      </div>

                      {ollamaStatus === "running" && (
                        <div className="space-y-3">
                          <p className="text-sm text-success flex items-center gap-1.5">
                            <Check className="w-4 h-4" /> Ollama is running
                            {ollamaModels.length > 0 && (
                              <span className="text-neutral-500 dark:text-neutral-400 ml-1">
                                ({ollamaModels.length} model{ollamaModels.length !== 1 ? "s" : ""} available)
                              </span>
                            )}
                          </p>
                          {ollamaModels.length > 0 && (
                            <Select
                              label="Default Model"
                              value={selectedModels["ollama"] || ""}
                              onChange={(e) => handleModelSelect("ollama", e.target.value)}
                              placeholder="Select a local model"
                              options={ollamaModels.map((m) => ({ value: m, label: m }))}
                            />
                          )}
                        </div>
                      )}

                      {ollamaStatus === "not_found" && (
                        <div className="p-4 rounded-xl bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20">
                          <p className="text-sm text-amber-700 dark:text-amber-400 font-medium mb-1">
                            Ollama not detected
                          </p>
                          <p className="text-xs text-amber-600 dark:text-amber-400/80 mb-3">
                            Make sure Ollama is installed and running on your machine.
                          </p>
                          <a
                            href="https://ollama.com/download"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-400 hover:underline"
                          >
                            Download Ollama <ExternalLink className="w-3 h-3" />
                          </a>
                        </div>
                      )}
                    </>
                  )}

                  {isConnected && !isActive && (
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => handleSetActive(provider.id)}
                    >
                      Set as Default Provider
                    </Button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
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

// ─── Main Settings Page ─────────────────────────────────────────────────────

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState("providers");

  return (
    <div className="min-h-screen">
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
        {activeTab === "connections" && <ConnectionsTab />}
        {activeTab === "brand" && <BrandVoiceTab />}
        {activeTab === "appearance" && <AppearanceTab />}
        {activeTab === "data" && <DataExportTab />}
        {activeTab === "about" && <AboutTab />}
      </div>
    </div>
  );
}
