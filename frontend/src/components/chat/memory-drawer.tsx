import { useState, useEffect, useCallback, useMemo } from "react";
import { Brain, X, Plus, Pin, PinOff, Trash2, Search, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button, Input } from "@/components/ui";
import { Switch } from "@/components/ui/switch";
import {
  listFacts,
  createFact,
  deleteFact,
  pinFact,
  getMemorySettings,
  updateMemorySettings,
  type MemoryFact,
  type MemorySettings,
} from "@/lib/api/memory-client";

export interface MemoryDrawerProps {
  open: boolean;
  onClose: () => void;
}

export function MemoryDrawer({ open, onClose }: MemoryDrawerProps) {
  const [facts, setFacts] = useState<MemoryFact[]>([]);
  const [settings, setSettings] = useState<MemorySettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);
  const [subject, setSubject] = useState("");
  const [predicate, setPredicate] = useState("");
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [factRows, memSettings] = await Promise.all([
        listFacts(),
        getMemorySettings().catch(() => null),
      ]);
      setFacts(factRows);
      if (memSettings) setSettings(memSettings);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load memory");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      void loadAll();
    }
  }, [open, loadAll]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  const filteredFacts = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const sorted = [...facts].sort((a, b) => Number(b.pinned) - Number(a.pinned));
    if (!q) return sorted;
    return sorted.filter(
      (f) =>
        f.text?.toLowerCase().includes(q) ||
        f.subject?.toLowerCase().includes(q) ||
        f.predicate?.toLowerCase().includes(q) ||
        f.value?.toLowerCase().includes(q)
    );
  }, [facts, searchQuery]);

  const handleToggleSetting = async (
    key: "enabled" | "chat_enabled",
    nextVal: boolean
  ) => {
    setSavingSettings(true);
    try {
      const updated = await updateMemorySettings({ [key]: nextVal });
      setSettings(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update settings");
    } finally {
      setSavingSettings(false);
    }
  };

  const handleCreateFact = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!subject.trim() || !predicate.trim() || !value.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await createFact({
        subject: subject.trim(),
        predicate: predicate.trim(),
        value: value.trim(),
        scope: "global",
      });
      setFacts((prev) => [created, ...prev]);
      setSubject("");
      setPredicate("");
      setValue("");
      setShowAddForm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save fact");
    } finally {
      setSubmitting(false);
    }
  };

  const handleTogglePin = async (fact: MemoryFact) => {
    try {
      const updated = await pinFact(fact.id, !fact.pinned);
      setFacts((prev) => prev.map((f) => (f.id === fact.id ? updated : f)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update pin");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      const ok = await deleteFact(id);
      if (ok) {
        setFacts((prev) => prev.filter((f) => f.id !== id));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete fact");
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Slide-over drawer */}
      <aside className="relative z-10 w-full max-w-md h-full bg-white dark:bg-neutral-900 border-l border-neutral-200 dark:border-neutral-800 shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-200 dark:border-neutral-800">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-primary-500/10 text-primary-600 dark:text-primary-400">
              <Brain className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-neutral-900 dark:text-white">
                Memory &amp; Recall
              </h2>
              <p className="text-[11px] text-neutral-500 dark:text-neutral-400">
                {facts.length} durable fact{facts.length === 1 ? "" : "s"} stored locally
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close Memory Drawer"
            className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Auto-recall toggles */}
        {settings && (
          <div className="px-5 py-3 bg-neutral-50/70 dark:bg-neutral-800/40 border-b border-neutral-200 dark:border-neutral-800 space-y-2.5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-neutral-800 dark:text-neutral-200">
                  Memory Enabled
                </div>
                <div className="text-[11px] text-neutral-500 dark:text-neutral-400">
                  Store and recall persistent facts across sessions
                </div>
              </div>
              <Switch
                size="sm"
                checked={settings.enabled}
                disabled={savingSettings}
                onChange={(next) => void handleToggleSetting("enabled", next)}
                label="Toggle Memory Enabled"
              />
            </div>

            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-neutral-800 dark:text-neutral-200">
                  Auto-Recall in Chat
                </div>
                <div className="text-[11px] text-neutral-500 dark:text-neutral-400">
                  Inject relevant facts into local &amp; cloud prompts
                </div>
              </div>
              <Switch
                size="sm"
                checked={settings.chat_enabled}
                disabled={savingSettings || !settings.enabled}
                onChange={(next) => void handleToggleSetting("chat_enabled", next)}
                label="Toggle Auto-Recall in Chat"
              />
            </div>
          </div>
        )}

        {/* Toolbar: search + add button */}
        <div className="px-5 py-3 border-b border-neutral-200 dark:border-neutral-800 space-y-2.5">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="w-3.5 h-3.5 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Filter saved facts..."
                className="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-500/30"
              />
            </div>
            <Button
              type="button"
              size="sm"
              variant={showAddForm ? "secondary" : "primary"}
              onClick={() => setShowAddForm((v) => !v)}
            >
              <Plus className="w-3.5 h-3.5" />
              Add
            </Button>
          </div>

          {showAddForm && (
            <form
              onSubmit={handleCreateFact}
              className="p-3 rounded-xl border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800/60 space-y-2"
            >
              <div className="grid grid-cols-2 gap-2">
                <Input
                  placeholder="Subject (e.g. User)"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  required
                />
                <Input
                  placeholder="Predicate (e.g. prefers)"
                  value={predicate}
                  onChange={(e) => setPredicate(e.target.value)}
                  required
                />
              </div>
              <Input
                placeholder="Value (e.g. concise TypeScript answers)"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                required
              />
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setShowAddForm(false)}
                >
                  Cancel
                </Button>
                <Button type="submit" size="sm" disabled={submitting}>
                  {submitting ? "Saving..." : "Save Fact"}
                </Button>
              </div>
            </form>
          )}
        </div>

        {/* Error banner */}
        {error && (
          <div className="mx-5 mt-3 px-3 py-2 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-xs text-red-700 dark:text-red-300">
            {error}
          </div>
        )}

        {/* Facts list */}
        <div className="flex-1 overflow-y-auto px-5 py-3 space-y-2">
          {loading ? (
            <div className="flex items-center justify-center py-10 text-xs text-neutral-500 gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading memory facts...
            </div>
          ) : filteredFacts.length === 0 ? (
            <div className="py-12 text-center text-xs text-neutral-500 dark:text-neutral-400">
              {searchQuery
                ? "No memory facts match your filter."
                : "No memory facts stored yet. Click Add to remember a preference or fact."}
            </div>
          ) : (
            filteredFacts.map((fact) => (
              <div
                key={fact.id}
                className={cn(
                  "p-3 rounded-xl border transition-colors",
                  fact.pinned
                    ? "border-primary-500/30 bg-primary-50/40 dark:bg-primary-500/5"
                    : "border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900"
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-neutral-900 dark:text-white leading-relaxed">
                      {fact.text || `${fact.subject} ${fact.predicate} ${fact.value}`}
                    </p>
                    <div className="flex items-center gap-2 mt-1.5 text-[10px] text-neutral-500 dark:text-neutral-400">
                      <span className="px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800">
                        {fact.scope}
                      </span>
                      {fact.pinned && (
                        <span className="text-primary-600 dark:text-primary-400 font-medium">
                          Pinned
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      type="button"
                      onClick={() => void handleTogglePin(fact)}
                      title={fact.pinned ? "Unpin fact" : "Pin fact"}
                      className="p-1.5 rounded-lg text-neutral-400 hover:text-primary-600 dark:hover:text-primary-400 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
                    >
                      {fact.pinned ? (
                        <PinOff className="w-3.5 h-3.5" />
                      ) : (
                        <Pin className="w-3.5 h-3.5" />
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDelete(fact.id)}
                      title="Delete fact"
                      className="p-1.5 rounded-lg text-neutral-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </aside>
    </div>
  );
}

export default MemoryDrawer;
