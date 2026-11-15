import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
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
  Zap,
  Gauge,
  ArrowRight,
} from "lucide-react";
import {
  getCatalog,
  getInstalledModels,
  getSystemInfo,
  getHardwareProfile,
  getLoadedModel,
  preloadLocalModel,
  benchmarkLocalModel,
  refreshModelCatalog,
  downloadModel,
  cancelDownload,
  deleteModel,
  syncLocalModels,
  listHfRepoGgufFiles,
  searchHfGgufModels,
  importLocalGguf,
  type CatalogModel,
  type InstalledModel,
  type SystemInfo,
  type DiskUsage,
  type DownloadProgress,
  type HardwareProfile,
  type HfRepoFile,
  type HfSearchModel,
} from "@/lib/api/local-models-client";
import { getApiBaseUrl, getSidecarToken } from "@/lib/transport";
import { useBackendStatus } from "@/contexts/backend-status-context";
import { BackendWaiting } from "@/components/backend-waiting";
import { Dialog } from "@/components/ui/dialog";
import { CloudProvidersTab } from "@/components/cloud-providers/cloud-providers-tab";

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

const QUANT_TOOLTIPS: Record<string, string> = {
  Q4_K_M: "Q4_K_M — Sweet-spot 4-bit quantization: ~99% of FP16 quality at 1/3 the RAM/VRAM.",
  Q4_K_S: "Q4_K_S — Compact 4-bit quantization for tighter RAM/VRAM budgets.",
  Q5_K_M: "Q5_K_M — High-precision 5-bit quantization with minimal perplexity loss.",
  Q6_K: "Q6_K — Near-lossless 6-bit quantization for high-VRAM machines.",
  Q8_0: "Q8_0 — Maximum 8-bit GGUF precision, virtually indistinguishable from original weights.",
};

type Tab = "discover" | "installed" | "cloud";

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
  onChat,
}: {
  model: CatalogModel;
  systemRam: number;
  downloading: boolean;
  progress?: DownloadProgress;
  onDownload: (id: string) => void;
  onCancel: (id: string) => void;
  onChat: (id: string) => void;
}) {
  const percent = progress?.percent ?? 0;
  const quantTip =
    QUANT_TOOLTIPS[model.quantization] ||
    `${model.quantization} — GGUF quantized weights optimized for local inference.`;

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
          <p className="text-[11px] text-neutral-500 flex items-center gap-1 flex-wrap">
            <span>
              {model.provider} · {model.parameter_size} · {model.size_gb} GB
            </span>
            {model.quantization && (
              <span
                title={quantTip}
                className="px-1.5 py-0.2 rounded bg-neutral-100 dark:bg-neutral-800 text-[10px] font-mono text-neutral-600 dark:text-neutral-400 cursor-help border border-neutral-200/70 dark:border-neutral-700"
              >
                {model.quantization}
              </span>
            )}
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

      {/* RAM + Fit Badge + Action */}
      {model.fit && (
        <div
          className={cn(
            "mb-2 px-2 py-1 rounded-md text-[11px] font-medium flex items-center justify-between",
            model.fit.verdict === "fits_gpu" &&
              "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
            model.fit.verdict === "partial_offload" &&
              "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
            model.fit.verdict === "wont_fit" &&
              "bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-300"
          )}
          title={model.fit.reason}
        >
          <span>{model.fit.badge_label}</span>
          {model.fit.estimated_tps > 0 && (
            <span className="tabular-nums opacity-80">~{model.fit.estimated_tps} tok/s</span>
          )}
        </div>
      )}
      <div className="flex items-center justify-between mt-auto pt-2 border-t border-neutral-100 dark:border-neutral-800">
        <RamIndicator required={model.ram_required_gb} systemRam={systemRam} />

        {model.installed ? (
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 text-xs font-medium text-green-600 dark:text-green-400">
              <Check className="w-3.5 h-3.5" /> Installed
            </span>
            <button
              type="button"
              onClick={() => onChat(model.id)}
              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded-lg bg-primary-50 dark:bg-primary-500/15 text-primary-600 dark:text-primary-400 hover:bg-primary-100 dark:hover:bg-primary-500/25 transition-colors"
            >
              Chat <ArrowRight className="w-3 h-3" />
            </button>
          </div>
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
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium rounded-full bg-primary-500 hover:bg-primary-600 text-white shadow-sm shadow-primary-500/25 transition-all active:scale-[0.98]"
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
  isLoaded,
  preloading,
  benchmarking,
  benchmarkTps,
  onPreload,
  onBenchmark,
  onChat,
  onDelete,
}: {
  model: InstalledModel;
  deleting: boolean;
  isLoaded: boolean;
  preloading: boolean;
  benchmarking: boolean;
  benchmarkTps?: number;
  onPreload: (id: string) => void;
  onBenchmark: (id: string) => void;
  onChat: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-800">
      <div className="flex items-center gap-3 min-w-0">
        <div className="p-2 rounded-lg bg-green-100 dark:bg-green-500/20 shrink-0">
          <Check className="w-4 h-4 text-green-600 dark:text-green-400" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="text-sm font-semibold text-neutral-900 dark:text-white truncate">
              {model.name}
            </h4>
            {isLoaded && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                Warm in RAM
              </span>
            )}
            {benchmarkTps !== undefined && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-primary-100 text-primary-700 dark:bg-primary-500/20 dark:text-primary-300 tabular-nums">
                <Gauge className="w-3 h-3" />
                {benchmarkTps.toFixed(1)} tok/s
              </span>
            )}
          </div>
          <p className="text-[11px] text-neutral-500 truncate">
            {model.provider} · {model.parameter_size} · {model.size_gb} GB on disk
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          onClick={() => onChat(model.id)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-primary-500 hover:bg-primary-600 text-white transition-colors"
        >
          <MessageSquare className="w-3.5 h-3.5" />
          Open in Chat
        </button>
        <button
          type="button"
          onClick={() => onPreload(model.id)}
          disabled={preloading || isLoaded}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors disabled:opacity-50"
          title="Preload GGUF weights into RAM/VRAM for instant first-token response"
        >
          {preloading ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Zap className="w-3.5 h-3.5 text-amber-500" />
          )}
          {isLoaded ? "Loaded" : "Preload"}
        </button>
        <button
          type="button"
          onClick={() => onBenchmark(model.id)}
          disabled={benchmarking}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors disabled:opacity-50"
          title="Run 64-token speed benchmark on your hardware"
        >
          {benchmarking ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin text-primary-500" />
          ) : (
            <Gauge className="w-3.5 h-3.5 text-primary-500" />
          )}
          {benchmarking ? "Benchmarking..." : "Benchmark"}
        </button>
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

// ── Custom Model Input (Live HF Search + Auto-Quant File Picker + Disk Import) ──

function CustomModelInput({ onDownload }: { onDownload: () => void }) {
  const [repo, setRepo] = useState("");
  const [filename, setFilename] = useState("");
  const [repoFiles, setRepoFiles] = useState<HfRepoFile[]>([]);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [hfQuery, setHfQuery] = useState("");
  const [hfResults, setHfResults] = useState<HfSearchModel[]>([]);
  const [searchingHf, setSearchingHf] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [localGgufPath, setLocalGgufPath] = useState("");
  const [importingLocal, setImportingLocal] = useState(false);

  const handleSearchHf = async () => {
    setSearchingHf(true);
    try {
      const res = await searchHfGgufModels(hfQuery.trim(), true);
      setHfResults(res.models || []);
    } catch {
      setHfResults([]);
    } finally {
      setSearchingHf(false);
    }
  };

  const handleInspectRepo = async (targetRepo: string) => {
    const clean = targetRepo.trim();
    if (!clean) return;
    setRepo(clean);
    setLoadingFiles(true);
    try {
      const res = await listHfRepoGgufFiles(clean);
      setRepoFiles(res.files || []);
      if (res.recommended_filename) {
        setFilename(res.recommended_filename);
      } else if (res.files?.length > 0) {
        setFilename(res.files[0].filename);
      }
    } catch {
      setRepoFiles([]);
    } finally {
      setLoadingFiles(false);
    }
  };

  const handleImportDisk = async () => {
    if (!localGgufPath.trim()) return;
    setImportingLocal(true);
    setStatus("Importing local .gguf...");
    try {
      await importLocalGguf(localGgufPath.trim(), false);
      setStatus("Imported local .gguf!");
      setLocalGgufPath("");
      onDownload();
    } catch (err) {
      setStatus(`Import error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setImportingLocal(false);
    }
  };

  const handleCustomDownload = async () => {
    if (!repo.trim() || !filename.trim()) return;
    setDownloading(true);
    setStatus("Downloading...");

    try {
      const baseUrl = await getApiBaseUrl();
      const token = await getSidecarToken();
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["X-ContextuAI-Token"] = token;
      const response = await fetch(`${baseUrl}/local-models/download/custom`, {
        method: "POST",
        headers,
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
                  setRepoFiles([]);
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
    <div className="space-y-4">
      {/* Live HuggingFace Hub Search */}
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={hfQuery}
          onChange={(e) => setHfQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearchHf()}
          placeholder="Search live HuggingFace GGUF repos (e.g. Qwen3, Llama-3.3, DeepSeek)..."
          className="flex-1 px-3 py-2 text-xs rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-white"
        />
        <button
          type="button"
          onClick={handleSearchHf}
          disabled={searchingHf}
          className="px-3 py-2 text-xs font-medium rounded-lg border border-neutral-200 dark:border-neutral-700 hover:bg-neutral-100 dark:hover:bg-neutral-800"
        >
          {searchingHf ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Search HF Hub"}
        </button>
      </div>

      {hfResults.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {hfResults.slice(0, 8).map((r) => (
            <button
              key={r.repo_id}
              type="button"
              onClick={() => handleInspectRepo(r.repo_id)}
              className="px-2.5 py-1 text-xs rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 hover:border-primary-500 text-neutral-800 dark:text-neutral-200"
            >
              {r.repo_id}
            </button>
          ))}
        </div>
      )}

      {/* Repo + Auto-Quant File Picker */}
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <label className="block text-[11px] text-neutral-500 mb-1">HuggingFace Repo</label>
          <div className="flex gap-1.5">
            <input
              type="text"
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              onBlur={() => repo.includes("/") && repoFiles.length === 0 && handleInspectRepo(repo)}
              placeholder="e.g. bartowski/Qwen2.5-7B-Instruct-GGUF"
              disabled={downloading}
              className="w-full px-3 py-2 text-xs rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-white placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-500/40"
            />
            <button
              type="button"
              onClick={() => handleInspectRepo(repo)}
              disabled={loadingFiles || !repo.trim()}
              className="px-2.5 py-2 text-xs rounded-lg border border-neutral-200 dark:border-neutral-700 hover:bg-neutral-100 dark:hover:bg-neutral-800 whitespace-nowrap"
            >
              {loadingFiles ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "List Quants"}
            </button>
          </div>
        </div>
        <div className="flex-1">
          <label className="block text-[11px] text-neutral-500 mb-1">
            GGUF Quantization File {repoFiles.length > 0 && `(${repoFiles.length} available)`}
          </label>
          {repoFiles.length > 0 ? (
            <select
              value={filename}
              onChange={(e) => setFilename(e.target.value)}
              disabled={downloading}
              className="w-full px-3 py-2 text-xs rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-white"
            >
              {repoFiles.map((f) => (
                <option key={f.filename} value={f.filename}>
                  {f.is_recommended_quant ? "★ Recommended · " : ""}
                  {f.filename} ({f.size_gb} GB · {f.fit.badge_label})
                </option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              value={filename}
              onChange={(e) => setFilename(e.target.value)}
              placeholder="e.g. Qwen2.5-7B-Instruct-Q4_K_M.gguf"
              disabled={downloading}
              className="w-full px-3 py-2 text-xs rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-white placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-500/40"
            />
          )}
        </div>
        <button
          onClick={handleCustomDownload}
          disabled={downloading || !repo.trim() || !filename.trim()}
          className="px-4 py-2 text-xs font-medium rounded-lg bg-neutral-900 dark:bg-white text-white dark:text-neutral-900 hover:bg-neutral-800 dark:hover:bg-neutral-100 transition-colors disabled:opacity-50"
        >
          {downloading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Pull"}
        </button>
      </div>

      {/* Import Local .gguf from Disk */}
      <div className="pt-3 border-t border-neutral-200 dark:border-neutral-800 flex items-end gap-2">
        <div className="flex-1">
          <label className="block text-[11px] text-neutral-500 mb-1">
            Import Existing <code className="font-mono">.gguf</code> File from Disk (Zero Re-Download)
          </label>
          <input
            type="text"
            value={localGgufPath}
            onChange={(e) => setLocalGgufPath(e.target.value)}
            placeholder="Absolute path to local .gguf file (e.g. C:\Models\qwen2.5-7b-q4_k_m.gguf)"
            disabled={importingLocal}
            className="w-full px-3 py-2 text-xs rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-white"
          />
        </div>
        <button
          type="button"
          onClick={handleImportDisk}
          disabled={importingLocal || !localGgufPath.trim()}
          className="px-4 py-2 text-xs font-medium rounded-lg border border-neutral-300 dark:border-neutral-700 hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-800 dark:text-neutral-200 disabled:opacity-50"
        >
          {importingLocal ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Import .gguf"}
        </button>
      </div>

      {status && (
        <div className="text-[11px] text-neutral-500">{status}</div>
      )}
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────

export default function ModelsPage() {
  const navigate = useNavigate();
  const { status: backendStatus } = useBackendStatus();
  const [tab, setTab] = useState<Tab>("discover");
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [hardwareProfile, setHardwareProfile] = useState<HardwareProfile | null>(null);
  const [bestModel, setBestModel] = useState<CatalogModel | null>(null);
  const [catalog, setCatalog] = useState<CatalogModel[]>([]);
  const [installed, setInstalled] = useState<InstalledModel[]>([]);
  const [diskUsage, setDiskUsage] = useState<DiskUsage | null>(null);
  const [loadedModelId, setLoadedModelId] = useState<string | null>(null);
  const [preloadingId, setPreloadingId] = useState<string | null>(null);
  const [benchmarkingId, setBenchmarkingId] = useState<string | null>(null);
  const [benchmarks, setBenchmarks] = useState<Record<string, number>>({});
  const [rescanningHw, setRescanningHw] = useState(false);
  const [wontFitGuardModel, setWontFitGuardModel] = useState<CatalogModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [downloads, setDownloads] = useState<Record<string, DownloadProgress>>({});
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [errorModal, setErrorModal] = useState<{ title: string; message: string } | null>(null);
  const abortControllers = useRef<Record<string, AbortController>>({});

  // ── Load data ──────────────────────────────────────────────────────────

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [sysInfo, catalogRes, installedRes, loadedRes] = await Promise.all([
        getSystemInfo(),
        getCatalog(),
        getInstalledModels(),
        getLoadedModel().catch(() => ({ loaded: false, model_id: undefined })),
      ]);
      setSystemInfo(sysInfo);
      setCatalog(catalogRes.models);
      setHardwareProfile(catalogRes.hardware_profile ?? null);
      setBestModel(catalogRes.best_for_machine ?? null);
      setInstalled(installedRes.models);
      setDiskUsage(installedRes.disk_usage);
      setLoadedModelId(loadedRes.model_id ?? null);
    } catch (err) {
      console.error("Failed to load model data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRescanHardware = async () => {
    setRescanningHw(true);
    try {
      const hw = await getHardwareProfile(true);
      setHardwareProfile(hw);
      await refreshModelCatalog().catch(() => {});
      await loadData();
    } catch {
      // ignore
    } finally {
      setRescanningHw(false);
    }
  };

  const handlePreload = async (modelId: string) => {
    setPreloadingId(modelId);
    try {
      const res = await preloadLocalModel(modelId);
      setLoadedModelId(res.model_id ?? modelId);
    } catch (err) {
      setErrorModal({
        title: "Preload Notice",
        message:
          err instanceof Error
            ? err.message
            : "Could not preload model into memory.",
      });
    } finally {
      setPreloadingId(null);
    }
  };

  const handleBenchmark = async (modelId: string) => {
    setBenchmarkingId(modelId);
    try {
      const res = await benchmarkLocalModel(modelId);
      if (typeof res.tokens_per_second === "number") {
        setBenchmarks((prev) => ({ ...prev, [modelId]: res.tokens_per_second }));
      }
      setLoadedModelId(res.model_id || modelId);
    } catch (err) {
      setErrorModal({
        title: "Benchmark Notice",
        message:
          err instanceof Error
            ? err.message
            : "Could not complete speed benchmark.",
      });
    } finally {
      setBenchmarkingId(null);
    }
  };

  const handleOpenInChat = useCallback(
    (modelId: string) => {
      navigate(`/?model=${encodeURIComponent(modelId)}`);
    },
    [navigate]
  );

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
          } else if (progress.status === "error") {
            setErrorModal({
              title: "Download Failed",
              message: progress.detail || "An unexpected error occurred during download.",
            });
            setDownloads((prev) => {
              const next = { ...prev };
              delete next[modelId];
              return next;
            });
          } else if (progress.status === "cancelled") {
            setDownloads((prev) => {
              const next = { ...prev };
              delete next[modelId];
              return next;
            });
          }
        },
        controller.signal
      );
    } catch (err) {
      // Network error or fetch failure
      setDownloads((prev) => {
        const next = { ...prev };
        delete next[modelId];
        return next;
      });
      const msg = err instanceof Error ? err.message : "Network error";
      if (!controller.signal.aborted) {
        setErrorModal({ title: "Download Failed", message: msg });
      }
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
      setErrorModal({ title: "Delete Failed", message: err instanceof Error ? err.message : "Could not delete model." });
    } finally {
      setDeletingId(null);
    }
  }, [loadData]);

  const requestDownload = useCallback(
    (modelId: string) => {
      const target = catalog.find((m) => m.id === modelId);
      if (target?.fit?.verdict === "wont_fit") {
        setWontFitGuardModel(target);
        return;
      }
      void handleDownload(modelId);
    },
    [catalog, handleDownload]
  );

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
    <div className="flex flex-col h-full">
      {/* M3 Header */}
      <div className="px-6 pt-6 pb-4 border-b border-neutral-200/75 dark:border-neutral-800/90 bg-white/80 dark:bg-neutral-900/75 backdrop-blur-md">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3.5">
            <div className="flex items-center justify-center w-11 h-11 rounded-2xl bg-primary-500/12 text-primary-600 dark:text-primary-400 border border-primary-500/20">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white">
                Model Hub
              </h1>
              <p className="text-xs sm:text-sm text-neutral-500 dark:text-neutral-400">
                Download, inspect, and benchmark local GGUF models tailored to your hardware
              </p>
            </div>
          </div>
          <button
            onClick={loadData}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-full text-xs font-medium border border-neutral-200/80 dark:border-neutral-700/80 bg-white/80 dark:bg-neutral-800/80 hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-3.5 h-3.5 text-neutral-500" />
            <span className="hidden sm:inline text-neutral-600 dark:text-neutral-300">Refresh</span>
          </button>
        </div>

        {/* M3 Hardware X-Ray Tonal Hero Card (SPEC-27) */}
        {systemInfo && (
          <div className="flex flex-wrap items-center gap-3 p-4 rounded-2xl m3-card-tonal mb-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-primary-500/15 text-primary-600 dark:text-primary-400">
                <Cpu className="w-4 h-4" />
              </div>
              <div>
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-xs font-bold uppercase tracking-wider text-primary-700 dark:text-primary-300">
                    Hardware X-Ray
                  </span>
                  {hardwareProfile?.recommended_backend && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase bg-primary-500/15 text-primary-700 dark:text-primary-300">
                      {hardwareProfile.recommended_backend} Engine
                    </span>
                  )}
                  {hardwareProfile?.avx2 && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-white/80 dark:bg-neutral-900/70 text-neutral-600 dark:text-neutral-300 border border-neutral-200/70 dark:border-neutral-700">
                      AVX2
                    </span>
                  )}
                </div>
                <div className="text-xs text-neutral-600 dark:text-neutral-300 mt-0.5 flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-neutral-900 dark:text-white">
                    {systemInfo.total_ram_gb} GB RAM
                  </span>
                  {hardwareProfile?.cpu_cores_physical && (
                    <span>· {hardwareProfile.cpu_cores_physical}C/{hardwareProfile.cpu_cores_logical}T CPU</span>
                  )}
                  <span>· Up to {systemInfo.max_recommended_params} params recommended</span>
                </div>
              </div>
            </div>
            {(hardwareProfile?.gpu_name || systemInfo.gpu) && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/90 dark:bg-neutral-900/80 border border-neutral-200/80 dark:border-neutral-700 text-xs text-neutral-700 dark:text-neutral-300">
                <Zap className="w-3.5 h-3.5 text-primary-500" />
                <span className="font-medium">{hardwareProfile?.gpu_name || systemInfo.gpu}</span>
                {(hardwareProfile?.gpu_vram_gb || systemInfo.gpu_vram_gb) && (
                  <span className="text-neutral-500">
                    ({hardwareProfile?.gpu_vram_gb ?? systemInfo.gpu_vram_gb} GB VRAM)
                  </span>
                )}
              </div>
            )}
            <div className="ml-auto flex items-center gap-2.5">
              {diskUsage && (
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/70 dark:bg-neutral-900/60 text-xs text-neutral-600 dark:text-neutral-300">
                  <HardDrive className="w-3.5 h-3.5 text-primary-500" />
                  {diskUsage.models_gb} GB used · {diskUsage.disk_free_gb} GB free
                </div>
              )}
              <button
                type="button"
                onClick={handleRescanHardware}
                disabled={rescanningHw}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-primary-500/15 hover:bg-primary-500/25 text-primary-700 dark:text-primary-300 transition-colors"
                title="Rescan GPU/RAM & sync OTA catalog"
              >
                <RefreshCw className={cn("w-3 h-3", rescanningHw && "animate-spin")} />
                Rescan HW
              </button>
            </div>
          </div>
        )}

        {/* M3 Segmented Tabs */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex gap-1 p-1 rounded-2xl bg-neutral-100/80 dark:bg-neutral-950/70 border border-neutral-200/70 dark:border-neutral-800">
            <button
              onClick={() => setTab("discover")}
              className={cn(
                "px-4 py-1.5 text-sm font-medium rounded-xl transition-all",
                tab === "discover"
                  ? "bg-primary-500/15 text-primary-700 dark:text-primary-300 shadow-sm ring-1 ring-primary-500/25"
                  : "text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-200"
              )}
            >
              Discover
            </button>
            <button
              onClick={() => setTab("installed")}
              className={cn(
                "px-4 py-1.5 text-sm font-medium rounded-xl transition-all flex items-center gap-2",
                tab === "installed"
                  ? "bg-primary-500/15 text-primary-700 dark:text-primary-300 shadow-sm ring-1 ring-primary-500/25"
                  : "text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-200"
              )}
            >
              Installed
              {installed.length > 0 && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-primary-500 text-white">
                  {installed.length}
                </span>
              )}
            </button>
            <button
              onClick={() => setTab("cloud")}
              className={cn(
                "px-4 py-1.5 text-sm font-medium rounded-xl transition-all flex items-center gap-2",
                tab === "cloud"
                  ? "bg-primary-500/15 text-primary-700 dark:text-primary-300 shadow-sm ring-1 ring-primary-500/25"
                  : "text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-200"
              )}
            >
              Cloud
            </button>
          </div>
          {activeDownloadCount > 0 && (
            <span className="ml-2 px-2.5 py-1 text-[11px] font-bold rounded-full bg-primary-500/15 text-primary-700 dark:text-primary-300 animate-pulse">
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
            <div className="flex flex-wrap items-center gap-3 mb-6">
              <div className="relative flex-1 min-w-[220px] max-w-md">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search models..."
                  className="w-full pl-10 pr-4 py-2 text-sm rounded-full border border-neutral-200/80 dark:border-neutral-700/80 bg-white/90 dark:bg-neutral-900/90 text-neutral-900 dark:text-white placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-500/40"
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

            {/* SPEC-27: Best Model for Your Machine Hero Banner */}
            {bestModel && !search && !activeCategory && (
              <div className="mb-6 p-4 m3-card-tonal flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-primary-600 dark:text-primary-400 mb-1">
                    <Star className="w-3.5 h-3.5" />
                    Best Model for Your Machine
                    {hardwareProfile?.recommended_backend && (
                      <span className="px-2 py-0.5 rounded-full bg-primary-100 dark:bg-primary-900/40 text-[10px]">
                        {hardwareProfile.recommended_backend.toUpperCase()} Accelerated
                      </span>
                    )}
                  </div>
                  <h3 className="text-base font-bold text-neutral-900 dark:text-white">
                    {bestModel.name} ({bestModel.parameter_size} · {bestModel.quantization})
                  </h3>
                  <p className="text-xs text-neutral-600 dark:text-neutral-400 mt-0.5">
                    {bestModel.description} —{" "}
                    <span className="font-medium">
                      {bestModel.fit?.badge_label || `${bestModel.size_gb} GB`}
                      {bestModel.fit?.estimated_tps ? ` · ~${bestModel.fit.estimated_tps} tok/s` : ""}
                    </span>
                  </p>
                </div>
                <div className="shrink-0">
                  {bestModel.installed ? (
                    <span className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold rounded-lg bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300">
                      <Check className="w-4 h-4" /> Ready on Disk
                    </span>
                  ) : (
                    <button
                      onClick={() => handleDownload(bestModel.id)}
                      disabled={!!downloads[bestModel.id]}
                      className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-lg bg-primary-500 hover:bg-primary-600 text-white transition-colors disabled:opacity-50"
                    >
                      <Download className="w-4 h-4" />
                      {downloads[bestModel.id] ? "Downloading..." : `1-Click Download (${bestModel.size_gb} GB)`}
                    </button>
                  )}
                </div>
              </div>
            )}

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
                      onDownload={requestDownload}
                      onCancel={handleCancel}
                      onChat={handleOpenInChat}
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
                      onDownload={requestDownload}
                      onCancel={handleCancel}
                      onChat={handleOpenInChat}
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
                    isLoaded={
                      !!loadedModelId &&
                      (loadedModelId === m.id ||
                        loadedModelId === m.id.replace(/^local:/, ""))
                    }
                    preloading={preloadingId === m.id}
                    benchmarking={benchmarkingId === m.id}
                    benchmarkTps={benchmarks[m.id]}
                    onPreload={handlePreload}
                    onBenchmark={handleBenchmark}
                    onChat={handleOpenInChat}
                    onDelete={handleDelete}
                  />
                ))}
              </div>
            )}
          </>
        )}

        {/* ── Cloud Tab ─────────────────────────────────────────────────── */}
        {tab === "cloud" && <CloudProvidersTab />}
      </div>

      {/* Won't Fit Hardware Guardrail Modal (SPEC-27) */}
      <Dialog
        open={!!wontFitGuardModel}
        onClose={() => setWontFitGuardModel(null)}
        title="Hardware Memory Guardrail"
        actions={
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setWontFitGuardModel(null)}
              className="px-4 py-2 text-xs font-medium rounded-lg border border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800"
            >
              Cancel
            </button>
            {bestModel && !bestModel.installed && (
              <button
                type="button"
                onClick={() => {
                  const recId = bestModel.id;
                  setWontFitGuardModel(null);
                  void handleDownload(recId);
                }}
                className="px-4 py-2 text-xs font-semibold rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white"
              >
                Download Recommended ({bestModel.name})
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                if (wontFitGuardModel) {
                  const id = wontFitGuardModel.id;
                  setWontFitGuardModel(null);
                  void handleDownload(id);
                }
              }}
              className="px-4 py-2 text-xs font-medium rounded-lg bg-amber-500 hover:bg-amber-600 text-white"
            >
              Download Anyway
            </button>
          </div>
        }
      >
        {wontFitGuardModel && (
          <div className="space-y-3 text-sm text-neutral-700 dark:text-neutral-300">
            <div className="flex items-start gap-3 p-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-700 dark:text-red-300 text-xs">
              <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
              <div>
                <div className="font-semibold">
                  {wontFitGuardModel.name} requires ~{wontFitGuardModel.ram_required_gb} GB memory
                </div>
                <div className="mt-0.5">
                  {wontFitGuardModel.fit?.reason ||
                    `Your system has ${systemInfo?.total_ram_gb ?? 8} GB total RAM. Loading this model may cause heavy swap thrashing or out-of-memory errors.`}
                </div>
              </div>
            </div>
            {bestModel && (
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                For optimal speed on your machine, Hardware X-Ray recommends{" "}
                <strong className="text-neutral-900 dark:text-white">
                  {bestModel.name} ({bestModel.size_gb} GB)
                </strong>
                .
              </p>
            )}
          </div>
        )}
      </Dialog>

      {/* Error modal */}
      <Dialog
        open={!!errorModal}
        onClose={() => setErrorModal(null)}
        title={errorModal?.title || "Error"}
        actions={
          <button
            onClick={() => setErrorModal(null)}
            className="px-4 py-2 text-sm font-medium text-white bg-primary-500 hover:bg-primary-600 rounded-lg transition-colors"
          >
            OK
          </button>
        }
      >
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-500 mt-0.5 shrink-0" />
          <p className="text-sm text-neutral-700 dark:text-neutral-300 whitespace-pre-wrap">
            {errorModal?.message}
          </p>
        </div>
      </Dialog>
    </div>
  );
}
