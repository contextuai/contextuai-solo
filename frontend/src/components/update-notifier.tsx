import { useState, useEffect, useCallback } from "react";
import { check, type Update } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import { cn } from "@/lib/utils";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Download, RefreshCw, X, Sparkles } from "lucide-react";

type Stage = "toast" | "modal-idle" | "downloading" | "ready" | "installing";

export function UpdateNotifier() {
  const [update, setUpdate] = useState<Update | null>(null);
  const [stage, setStage] = useState<Stage>("toast");
  const [progress, setProgress] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Check for updates once on mount
  useEffect(() => {
    if (!("__TAURI__" in window)) return;

    let cancelled = false;
    (async () => {
      try {
        const result = await check();
        if (!cancelled && result?.available) {
          setUpdate(result);
        }
      } catch (err) {
        console.warn("Update check failed:", err);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const handleDownload = useCallback(async () => {
    if (!update) return;
    setStage("downloading");
    setProgress(0);
    setError(null);

    try {
      let totalBytes = 0;
      let downloadedBytes = 0;

      await update.downloadAndInstall((event) => {
        switch (event.event) {
          case "Started":
            totalBytes = event.data.contentLength ?? 0;
            break;
          case "Progress":
            downloadedBytes += event.data.chunkLength;
            if (totalBytes > 0) {
              setProgress(Math.min(100, Math.round((downloadedBytes / totalBytes) * 100)));
            }
            break;
          case "Finished":
            setProgress(100);
            break;
        }
      });

      setStage("ready");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
      setStage("modal-idle");
    }
  }, [update]);

  const handleRelaunch = useCallback(async () => {
    setStage("installing");
    try {
      await relaunch();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Relaunch failed");
      setStage("ready");
    }
  }, []);

  // Nothing to show
  if (!update || dismissed) return null;

  const version = update.version;

  // Toast — bottom-left corner
  if (stage === "toast") {
    return (
      <div className="fixed bottom-4 left-4 z-50 animate-in slide-in-from-bottom-4 fade-in duration-300">
        <div
          className={cn(
            "flex items-center gap-3 pl-4 pr-2 py-2.5 rounded-xl cursor-pointer",
            "bg-neutral-900 dark:bg-neutral-800",
            "border border-neutral-700 dark:border-neutral-700",
            "shadow-lg shadow-black/20",
            "text-sm text-white",
            "hover:bg-neutral-800 dark:hover:bg-neutral-750 transition-colors"
          )}
        >
          <div
            className="flex items-center gap-2 flex-1"
            onClick={() => setStage("modal-idle")}
          >
            <Sparkles className="w-4 h-4 text-primary-400 shrink-0" />
            <span>Update available — v{version}</span>
          </div>
          <button
            onClick={(e) => { e.stopPropagation(); setDismissed(true); }}
            className="p-1 rounded-lg text-neutral-400 hover:text-white hover:bg-neutral-700 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    );
  }

  // Modal
  return (
    <Dialog
      open
      onClose={() => { if (stage !== "installing") setDismissed(true); }}
      title={`Update to v${version}`}
    >
      {/* Release notes */}
      {update.body && (
        <div className="mb-4 max-h-48 overflow-y-auto text-sm text-neutral-600 dark:text-neutral-400 whitespace-pre-wrap">
          {update.body}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mb-3 p-2.5 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-xs">
          {error}
        </div>
      )}

      {/* Progress bar */}
      {(stage === "downloading" || stage === "ready") && (
        <div className="mb-4">
          <div className="flex justify-between text-xs text-neutral-500 dark:text-neutral-400 mb-1.5">
            <span>{stage === "ready" ? "Download complete" : "Downloading..."}</span>
            <span>{progress}%</span>
          </div>
          <div className="w-full h-2 bg-neutral-200 dark:bg-neutral-700 rounded-full overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-300",
                stage === "ready" ? "bg-green-500" : "bg-primary-500"
              )}
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-end gap-3 pt-2">
        {stage !== "installing" && (
          <Button variant="ghost" size="sm" onClick={() => setDismissed(true)}>
            Later
          </Button>
        )}

        {stage === "modal-idle" && (
          <Button size="sm" onClick={handleDownload}>
            <Download className="w-4 h-4" />
            Download
          </Button>
        )}

        {stage === "downloading" && (
          <Button size="sm" disabled>
            <Download className="w-4 h-4 animate-pulse" />
            Downloading...
          </Button>
        )}

        {stage === "ready" && (
          <Button size="sm" onClick={handleRelaunch}>
            <RefreshCw className="w-4 h-4" />
            Relaunch to Update
          </Button>
        )}

        {stage === "installing" && (
          <Button size="sm" disabled>
            <RefreshCw className="w-4 h-4 animate-spin" />
            Restarting...
          </Button>
        )}
      </div>
    </Dialog>
  );
}
