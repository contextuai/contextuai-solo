/**
 * SPEC-15 & SPEC-09: Context Window Usage Meter & Local Model Warmth Pill
 *
 * Displays estimated active context tokens vs model context window in Chat
 * (`~1.4k / 32k ctx`) with a visual warning when approaching truncation threshold,
 * plus 1-click Preload into RAM/VRAM for local GGUF models.
 */
import { useState, useEffect, useMemo } from "react";
import { Cpu, Zap, AlertTriangle, Loader2, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/chat";
import type { ModelConfig } from "@/lib/api/models-client";
import { getLoadedModel, preloadLocalModel } from "@/lib/api/local-models-client";

interface ContextMeterProps {
  messages: ChatMessage[];
  draftInput: string;
  selectedModel: ModelConfig | null;
}

function estimateTokens(text: string): number {
  if (!text) return 0;
  // Standard ~4 chars/token heuristic for English/code
  return Math.ceil(text.length / 4);
}

function formatTokenCount(n: number): string {
  if (n >= 1000) {
    return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k`;
  }
  return String(n);
}

export function ContextMeter({
  messages,
  draftInput,
  selectedModel,
}: ContextMeterProps) {
  const [loadedModelId, setLoadedModelId] = useState<string | null>(null);
  const [preloading, setPreloading] = useState(false);

  const isLocal = useMemo(() => {
    if (!selectedModel) return false;
    return (
      selectedModel.provider?.toLowerCase() === "local" ||
      selectedModel.id.startsWith("local:") ||
      selectedModel.id.startsWith("local-")
    );
  }, [selectedModel]);

  useEffect(() => {
    let mounted = true;
    if (!isLocal) return;
    getLoadedModel()
      .then((res) => {
        if (mounted) setLoadedModelId(res.model_id ?? null);
      })
      .catch(() => {});
    return () => {
      mounted = false;
    };
  }, [isLocal, selectedModel?.id, messages.length]);

  const usedTokens = useMemo(() => {
    let total = estimateTokens(draftInput);
    for (const m of messages) {
      total += estimateTokens(m.content || "");
      if (m.reasoning) total += estimateTokens(m.reasoning);
    }
    // Add system prompt / overhead buffer when conversation has started
    if (messages.length > 0) total += 250;
    return total;
  }, [messages, draftInput]);

  const maxContext = useMemo(() => {
    const raw =
      (selectedModel as unknown as { context_window?: number })?.context_window ||
      (selectedModel as unknown as { max_tokens?: number })?.max_tokens ||
      32768;
    return raw >= 2048 ? raw : 32768;
  }, [selectedModel]);

  const ratio = Math.min(1, usedTokens / maxContext);
  const pct = Math.round(ratio * 100);
  const isNearLimit = ratio >= 0.8;
  const isWarning = ratio >= 0.6 && ratio < 0.8;

  const cleanSelectedId = selectedModel?.id.replace(/^local:/, "") ?? "";
  const isWarm =
    isLocal &&
    !!loadedModelId &&
    (loadedModelId === cleanSelectedId ||
      loadedModelId === selectedModel?.id ||
      cleanSelectedId.includes(loadedModelId));

  const handlePreload = async () => {
    if (!selectedModel || preloading) return;
    setPreloading(true);
    try {
      const res = await preloadLocalModel(selectedModel.id);
      setLoadedModelId(res.model_id || cleanSelectedId);
    } catch {
      // ignore if llama-cpp not installed in test env
    } finally {
      setPreloading(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      {/* Local GGUF Warmth / Preload Pill */}
      {isLocal && selectedModel && (
        <button
          type="button"
          onClick={handlePreload}
          disabled={preloading || isWarm}
          title={
            isWarm
              ? `${selectedModel.name} is warm in RAM/VRAM — zero cold-start delay`
              : "Click to preload GGUF weights into RAM/VRAM before sending your first message"
          }
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors",
            isWarm
              ? "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/25 cursor-default"
              : "bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300 border-neutral-200 dark:border-neutral-700 hover:border-primary-400"
          )}
        >
          {preloading ? (
            <>
              <Loader2 className="w-3 h-3 animate-spin text-primary-500" />
              <span>Loading GGUF...</span>
            </>
          ) : isWarm ? (
            <>
              <CheckCircle2 className="w-3 h-3 text-emerald-500" />
              <span>Warm in RAM</span>
            </>
          ) : (
            <>
              <Zap className="w-3 h-3 text-amber-500" />
              <span>Preload Model</span>
            </>
          )}
        </button>
      )}

      {/* Context Window Usage Pill */}
      <div
        className={cn(
          "inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors",
          isNearLimit
            ? "bg-red-50 dark:bg-red-500/15 text-red-700 dark:text-red-300 border-red-200 dark:border-red-500/30"
            : isWarning
              ? "bg-amber-50 dark:bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/30"
              : "bg-neutral-50 dark:bg-neutral-800/80 text-neutral-600 dark:text-neutral-400 border-neutral-200 dark:border-neutral-700"
        )}
        title={`Estimated context usage: ~${usedTokens.toLocaleString()} of ${maxContext.toLocaleString()} tokens (${pct}%).${
          isNearLimit
            ? " Context window is over 80% full — older messages may be truncated."
            : ""
        }`}
      >
        {isNearLimit ? (
          <AlertTriangle className="w-3 h-3 text-red-500 shrink-0" />
        ) : (
          <Cpu className="w-3 h-3 text-neutral-400 shrink-0" />
        )}
        <span className="tabular-nums">
          {formatTokenCount(usedTokens)} / {formatTokenCount(maxContext)} ctx
        </span>
        <div className="w-10 h-1.5 rounded-full bg-neutral-200 dark:bg-neutral-700 overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-300",
              isNearLimit
                ? "bg-red-500"
                : isWarning
                  ? "bg-amber-500"
                  : "bg-emerald-500"
            )}
            style={{ width: `${Math.max(4, pct)}%` }}
          />
        </div>
      </div>
    </div>
  );
}
