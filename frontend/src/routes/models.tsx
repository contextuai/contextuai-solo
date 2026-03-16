import { useState, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { useAiMode } from "@/contexts/ai-mode-context";
import {
  getAvailableModels,
  getModelStatus,
  startDownload,
  loadModel,
  unloadModel,
  deleteModel,
  syncLocalModels,
  streamDownloadProgress,
  type LocalModel,
  type ModelStatus,
  type DownloadProgress,
} from "@/lib/api/local-models-client";
import { getModels, type ModelConfig } from "@/lib/api/models-client";
import {
  Monitor,
  Cloud,
  Download,
  Trash2,
  Loader2,
  Zap,
  HardDrive,
  Cpu,
  Power,
  PowerOff,
  RefreshCw,
  AlertCircle,
} from "lucide-react";

const TIER_LABELS: Record<string, { label: string; color: string }> = {
  basic: { label: "Starter", color: "bg-neutral-100 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-400" },
  recommended: { label: "Recommended", color: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400" },
  best: { label: "Best", color: "bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400" },
};

function formatSize(bytes: number): string {
  if (bytes >= 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(1)} GB`;
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(0)} MB`;
  return `${bytes} B`;
}

export default function ModelsPage() {
  const { aiMode, setAiMode } = useAiMode();
  const [localModels, setLocalModels] = useState<LocalModel[]>([]);
  const [cloudModels, setCloudModels] = useState<ModelConfig[]>([]);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloadProgress, setDownloadProgress] = useState<DownloadProgress | null>(null);
  const [loadingModelId, setLoadingModelId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const downloadCancelRef = useRef<{ cancel: () => void } | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [locals, status, cloud] = await Promise.all([
        getAvailableModels(),
        getModelStatus().catch(() => null),
        getModels("cloud").catch(() => []),
      ]);
      setLocalModels(locals);
      setModelStatus(status);
      setCloudModels(cloud);
    } catch (err) {
      console.warn("Failed to load models:", err);
    } finally {
      setLoading(false);
    }
  }

  async function handleDownload(modelId: string) {
    setDownloadingId(modelId);
    setDownloadProgress(null);
    setError(null);

    try {
      await startDownload(modelId);
      const stream = streamDownloadProgress(
        (progress) => {
          setDownloadProgress(progress);
          if (progress.status === "complete") {
            setDownloadingId(null);
            setDownloadProgress(null);
            downloadCancelRef.current = null;
            syncLocalModels().catch(() => {});
            loadData();
          } else if (progress.status === "error") {
            setDownloadingId(null);
            setError(progress.error || "Download failed");
            downloadCancelRef.current = null;
          }
        },
        (err) => {
          setDownloadingId(null);
          setError(err);
          downloadCancelRef.current = null;
        }
      );
      downloadCancelRef.current = stream;
    } catch (err) {
      setDownloadingId(null);
      setError(String(err));
    }
  }

  async function handleLoad(modelId: string) {
    setLoadingModelId(modelId);
    try {
      await loadModel(modelId);
      const status = await getModelStatus().catch(() => null);
      setModelStatus(status);
    } catch (err) {
      setError(`Failed to load model: ${err}`);
    } finally {
      setLoadingModelId(null);
    }
  }

  async function handleUnload() {
    try {
      await unloadModel();
      setModelStatus(null);
    } catch (err) {
      setError(`Failed to unload: ${err}`);
    }
  }

  async function handleDelete(modelId: string) {
    setDeletingId(modelId);
    try {
      await deleteModel(modelId);
      await syncLocalModels().catch(() => {});
      loadData();
    } catch (err) {
      setError(`Failed to delete: ${err}`);
    } finally {
      setDeletingId(null);
    }
  }

  const downloadedModels = localModels.filter((m) => m.downloaded);
  const availableModels = localModels.filter((m) => !m.downloaded);
  const loadedModelId = modelStatus?.model_id || null;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-3xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Models</h1>
            <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
              Download and manage your AI models
            </p>
          </div>
          <button
            onClick={loadData}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 transition-colors"
          >
            <RefreshCw className={cn("w-3 h-3", loading && "animate-spin")} />
            Refresh
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 text-sm mb-6">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            {error}
            <button onClick={() => setError(null)} className="ml-auto text-xs underline">Dismiss</button>
          </div>
        )}

        {/* ── AI Mode Banner ───────────────────────────────────── */}
        <div className={cn(
          "rounded-2xl border-2 p-5 mb-8 transition-all",
          aiMode === "local"
            ? "border-emerald-200 dark:border-emerald-800 bg-gradient-to-r from-emerald-50 to-white dark:from-emerald-500/5 dark:to-neutral-900"
            : "border-sky-200 dark:border-sky-800 bg-gradient-to-r from-sky-50 to-white dark:from-sky-500/5 dark:to-neutral-900"
        )}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {aiMode === "local" ? (
                <div className="p-2 rounded-xl bg-emerald-100 dark:bg-emerald-500/20">
                  <Monitor className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                </div>
              ) : (
                <div className="p-2 rounded-xl bg-sky-100 dark:bg-sky-500/20">
                  <Cloud className="w-5 h-5 text-sky-600 dark:text-sky-400" />
                </div>
              )}
              <div>
                <h2 className="text-sm font-bold text-neutral-900 dark:text-white">
                  {aiMode === "local" ? "Local AI Mode" : "Cloud Mode"}
                </h2>
                <p className="text-xs text-neutral-500 dark:text-neutral-400">
                  {aiMode === "local"
                    ? "Running models on your machine. Free, private, offline."
                    : "Using cloud APIs. Requires API keys and internet."}
                </p>
              </div>
            </div>
            <button
              onClick={() => setAiMode(aiMode === "local" ? "cloud" : "local")}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors",
                "text-neutral-600 dark:text-neutral-400 border-neutral-200 dark:border-neutral-700",
                "hover:bg-neutral-100 dark:hover:bg-neutral-800"
              )}
            >
              Switch to {aiMode === "local" ? "Cloud" : "Local"}
            </button>
          </div>
        </div>

        {/* ── LOCAL MODELS ─────────────────────────────────────── */}
        <div className="mb-10">
          <div className="flex items-center gap-2 mb-4">
            <Monitor className="w-4 h-4 text-emerald-500" />
            <h2 className="text-lg font-bold text-neutral-900 dark:text-white">Local Models</h2>
            <span className="text-xs text-neutral-400">({downloadedModels.length} downloaded)</span>
          </div>

          {/* Downloaded models */}
          {downloadedModels.length > 0 && (
            <div className="space-y-2 mb-6">
              {downloadedModels.map((model) => {
                const isLoaded = loadedModelId === model.id;
                const isLoadingThis = loadingModelId === model.id;
                const isDeletingThis = deletingId === model.id;
                const tier = TIER_LABELS[model.tier] || TIER_LABELS.basic;

                return (
                  <div
                    key={model.id}
                    className={cn(
                      "flex items-center justify-between p-4 rounded-xl border transition-all",
                      isLoaded
                        ? "border-emerald-300 dark:border-emerald-700 bg-emerald-50/50 dark:bg-emerald-500/5"
                        : "border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900"
                    )}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={cn(
                        "p-2 rounded-lg",
                        isLoaded ? "bg-emerald-100 dark:bg-emerald-500/20" : "bg-neutral-100 dark:bg-neutral-800"
                      )}>
                        <Cpu className={cn("w-4 h-4", isLoaded ? "text-emerald-500" : "text-neutral-400")} />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm text-neutral-900 dark:text-white">{model.name}</span>
                          <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", tier.color)}>
                            {tier.label}
                          </span>
                          {isLoaded && (
                            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500 text-white">
                              ACTIVE
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 mt-0.5">
                          <span className="text-[11px] text-neutral-400 flex items-center gap-1">
                            <HardDrive className="w-3 h-3" /> {formatSize(model.size_bytes)}
                          </span>
                          <span className="text-[11px] text-neutral-400 flex items-center gap-1">
                            <Zap className="w-3 h-3" /> {model.ram_gb} GB RAM
                          </span>
                          {model.supports_tools && (
                            <span className="text-[11px] text-blue-500 font-medium">Tool calling</span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      {isLoaded ? (
                        <button
                          onClick={handleUnload}
                          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
                        >
                          <PowerOff className="w-3 h-3" /> Unload
                        </button>
                      ) : (
                        <button
                          onClick={() => handleLoad(model.id)}
                          disabled={isLoadingThis}
                          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 transition-colors"
                        >
                          {isLoadingThis ? <Loader2 className="w-3 h-3 animate-spin" /> : <Power className="w-3 h-3" />}
                          Load
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete(model.id)}
                        disabled={isDeletingThis || isLoaded}
                        className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 disabled:opacity-30 transition-colors"
                      >
                        {isDeletingThis ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Available to download */}
          <div className="space-y-2">
            {availableModels.length > 0 && (
              <h3 className="text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-3">
                Available to Download
              </h3>
            )}
            {loading && localModels.length === 0 && (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-5 h-5 animate-spin text-neutral-400" />
              </div>
            )}
            {availableModels.map((model) => {
              const isDownloading = downloadingId === model.id;
              const tier = TIER_LABELS[model.tier] || TIER_LABELS.basic;

              return (
                <div
                  key={model.id}
                  className="flex items-center justify-between p-4 rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 transition-all"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="p-2 rounded-lg bg-neutral-100 dark:bg-neutral-800">
                      <Cpu className="w-4 h-4 text-neutral-400" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm text-neutral-900 dark:text-white">{model.name}</span>
                        <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", tier.color)}>
                          {tier.label}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 mt-0.5">
                        <span className="text-[11px] text-neutral-400 flex items-center gap-1">
                          <Download className="w-3 h-3" /> {formatSize(model.size_bytes)}
                        </span>
                        <span className="text-[11px] text-neutral-400 flex items-center gap-1">
                          <Zap className="w-3 h-3" /> {model.ram_gb} GB RAM needed
                        </span>
                        {model.supports_tools && (
                          <span className="text-[11px] text-blue-500 font-medium">Tool calling</span>
                        )}
                      </div>
                    </div>
                  </div>

                  {isDownloading ? (
                    <div className="w-40">
                      {downloadProgress ? (
                        <div>
                          <div className="flex justify-between text-[10px] text-emerald-600 dark:text-emerald-400 mb-1">
                            <span>Downloading</span>
                            <span className="font-bold">{downloadProgress.percent}%</span>
                          </div>
                          <div className="w-full h-1.5 bg-emerald-200 dark:bg-emerald-900 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-emerald-500 rounded-full transition-all"
                              style={{ width: `${downloadProgress.percent}%` }}
                            />
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5">
                          <Loader2 className="w-3 h-3 animate-spin text-emerald-500" />
                          <span className="text-xs text-neutral-400">Starting...</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <button
                      onClick={() => handleDownload(model.id)}
                      disabled={downloadingId !== null}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-800 disabled:opacity-30 transition-colors"
                    >
                      <Download className="w-3 h-3" />
                      Download
                    </button>
                  )}
                </div>
              );
            })}
          </div>

          {/* RAM recommendation */}
          <div className="mt-6 p-4 rounded-xl bg-neutral-50 dark:bg-neutral-800/50 border border-neutral-200 dark:border-neutral-700">
            <h4 className="text-xs font-semibold text-neutral-600 dark:text-neutral-300 uppercase tracking-wider mb-2">
              RAM Guide
            </h4>
            <div className="grid grid-cols-3 gap-3 text-[11px]">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-neutral-400" />
                <span className="text-neutral-500 dark:text-neutral-400">8 GB RAM: up to 3B</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-emerald-500" />
                <span className="text-neutral-500 dark:text-neutral-400">16 GB RAM: up to 7B</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-amber-500" />
                <span className="text-neutral-500 dark:text-neutral-400">32+ GB RAM: up to 32B</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── CLOUD MODELS ─────────────────────────────────────── */}
        <div>
          <div className="flex items-center gap-2 mb-4">
            <Cloud className="w-4 h-4 text-sky-500" />
            <h2 className="text-lg font-bold text-neutral-900 dark:text-white">Cloud Models</h2>
            <span className="text-xs text-neutral-400">({cloudModels.length} configured)</span>
          </div>

          {cloudModels.length === 0 ? (
            <div className="text-center py-8 rounded-xl border border-dashed border-neutral-300 dark:border-neutral-700">
              <Cloud className="w-8 h-8 text-neutral-300 dark:text-neutral-600 mx-auto mb-2" />
              <p className="text-sm text-neutral-500 dark:text-neutral-400">
                No cloud providers configured yet
              </p>
              <p className="text-xs text-neutral-400 mt-1">
                Add API keys in Settings to use cloud models
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {cloudModels.map((model) => (
                <div
                  key={model.id}
                  className="flex items-center justify-between p-4 rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-sky-100 dark:bg-sky-500/20">
                      <Cloud className="w-4 h-4 text-sky-500" />
                    </div>
                    <div>
                      <span className="font-semibold text-sm text-neutral-900 dark:text-white">{model.name}</span>
                      <span className="text-[11px] text-neutral-400 ml-2">{model.provider}</span>
                    </div>
                  </div>
                  <span className={cn(
                    "text-[10px] font-medium px-2 py-0.5 rounded-full",
                    model.enabled
                      ? "bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400"
                      : "bg-neutral-100 text-neutral-500 dark:bg-neutral-700 dark:text-neutral-400"
                  )}>
                    {model.enabled ? "Enabled" : "Disabled"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
