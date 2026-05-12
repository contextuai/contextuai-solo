import { useEffect, useRef, useState } from "react";
import { ChevronDown, CheckCircle2, AlertCircle, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/transport";
import { listCloudProviders } from "@/lib/api/cloud-providers-client";
import type { CloudProvider } from "@/lib/api/cloud-providers-client";

// ---------------------------------------------------------------------------
// Types from GET /v1/models (OpenAI-shape)
// ---------------------------------------------------------------------------

interface OpenAIModel {
  id: string;
  object: string;
  owned_by: string;
}

interface OpenAIModelList {
  data: OpenAIModel[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function shortLabel(modelId: string, ownedBy: string): string {
  // Strip provider prefix if present (e.g. "anthropic:claude-opus-4-7")
  const bare = modelId.includes(":") ? modelId.split(":").slice(1).join(":") : modelId;
  // Shorten common names
  if (bare.includes("claude-opus")) return `Opus ${bare.split("-").pop()} (anthropic)`;
  if (bare.includes("claude-sonnet")) return `Sonnet ${bare.split("-").pop()} (anthropic)`;
  if (bare.includes("claude-haiku")) return `Haiku ${bare.split("-").pop()} (anthropic)`;
  if (bare.includes("gpt-4o")) return "GPT-4o (openai)";
  if (bare.includes("gemini")) return `${bare} (google)`;
  // Local / ollama
  if (ownedBy === "ollama" || modelId.startsWith("ollama:")) {
    return `${bare} (ollama)`;
  }
  if (!modelId.includes(":")) return `${bare} (local)`;
  return bare;
}

function providerFromOwnedBy(ownedBy: string): string {
  // Normalize to lowercase key used in saved providers
  const low = ownedBy.toLowerCase();
  if (low === "anthropic") return "anthropic";
  if (low === "openai") return "openai";
  if (low === "google") return "google";
  if (low === "bedrock" || low === "aws") return "bedrock";
  if (low === "ollama") return "ollama";
  if (low === "local" || low === "") return "local";
  return low;
}

type GroupedModels = Map<string, OpenAIModel[]>;

function groupModels(models: OpenAIModel[]): GroupedModels {
  const map: GroupedModels = new Map();
  for (const m of models) {
    const group = providerFromOwnedBy(m.owned_by);
    if (!map.has(group)) map.set(group, []);
    map.get(group)!.push(m);
  }
  return map;
}

function groupLabel(group: string): string {
  const labels: Record<string, string> = {
    local: "LOCAL — DOWNLOADED",
    ollama: "LOCAL — OLLAMA",
    anthropic: "CLOUD — ANTHROPIC",
    openai: "CLOUD — OPENAI",
    google: "CLOUD — GOOGLE",
    bedrock: "CLOUD — AWS BEDROCK",
  };
  return labels[group] ?? group.toUpperCase();
}

const CLOUD_GROUPS = new Set(["anthropic", "openai", "google", "bedrock"]);

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface ModelPickerProps {
  value: string;
  onChange: (modelId: string) => void;
  className?: string;
}

export function ModelPicker({ value, onChange, className }: ModelPickerProps) {
  const [open, setOpen] = useState(false);
  const [models, setModels] = useState<OpenAIModel[]>([]);
  const [savedProviders, setSavedProviders] = useState<CloudProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Fetch models + saved cloud providers once on mount
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.get<OpenAIModelList>("/v1/models").then((r) => r.data.data ?? []).catch(() => [] as OpenAIModel[]),
      listCloudProviders().catch(() => [] as CloudProvider[]),
    ]).then(([m, p]) => {
      if (cancelled) return;
      setModels(m);
      setSavedProviders(p);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    window.addEventListener("mousedown", handler);
    return () => window.removeEventListener("mousedown", handler);
  }, [open]);

  const grouped = groupModels(models);
  const savedProviderTypes = new Set(savedProviders.map((p) => p.provider_type));

  // All provider groups we want to show — discovered groups first, then
  // any cloud groups not present in the model list (show "no key" hint)
  const allGroups = Array.from(
    new Set([
      ...Array.from(grouped.keys()),
      ...Array.from(CLOUD_GROUPS),
    ]),
  );

  const currentModel = models.find((m) => m.id === value);
  const triggerLabel = currentModel
    ? shortLabel(currentModel.id, currentModel.owned_by)
    : value || "Select model…";

  return (
    <div className={cn("relative", className)} ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "w-full flex items-center justify-between gap-2 px-3 py-2 rounded-xl text-sm",
          "bg-neutral-50 dark:bg-neutral-800",
          "border border-neutral-200 dark:border-neutral-700",
          "text-neutral-900 dark:text-white",
          "hover:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/40",
          "transition-all",
        )}
      >
        <span className="truncate text-left">{loading ? "Loading models…" : triggerLabel}</span>
        <ChevronDown className={cn("w-4 h-4 text-neutral-400 flex-shrink-0 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div
          className={cn(
            "absolute left-0 top-full mt-1 z-50 w-80",
            "rounded-xl border border-neutral-200 dark:border-neutral-800",
            "bg-white dark:bg-neutral-900 shadow-xl",
            "overflow-y-auto max-h-96",
          )}
        >
          {allGroups.map((group) => {
            const groupModels = grouped.get(group) ?? [];
            const isCloud = CLOUD_GROUPS.has(group);
            const hasKey = isCloud ? savedProviderTypes.has(group as CloudProvider["provider_type"]) : null;

            return (
              <div key={group}>
                {/* Group header */}
                <div className="flex items-center justify-between gap-2 px-3 pt-2 pb-1">
                  <span className="text-[10px] font-semibold tracking-wider text-neutral-400 dark:text-neutral-500 uppercase">
                    {groupLabel(group)}
                  </span>
                  {isCloud && (
                    <span className={cn("flex items-center gap-1 text-[10px]", hasKey ? "text-emerald-500" : "text-amber-500")}>
                      {hasKey ? (
                        <CheckCircle2 className="w-3 h-3" />
                      ) : (
                        <AlertCircle className="w-3 h-3" />
                      )}
                      {hasKey ? "key saved" : "no key"}
                    </span>
                  )}
                </div>

                {groupModels.length === 0 ? (
                  <div className="px-3 pb-2">
                    {isCloud && !hasKey ? (
                      <a
                        href="/settings?tab=ai-providers"
                        onClick={() => setOpen(false)}
                        className="flex items-center gap-1 text-xs text-primary-500 hover:underline"
                      >
                        Set up {group} provider <ExternalLink className="w-3 h-3" />
                      </a>
                    ) : (
                      <span className="text-xs text-neutral-400 dark:text-neutral-500">No models available</span>
                    )}
                  </div>
                ) : (
                  <div className="pb-1">
                    {groupModels.map((m) => (
                      <button
                        key={m.id}
                        type="button"
                        onClick={() => {
                          onChange(m.id);
                          setOpen(false);
                        }}
                        className={cn(
                          "w-full text-left px-3 py-1.5 text-sm",
                          "hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors",
                          m.id === value && "bg-primary-50 dark:bg-primary-500/10 text-primary-600 dark:text-primary-400",
                          m.id !== value && "text-neutral-800 dark:text-neutral-200",
                        )}
                      >
                        {shortLabel(m.id, m.owned_by)}
                      </button>
                    ))}
                  </div>
                )}

                <div className="border-b border-neutral-100 dark:border-neutral-800 last:border-0" />
              </div>
            );
          })}

          {models.length === 0 && !loading && (
            <div className="px-4 py-6 text-center text-xs text-neutral-400">
              No models found. Download a local model or configure a cloud provider.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
