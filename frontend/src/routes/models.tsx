import { useState, useEffect, useCallback, useRef } from "react";
import { cn } from "@/lib/utils";
import {
  Download,
  Trash2,
  Check,
  HardDrive,
  Cpu,
  Search,
  Star,
  Loader2,
  X,
  ExternalLink,
  MessageSquare,
  Brain,
  Code,
  Palette,
  Globe,
  Eye,
  AlertTriangle,
  RefreshCw,
} from "lucide-react";
import {
  getCatalog,
  getInstalledModels,
  getSystemInfo,
  downloadModel,
  cancelDownload,
  deleteModel,
  syncLocalModels,
  type CatalogModel,
  type InstalledModel,
  type SystemInfo,
  type DiskUsage,
  type DownloadProgress,
} from "@/lib/api/local-models-client";
import { getApiBaseUrl } from "@/lib/transport";
import { useBackendStatus } from "@/contexts/backend-status-context";
import { BackendWaiting } from "@/components/backend-waiting";

// ── Constants ────────────────────────────────────────────────────────────

const CATEGORY_ICONS: Record<string, React.ElementType> = {
  general: MessageSquare,
  reasoning: Brain,
  coding: Code,
  creative: Palette,
  multilingual: Globe,
  vision: Eye,
};

const QUALITY_COLORS: Record<string, string> = {
  basic: "bg-neutral-100 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-300",
  good: "bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400",
  great: "bg-purple-100 text-purple-700 dark:bg-purple-500/20 dark:text-purple-400",
  best: "bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400",
};

const SPEED_LABELS: Record<string, string> = {
  fast: "Fast",
  medium: "Medium",
  slow: "Slow",
};

type Tab = "discover" | "installed";

// ── RAM indicator ────────────────────────────────────────────────────────

function RamIndicator({ required, systemRam }: { required: number; systemRam: number }) {
  const fits = required <= systemRam;
  const tight = required > systemRam * 0.7;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-[11px] font-medium px-1.5 py-0.5 rounded",
        fits && !tight && "bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400",
        fits && tight && "bg-yellow-100 text-yellow-700 dark:bg-yellow-500/20 dark:text-yellow-400",
        !fits && "bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400"
      )}
    >
      {required} GB RAM
      {!fits && <AlertTriangle className="w-3 h-3" />}
    </span>
  );
}

// ── Model Card ───────────────────────────────────────────────────────────

function ModelCard({
  model,
  systemRam,
  downloading,
  progress,
  onDownload,
  onCancel,
}: {
  model: CatalogModel;
  systemRam: number;
  downloading: boolean;
  progress?: DownloadProgress;
  onDownload: (id: string) => void;
  onCancel: (id: string) => void;
}) {
  const percent = progress?.percent ?? 0;

  return (
    <div
      className={cn(
        "relative flex flex-col p-4 rounded-xl border bg-white dark:bg-neutral-900 transition-all",
        model.is_recommended
          ? "border-primary-300 dark:border-primary-700 ring-1 ring-primary-200 dark:ring-primary-800"
          : "border-neutral-200 dark:border-neutral-800"
      )}
    >
      {model.is_recommended && (
        <span className="absolute -top-2.5 left-3 px-2 py-0.5 text-[10px] font-bold bg-primary-500 text-white rounded-full flex items-center gap-1">
          <Star className="w-3 h-3" /> Recommended
        </span>
      )}

      {/* Header */}
      <div className="flex items-start justify-between mb-2">
        <div>
          <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">
            {model.name}
          </h3>
          <p className="text-[11px] text-neutral-500">
            {model.provider} · {model.parameter_size} · {model.size_gb} GB download
          </p>
        </div>
        <span className={cn("text-[10px] font-medium px-1.5 py-0.5 rounded", QUALITY_COLORS[model.quality_tier])}>
          {model.quality_tier}
        </span>
      </div>

      {/* Description */}
      <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-2 line-clamp-2">
        {model.description}
      </p>

      {/* Source link */}
      {model.hf_repo && (
        <a
          href={`https://huggingface.co/${model.hf_repo}`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[11px] text-primary-500 hover:text-primary-400 underline underline-offset-2 mb-3"
        >
          <ExternalLink className="w-3 h-3" />
          View on HuggingFace
        </a>
      )}

      {/* Tags */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {model.categories.map((cat) => {
          const Icon = CATEGORY_ICONS[cat] || MessageSquare;
          return (
            <span
              key={cat}
              className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400"
            >
              <Icon className="w-3 h-3" />
              {cat}
            </span>
          );
        })}
        <span className="text-[10px] text-neutral-400 px-1.5 py-0.5">
          {SPEED_LABELS[model.speed_tier]} · {model.context_window >= 100000 ? "128K ctx" : `${Math.round(model.context_window / 1024)}K ctx`}
        </span>
      </div>

      {/* RAM + Action */}
      <div className="flex items-center justify-between mt-auto pt-2 border-t border-neutral-100 dark:border-neutral-800">
        <RamIndicator required={model.ram_required_gb} systemRam={systemRam} />

        {model.installed ? (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-green-600 dark:text-green-400">
            <Check className="w-3.5 h-3.5" /> Installed
          </span>
        ) : downloading ? (
          <div className="flex items-center gap-2">
            {progress?.status === "error" ? (
              <div className="flex flex-col gap-1 max-w-xs">
                <span className="text-[11px] text-red-500 font-semibold">Download failed</span>
                <span className="text-[10px] text-red-400 leading-tight">
                  {progress.detail || "Unknown error"}
                </span>
              </div>
            ) : progress?.status === "starting" || progress?.status === "connecting" ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin text-primary-500" />
                <span className="text-[10px] text-neutral-500">
                  {progress?.status === "connecting"
                    ? "Starting download..."
                    : "Preparing..."}
                </span>
                <button
                  onClick={() => onCancel(model.id)}
                  className="p-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800"
                >
                  <X className="w-3 h-3 text-neutral-400" />
                </button>
              </>
            ) : (
              <>
                <div className="w-24 h-1.5 rounded-full bg-neutral-200 dark:bg-neutral-700 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-primary-500 transition-all duration-300"
                    style={{ width: `${percent}%` }}
                  />
                </div>
                <span className="text-[10px] text-neutral-500 tabular-nums font-medium">
                  {Math.round(percent)}%
                </span>
                {progress?.total_mb ? (
                  <span className="text-[10px] text-neutral-400 tabular-nums">
                    {progress.completed_mb ?? 0} / {progress.total_mb} MB
                  </span>
                ) : null}
                <button
                  onClick={() => onCancel(model.id)}
                  className="p-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-800"
                >
                  <X className="w-3 h-3 text-neutral-400" />
                </button>
              </>
            )}
          </div>
        ) : (
          <button
            onClick={() => onDownload(model.id)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary-500 hover:bg-primary-600 text-white transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            Download
          </button>
        )}
      </div>
    </div>
  );
}

// ── Installed Model Row ──────────────────────────────────────────────────

function InstalledRow({
  model,
  deleting,
  onDelete,
}: {
  model: InstalledModel;
  deleting: boolean;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="flex items-center justify-between p-4 bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-800">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-green-100 dark:bg-green-500/20">
          <Check className="w-4 h-4 text-green-600 dark:text-green-400" />
        </div>
        <div>
          <h4 className="text-sm font-semibold text-neutral-900 dark:text-white">
            {model.name}
          </h4>
          <p className="text-[11px] text-neutral-500">
            {model.provider} · {model.parameter_size} · {model.size_gb} GB on disk
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {model.hf_repo && (
          <a
            href={`https://huggingface.co/${model.hf_repo}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            Source
          </a>
        )}
        <button
          onClick={() => onDelete(model.id)}
          disabled={deleting}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors disabled:opacity-50"
        >
          {deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
          Delete
        </button>
      </div>
    </div>
  );
}

// ── Custom Model Input ───────────────────────────────────────────────────

function CustomModelInput({ onDownload }: { onDownload: () => void }) {
  const [repo, setRepo] = useState("");
  const [filename, setFilename] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const handleCustomDownload = async () => {
    if (!repo.trim() || !filename.trim()) return;
    setDownloading(true);
    setStatus("Downloading...");

    try {
      const baseUrl = await getApiBaseUrl();
      const response = await fetch(`${baseUrl}/local-models/download/custom`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hf_repo: repo.trim(), hf_filename: filename.trim() }),
      });

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data: ")) {
            try {
              const parsed = JSON.parse(trimmed.substring(6));
              if (parsed.status === "done") {
                setStatus("Download complete!");
                setTimeout(() => {
                  setStatus(null);
                  setRepo("");
                  setFilename("");
                  onDownload();
                }, 1000);
              } else if (parsed.status === "error") {
                setStatus(`Error: ${parsed.detail}`);
              } else if (parsed.percent) {
                setStatus(`Downloading... ${Math.round(parsed.percent)}%`);
              }
            } catch { /* skip */ }
          }
        }
      }
    } catch (err) {
      setStatus(`Error: ${err}`);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="flex items-end gap-2">
      <div className="flex-1">
        <label className="block text-[11px] text-neutral-500 mb-1">HuggingFace Repo</label>
        <input
          type="text"
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          placeholder="e.g. Qwen/Qwen2.5-7B-Instruct-GGUF"
          disabled={downloading}
          className="w-full px-3 py-2 text-xs rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-white placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-500/40"
        />
      </div>
      <div className="flex-1">
        <label className="block text-[11px] text-neutral-500 mb-1">GGUF Filename</label>
        <input
          type="text"
          value={filename}
          onChange={(e) => setFilename(e.target.value)}
          placeholder="e.g. qwen2.5-7b-instruct-q4_k_m.gguf"
          disabled={downloading}
          className="w-full px-3 py-2 text-xs rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-white placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-500/40"
        />
      </div>
      <button
        onClick={handleCustomDownload}
        disabled={downloading || !repo.trim() || !filename.trim()}
        className="px-4 py-2 text-xs font-medium rounded-lg bg-neutral-900 dark:bg-white text-white dark:text-neutral-900 hover:bg-neutral-800 dark:hover:bg-neutral-100 transition-colors disabled:opacity-50"
      >
        {downloading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Pull"}
      </button>
      {status && (
        <span className="text-[11px] text-neutral-500 ml-1 whitespace-nowrap">{status}</span>
      )}
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────

export default function ModelsPage() {
  const { status: backendStatus } = useBackendStatus();
  const [tab, setTab] = useState<Tab>("discover");
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [catalog, setCatalog] = useState<CatalogModel[]>([]);
  const [installed, setInstalled] = useState<InstalledModel[]>([]);
  const [diskUsage, setDiskUsage] = useState<DiskUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [downloads, setDownloads] = useState<Record<string, DownloadProgress>>({});
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const abortControllers = useRef<Record<string, AbortController>>({});

  // ── Load data ──────────────────────────────────────────────────────────

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [sysInfo, catalogRes, installedRes] = await Promise.all([
        getSystemInfo(),
        getCatalog(),
        getInstalledModels(),
      ]);
      setSystemInfo(sysInfo);
      setCatalog(catalogRes.models);
      setInstalled(installedRes.models);
      setDiskUsage(installedRes.disk_usage);
    } catch (err) {
      console.error("Failed to load model data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // ── Download handler ───────────────────────────────────────────────────

  const handleDownload = useCallback(async (modelId: string) => {
    const controller = new AbortController();
    abortControllers.current[modelId] = controller;

    setDownloads((prev) => ({
      ...prev,
      [modelId]: { status: "starting", percent: 0, detail: "Preparing..." },
    }));

    try {
      await downloadModel(
        modelId,
        (progress) => {
          setDownloads((prev) => ({ ...prev, [modelId]: progress }));

          if (progress.status === "done") {
            // If file already existed, skip animation and refresh immediately
            const delay = progress.already_exists ? 0 : 500;
            setTimeout(() => {
              setDownloads((prev) => {
                const next = { ...prev };
                delete next[modelId];
                return next;
              });
              loadData();
            }, delay);
          } else if (progress.status === "error" || progress.status === "cancelled") {
            // Show error briefly, then clean up
            setTimeout(() => {
              setDownloads((prev) => {
                const next = { ...prev };
                delete next[modelId];
                return next;
              });
            }, 3000);
          }
        },
        controller.signal
      );
    } catch {
      // Network error or fetch failure — clean up stuck download state
      setDownloads((prev) => {
        const next = { ...prev };
        delete next[modelId];
        return next;
      });
    }
  }, [loadData]);

  const handleCancel = useCallback(async (modelId: string) => {
    abortControllers.current[modelId]?.abort();
    delete abortControllers.current[modelId];
    await cancelDownload(modelId).catch(() => {});
    setDownloads((prev) => {
      const next = { ...prev };
      delete next[modelId];
      return next;
    });
  }, []);

  // ── Delete handler ─────────────────────────────────────────────────────

  const handleDelete = useCallback(async (modelId: string) => {
    if (!confirm(`Delete this model? This will free up disk space.`)) return;
    setDeletingId(modelId);
    try {
      await deleteModel(modelId);
      await loadData();
    } catch (err) {
      console.error("Delete failed:", err);
    } finally {
      setDeletingId(null);
    }
  }, [loadData]);

  // ── Filter catalog ─────────────────────────────────────────────────────

  const filteredCatalog = catalog.filter((m) => {
    if (activeCategory && !m.categories.includes(activeCategory)) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        m.name.toLowerCase().includes(q) ||
        m.provider.toLowerCase().includes(q) ||
        m.description.toLowerCase().includes(q) ||
        m.categories.some((c) => c.includes(q))
      );
    }
    return true;
  });

  const recommendedModels = filteredCatalog.filter((m) => m.is_recommended);
  const otherModels = filteredCatalog.filter((m) => !m.is_recommended);

  const categories = [
    { id: null, label: "All" },
    { id: "general", label: "General" },
    { id: "reasoning", label: "Reasoning" },
    { id: "coding", label: "Coding" },
    { id: "creative", label: "Creative" },
    { id: "multilingual", label: "Multilingual" },
    { id: "vision", label: "Vision" },
  ];

  const activeDownloadCount = Object.keys(downloads).length;

  // ── Render ─────────────────────────────────────────────────────────────

  if (loading && backendStatus !== "ready") {
    return (
      <div className="flex items-center justify-center h-full">
        <BackendWaiting />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-6 h-6 animate-spin text-primary-500" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-neutral-50 dark:bg-[#1a1b1a]">
      {/* Header */}
      <div className="px-6 pt-6 pb-4 border-b border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-bold text-neutral-900 dark:text-white">
              Model Hub
            </h1>
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              Download and manage local AI models
            </p>
          </div>
          <button
            onClick={loadData}
            className="p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4 text-neutral-500" />
          </button>
        </div>

        {/* System info banner */}
        {systemInfo && (
          <div className="flex items-center gap-4 p-3 rounded-xl bg-neutral-50 dark:bg-neutral-800 mb-4">
            <div className="flex items-center gap-2">
              <Cpu className="w-4 h-4 text-primary-500" />
              <span className="text-sm font-medium text-neutral-900 dark:text-white">
                {systemInfo.total_ram_gb} GB RAM
              </span>
              <span className="text-xs text-neutral-500">
                — models up to {systemInfo.max_recommended_params} recommended
              </span>
            </div>
            {systemInfo.gpu && (
              <div className="flex items-center gap-1.5 text-xs text-neutral-500">
                <HardDrive className="w-3.5 h-3.5" />
                {systemInfo.gpu}
                {systemInfo.gpu_vram_gb && ` (${systemInfo.gpu_vram_gb} GB)`}
              </div>
            )}
            {diskUsage && (
              <div className="ml-auto flex items-center gap-1.5 text-xs text-neutral-500">
                <HardDrive className="w-3.5 h-3.5" />
                {diskUsage.models_gb} GB used · {diskUsage.disk_free_gb} GB free
              </div>
            )}
          </div>
        )}

        {/* Tabs */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => setTab("discover")}
            className={cn(
              "px-4 py-2 text-sm font-medium rounded-lg transition-colors",
              tab === "discover"
                ? "bg-primary-50 dark:bg-primary-500/10 text-primary-600 dark:text-primary-400"
                : "text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800"
            )}
          >
            Discover
          </button>
          <button
            onClick={() => setTab("installed")}
            className={cn(
              "px-4 py-2 text-sm font-medium rounded-lg transition-colors flex items-center gap-2",
              tab === "installed"
                ? "bg-primary-50 dark:bg-primary-500/10 text-primary-600 dark:text-primary-400"
                : "text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800"
            )}
          >
            Installed
            {installed.length > 0 && (
              <span className="px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400">
                {installed.length}
              </span>
            )}
          </button>
          {activeDownloadCount > 0 && (
            <span className="ml-2 px-2 py-1 text-[10px] font-bold rounded-full bg-primary-100 text-primary-700 dark:bg-primary-500/20 dark:text-primary-400 animate-pulse">
              {activeDownloadCount} downloading
            </span>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {/* ── Discover Tab ──────────────────────────────────────────────── */}
        {tab === "discover" && (
          <>
            {/* Search + Filters */}
            <div className="flex items-center gap-3 mb-6">
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search models..."
                  className="w-full pl-9 pr-4 py-2 text-sm rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-500/40"
                />
              </div>
              <div className="flex items-center gap-1.5 overflow-x-auto">
                {categories.map((cat) => (
                  <button
                    key={cat.id ?? "all"}
                    onClick={() => setActiveCategory(cat.id)}
                    className={cn(
                      "px-3 py-1.5 text-xs font-medium rounded-full whitespace-nowrap transition-colors",
                      activeCategory === cat.id
                        ? "bg-primary-500 text-white"
                        : "bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 hover:bg-neutral-200 dark:hover:bg-neutral-700"
                    )}
                  >
                    {cat.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Recommended section */}
            {recommendedModels.length > 0 && !search && !activeCategory && (
              <div className="mb-8">
                <h2 className="flex items-center gap-2 text-sm font-semibold text-neutral-900 dark:text-white mb-3">
                  <Star className="w-4 h-4 text-primary-500" />
                  Recommended for You
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {recommendedModels.map((m) => (
                    <ModelCard
                      key={m.id}
                      model={m}
                      systemRam={systemInfo?.total_ram_gb ?? 8}
                      downloading={!!downloads[m.id]}
                      progress={downloads[m.id]}
                      onDownload={handleDownload}
                      onCancel={handleCancel}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* All models */}
            <div>
              <h2 className="text-sm font-semibold text-neutral-900 dark:text-white mb-3">
                {search || activeCategory ? `Results (${filteredCatalog.length})` : "All Models"}
              </h2>
              {(search || activeCategory ? filteredCatalog : otherModels).length === 0 ? (
                <div className="text-center py-12">
                  <p className="text-sm text-neutral-500">No models found matching your search.</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {(search || activeCategory ? filteredCatalog : otherModels).map((m) => (
                    <ModelCard
                      key={m.id}
                      model={m}
                      systemRam={systemInfo?.total_ram_gb ?? 8}
                      downloading={!!downloads[m.id]}
                      progress={downloads[m.id]}
                      onDownload={handleDownload}
                      onCancel={handleCancel}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Custom model input */}
            <div className="mt-8 p-4 rounded-xl border border-dashed border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900">
              <div className="flex items-center gap-2 mb-2">
                <ExternalLink className="w-4 h-4 text-neutral-500" />
                <span className="text-sm font-medium text-neutral-900 dark:text-white">
                  Custom Model
                </span>
              </div>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-3">
                Don't see your model?{" "}
                <a
                  href="https://huggingface.co/models?sort=trending&search=gguf"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary-500 hover:text-primary-400 underline underline-offset-2 inline-flex items-center gap-1"
                >
                  Browse GGUF models on HuggingFace
                  <ExternalLink className="w-3 h-3" />
                </a>{" "}
                and enter the repo and filename below.
              </p>
              <CustomModelInput onDownload={loadData} />
            </div>
          </>
        )}

        {/* ── Installed Tab ─────────────────────────────────────────────── */}
        {tab === "installed" && (
          <>
            {installed.length === 0 ? (
              <div className="text-center py-16">
                <HardDrive className="w-10 h-10 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
                <h3 className="text-sm font-semibold text-neutral-900 dark:text-white mb-1">
                  No models installed
                </h3>
                <p className="text-xs text-neutral-500 dark:text-neutral-400 mb-4">
                  Browse the Discover tab to download your first model, or copy a .gguf file into the models folder and sync.
                </p>
                <div className="flex items-center justify-center gap-3">
                  <button
                    onClick={() => setTab("discover")}
                    className="px-4 py-2 text-sm font-medium rounded-lg bg-primary-500 text-white hover:bg-primary-600 transition-colors"
                  >
                    Browse Models
                  </button>
                  <button
                    onClick={async () => {
                      await syncLocalModels().catch(() => {});
                      loadData();
                    }}
                    className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    Sync Models
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                {diskUsage && (
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2 text-xs text-neutral-500">
                      <HardDrive className="w-3.5 h-3.5" />
                      {diskUsage.model_count} model{diskUsage.model_count !== 1 ? "s" : ""} ·{" "}
                      {diskUsage.models_gb} GB used · {diskUsage.disk_free_gb} GB free on disk
                    </div>
                    <button
                      onClick={async () => {
                        await syncLocalModels().catch(() => {});
                        loadData();
                      }}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
                      title="Sync manually-added models to the database"
                    >
                      <RefreshCw className="w-3 h-3" />
                      Sync to DB
                    </button>
                  </div>
                )}
                {installed.map((m) => (
                  <InstalledRow
                    key={m.id}
                    model={m}
                    deleting={deletingId === m.id}
                    onDelete={handleDelete}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
