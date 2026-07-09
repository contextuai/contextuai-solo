import { useCallback, useEffect, useMemo, useState } from "react";
import { Brain, Download, Loader2, Plus, Search, ShieldOff, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { FactRow } from "@/components/memory/fact-row";
import { FactFormModal, type FactFormValues } from "@/components/memory/fact-form-modal";
import { MemorySettingsCard } from "@/components/memory/memory-settings-card";
import { cn } from "@/lib/utils";
import {
  createFact,
  deleteFact,
  exportMemory,
  getMemorySettings,
  listFacts,
  pinFact,
  updateFact,
  updateMemorySettings,
  type MemoryFact,
  type MemorySettings,
} from "@/lib/api/memory-client";

type StatusFilter = "all" | "active" | "review";

const FILTERS: { id: StatusFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "active", label: "Active" },
  { id: "review", label: "Review" },
];

export default function MemoryPage() {
  const [facts, setFacts] = useState<MemoryFact[]>([]);
  const [loadingFacts, setLoadingFacts] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [searchInput, setSearchInput] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  const [settings, setSettings] = useState<MemorySettings | null>(null);
  const [settingsLoading, setSettingsLoading] = useState(true);

  const [formOpen, setFormOpen] = useState(false);
  const [editingFact, setEditingFact] = useState<MemoryFact | null>(null);

  const [exporting, setExporting] = useState(false);

  // Debounce the search box — semantic search hits the embedding model.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(searchInput.trim()), 350);
    return () => clearTimeout(t);
  }, [searchInput]);

  const reloadFacts = useCallback(async () => {
    setLoadingFacts(true);
    setListError(null);
    try {
      const items = await listFacts({
        status: statusFilter === "all" ? undefined : statusFilter,
        q: debouncedQuery || undefined,
      });
      setFacts(items);
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Failed to load memory");
    } finally {
      setLoadingFacts(false);
    }
  }, [statusFilter, debouncedQuery]);

  useEffect(() => {
    reloadFacts();
  }, [reloadFacts]);

  const loadSettings = useCallback(async () => {
    setSettingsLoading(true);
    try {
      setSettings(await getMemorySettings());
    } catch (e) {
      console.error("Failed to load memory settings:", e);
    } finally {
      setSettingsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  async function handleUpdateSettings(patch: Partial<MemorySettings>) {
    const previous = settings;
    // Optimistic update — settings toggles should feel instant.
    if (previous) setSettings({ ...previous, ...patch });
    try {
      setSettings(await updateMemorySettings(patch));
    } catch (e) {
      if (previous) setSettings(previous);
      alert(e instanceof Error ? e.message : "Failed to update settings");
    }
  }

  async function handleCreateOrUpdate(values: FactFormValues) {
    if (editingFact) {
      const updated = await updateFact(editingFact.id, values);
      setFacts((prev) => prev.map((f) => (f.id === updated.id ? updated : f)));
    } else {
      const created = await createFact(values);
      setFacts((prev) => [created, ...prev]);
    }
  }

  async function handleDelete(fact: MemoryFact) {
    await deleteFact(fact.id);
    setFacts((prev) => prev.filter((f) => f.id !== fact.id));
  }

  async function handleTogglePin(fact: MemoryFact) {
    const updated = await pinFact(fact.id, !fact.pinned);
    setFacts((prev) => prev.map((f) => (f.id === updated.id ? updated : f)));
  }

  async function handleExport() {
    setExporting(true);
    try {
      const data = await exportMemory();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "contextuai-memory.json";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  // Pinned facts always float to the top, preserving relative order within
  // each group (the backend already does this for the non-search path).
  const orderedFacts = useMemo(() => {
    const pinned = facts.filter((f) => f.pinned);
    const rest = facts.filter((f) => !f.pinned);
    return [...pinned, ...rest];
  }, [facts]);

  const isSearching = debouncedQuery.length > 0;
  const noFactsAtAll =
    !loadingFacts && facts.length === 0 && !isSearching && statusFilter === "all";

  return (
    <div className="h-full overflow-y-auto bg-neutral-50 dark:bg-neutral-950">
      <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary-50 dark:bg-primary-500/10 flex items-center justify-center flex-shrink-0">
              <Brain className="w-5 h-5 text-primary-500" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-neutral-900 dark:text-white">
                Memory
              </h1>
              <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
                What Solo remembers about you and your work — you're in full
                control.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <span className="text-xs font-medium text-neutral-500 dark:text-neutral-400">
              Memory enabled
            </span>
            <Switch
              checked={settings?.enabled ?? false}
              onChange={(v) => handleUpdateSettings({ enabled: v })}
              disabled={settingsLoading || !settings}
            />
          </div>
        </div>

        {/* Kill-switch banner */}
        {settings && !settings.enabled && (
          <div className="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-neutral-100 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 text-sm text-neutral-600 dark:text-neutral-400">
            <ShieldOff className="w-4 h-4 flex-shrink-0" />
            Memory is off — nothing is being recalled.
          </div>
        )}

        {/* Toolbar */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400" />
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search memory…"
              className={cn(
                "w-full pl-9 pr-9 py-2.5 rounded-xl text-sm",
                "bg-white dark:bg-neutral-900",
                "border border-neutral-200 dark:border-neutral-700",
                "text-neutral-900 dark:text-white",
                "placeholder:text-neutral-400 dark:placeholder:text-neutral-500",
                "focus:outline-none focus:ring-2 focus:ring-primary-500/40 focus:border-primary-500",
              )}
            />
            {searchInput && (
              <button
                onClick={() => setSearchInput("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          <Button
            variant="secondary"
            size="md"
            onClick={handleExport}
            disabled={exporting}
          >
            {exporting ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Download className="w-3.5 h-3.5" />
            )}
            Export
          </Button>

          <Button
            size="md"
            onClick={() => {
              setEditingFact(null);
              setFormOpen(true);
            }}
          >
            <Plus className="w-3.5 h-3.5" />
            Add memory
          </Button>
        </div>

        {/* Filter chips */}
        <div className="flex items-center gap-2">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              onClick={() => setStatusFilter(f.id)}
              className={cn(
                "px-3 py-1.5 rounded-full text-xs font-medium transition-colors",
                statusFilter === f.id
                  ? "bg-primary-500 text-white"
                  : "bg-white dark:bg-neutral-900 text-neutral-600 dark:text-neutral-400 border border-neutral-200 dark:border-neutral-700 hover:bg-neutral-100 dark:hover:bg-neutral-800",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* Settings */}
        {settings && (
          <MemorySettingsCard settings={settings} onUpdate={handleUpdateSettings} />
        )}

        {/* Fact list */}
        <div>
          {loadingFacts && (
            <div className="flex items-center gap-2 px-1 py-6 text-sm text-neutral-500">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading…
            </div>
          )}

          {!loadingFacts && listError && (
            <p className="text-sm text-red-500 px-1 py-4">{listError}</p>
          )}

          {!loadingFacts && !listError && noFactsAtAll && (
            <div className="flex flex-col items-center justify-center text-center px-6 py-16 rounded-2xl border border-dashed border-neutral-300 dark:border-neutral-700">
              <Brain className="w-10 h-10 text-neutral-300 dark:text-neutral-700 mb-3" />
              <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                No memory yet
              </p>
              <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1 max-w-sm">
                Solo will start filling this in automatically as you chat.
                For now, you can add facts by hand — try something like
                "pricing is $49/mo".
              </p>
              <Button
                size="sm"
                className="mt-4"
                onClick={() => {
                  setEditingFact(null);
                  setFormOpen(true);
                }}
              >
                <Plus className="w-3.5 h-3.5" />
                Add memory
              </Button>
            </div>
          )}

          {!loadingFacts && !listError && !noFactsAtAll && facts.length === 0 && (
            <p className="text-sm text-neutral-500 dark:text-neutral-400 px-1 py-8 text-center">
              {isSearching
                ? "No matches. Try a different phrasing."
                : "No facts in this filter."}
            </p>
          )}

          {!loadingFacts && !listError && facts.length > 0 && (
            <ul className="rounded-xl border border-neutral-200 dark:border-neutral-800 divide-y divide-neutral-200 dark:divide-neutral-800 bg-white dark:bg-neutral-900">
              {orderedFacts.map((fact) => (
                <FactRow
                  key={fact.id}
                  fact={fact}
                  onEdit={() => {
                    setEditingFact(fact);
                    setFormOpen(true);
                  }}
                  onDelete={() => handleDelete(fact)}
                  onTogglePin={() => handleTogglePin(fact)}
                />
              ))}
            </ul>
          )}
        </div>
      </div>

      <FactFormModal
        open={formOpen}
        editingFact={editingFact}
        onClose={() => setFormOpen(false)}
        onSubmit={handleCreateOrUpdate}
      />
    </div>
  );
}
