import { useState, useEffect, useMemo } from "react";
import { cn } from "@/lib/utils";
import {
  Check,
  AlertTriangle,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Eye,
  EyeOff,
  Loader2,
  Trash2,
  AlertCircle,
} from "lucide-react";
import type { ProviderGuide } from "@/data/provider-guides";
import type {
  CloudProvider,
  TestResult,
} from "@/lib/api/cloud-providers-client";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ProviderCardProps {
  guide: ProviderGuide;
  /** Saved backend row, or undefined if not yet configured. */
  saved?: CloudProvider;
  /** providerType is the guide id string — parent narrows it further. */
  onSave: (providerType: string, config: Record<string, string>) => Promise<void>;
  onTest: (providerType: string, config: Record<string, string> | undefined) => Promise<TestResult>;
  onRemove: () => Promise<void>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const PROVIDER_COLORS: Record<string, string> = {
  anthropic: "#cd7f32",
  openai: "#10a37f",
  google: "#4285f4",
  bedrock: "#ff9900",
  ollama: "#7c3aed",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ProviderCard({ guide, saved, onSave, onTest, onRemove }: ProviderCardProps) {
  const isConnected = !!saved && saved.connected;

  // Collapsible: open by default if not connected, closed if connected
  const [stepsOpen, setStepsOpen] = useState(!isConnected);

  // Re-sync when connection status changes
  useEffect(() => {
    setStepsOpen(!isConnected);
  }, [isConnected]);

  // Per-field form state
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [showSecret, setShowSecret] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [showRemoveConfirm, setShowRemoveConfirm] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Reset form when saved row changes
  useEffect(() => {
    setFormData({});
    setTestResult(null);
    setSaveError(null);
  }, [saved?.provider_id, saved?.updated_at]);

  // Non-secret fields are prefilled from saved config
  const prefilledFromSaved = useMemo(() => {
    const vals: Record<string, string> = {};
    if (!saved) return vals;
    for (const f of guide.fields) {
      if (f.type !== "password") {
        const v = saved.config?.[f.key];
        if (v && v !== "***") vals[f.key] = v;
      }
    }
    return vals;
  }, [saved, guide.fields]);

  const valueOf = (key: string) => formData[key] ?? prefilledFromSaved[key] ?? "";

  const setField = (key: string, value: string) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
    setTestResult(null);
    setSaveError(null);
  };

  const buildConfig = (): Record<string, string> => {
    const cfg: Record<string, string> = {};
    for (const f of guide.fields) {
      const userVal = formData[f.key]?.trim();
      if (f.type === "password") {
        if (userVal) cfg[f.key] = userVal;
      } else {
        const v = userVal ?? prefilledFromSaved[f.key] ?? "";
        if (v) cfg[f.key] = v;
      }
    }
    return cfg;
  };

  // Can submit: required secret fields must be filled (unless already saved), required text fields always needed
  const canSubmit = useMemo(() => {
    for (const f of guide.fields) {
      if (!f.required) continue;
      const userVal = formData[f.key]?.trim();
      if (f.type === "password") {
        // For initial connect we need the key; for update it can be blank (keep existing)
        if (!isConnected && !userVal) return false;
      } else {
        const v = userVal ?? prefilledFromSaved[f.key] ?? "";
        if (!v.trim()) return false;
      }
    }
    return true;
  }, [formData, prefilledFromSaved, guide.fields, isConnected]);

  const canTest = isConnected || canSubmit;

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    setTestResult(null);
    try {
      await onSave(guide.id, buildConfig());
      setFormData({});
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setSaveError(null);
    setTestResult(null);
    try {
      const userTouched = Object.values(formData).some((v) => v.trim());
      const cfg = isConnected && !userTouched ? undefined : buildConfig();
      const result = await onTest(guide.id, cfg);
      setTestResult(result);
    } catch (err) {
      setTestResult({
        ok: false,
        latency_ms: 0,
        error: err instanceof Error ? err.message : "Test failed",
      });
    } finally {
      setTesting(false);
    }
  };

  const handleRemove = async () => {
    setRemoving(true);
    setSaveError(null);
    try {
      await onRemove();
      setFormData({});
      setTestResult(null);
      setShowRemoveConfirm(false);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to remove");
    } finally {
      setRemoving(false);
    }
  };

  const brandColor = PROVIDER_COLORS[guide.id] ?? "#888";

  return (
    <div
      data-testid={`provider-card-${guide.id}`}
      className={cn(
        "rounded-2xl border bg-white dark:bg-neutral-900 transition-all",
        isConnected
          ? "border-emerald-200 dark:border-emerald-800/50"
          : "border-neutral-200 dark:border-neutral-800",
      )}
    >
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-3 px-5 pt-5 pb-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <span
            className="w-2.5 h-2.5 rounded-full flex-shrink-0"
            style={{ backgroundColor: brandColor }}
          />
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-white truncate">
              {guide.name}
            </h3>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
              {guide.short_blurb}
            </p>
          </div>
        </div>

        {/* Status badge */}
        {isConnected ? (
          <span
            data-testid={`status-badge-${guide.id}`}
            className="flex items-center gap-1 flex-shrink-0 text-[10px] font-medium text-emerald-600 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-500/20 px-2 py-0.5 rounded-full"
          >
            <Check className="w-3 h-3" /> Key saved
          </span>
        ) : (
          <span
            data-testid={`status-badge-${guide.id}`}
            className="flex items-center gap-1 flex-shrink-0 text-[10px] font-medium text-amber-600 dark:text-amber-400 bg-amber-100 dark:bg-amber-500/20 px-2 py-0.5 rounded-full"
          >
            <AlertTriangle className="w-3 h-3" /> Not configured
          </span>
        )}
      </div>

      {/* ── Collapsible setup steps ─────────────────────────────────────── */}
      <div className="px-5 pb-3">
        <div className="border border-neutral-100 dark:border-neutral-800 rounded-xl overflow-hidden">
          {/* Toggle row */}
          <button
            type="button"
            onClick={() => setStepsOpen((prev) => !prev)}
            className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors"
            data-testid={`steps-toggle-${guide.id}`}
            aria-expanded={stepsOpen}
          >
            <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
              How to get your API key
            </span>
            <div className="flex items-center gap-2">
              <a
                href={guide.dashboard_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="inline-flex items-center gap-1 text-[11px] font-medium text-primary-600 dark:text-primary-400 hover:text-primary-500 transition-colors"
              >
                Open dashboard <ExternalLink className="w-3 h-3" />
              </a>
              {stepsOpen ? (
                <ChevronUp className="w-4 h-4 text-neutral-400" />
              ) : (
                <ChevronDown className="w-4 h-4 text-neutral-400" />
              )}
            </div>
          </button>

          {/* Steps list */}
          {stepsOpen && (
            <div
              className="px-4 pb-3 pt-1 border-t border-neutral-100 dark:border-neutral-800"
              data-testid={`steps-content-${guide.id}`}
            >
              <ol className="space-y-1.5">
                {guide.steps.map((step, idx) => (
                  <li
                    key={idx}
                    className="flex gap-2 text-xs text-neutral-600 dark:text-neutral-400 leading-relaxed"
                    data-testid={`step-${guide.id}-${idx}`}
                  >
                    <span className="flex-shrink-0 w-4 h-4 rounded-full bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400 text-[10px] font-medium flex items-center justify-center mt-0.5">
                      {idx + 1}
                    </span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      </div>

      {/* ── Form fields ─────────────────────────────────────────────────── */}
      <div className="px-5 pb-3 space-y-3">
        {guide.fields.map((field) => {
          const isSecret = field.type === "password";
          const show = showSecret[field.key] === true;
          const savedHasValue =
            isSecret && !!saved && !!saved.config?.[field.key] && !formData[field.key];
          const placeholder = savedHasValue
            ? "(saved — leave blank to keep)"
            : field.placeholder;

          return (
            <div key={field.key}>
              <label className="block text-[11px] font-medium text-neutral-600 dark:text-neutral-400 mb-1">
                {field.label}
                {field.required && <span className="text-red-500 ml-0.5">*</span>}
              </label>
              <div className="relative flex gap-2">
                <div className="relative flex-1">
                  <input
                    type={isSecret && !show ? "password" : "text"}
                    value={valueOf(field.key)}
                    onChange={(e) => setField(field.key, e.target.value)}
                    placeholder={placeholder}
                    spellCheck={false}
                    autoComplete="off"
                    data-testid={`field-${guide.id}-${field.key}`}
                    className={cn(
                      "w-full px-3 py-2 rounded-lg text-xs",
                      "bg-neutral-50 dark:bg-neutral-800",
                      "border border-neutral-200 dark:border-neutral-700",
                      "text-neutral-900 dark:text-white",
                      "placeholder:text-neutral-400 dark:placeholder:text-neutral-500",
                      "focus:outline-none focus:ring-2 focus:ring-primary-500/40 focus:border-primary-500",
                      "transition-all",
                      isSecret && "pr-9",
                    )}
                  />
                  {isSecret && (
                    <button
                      type="button"
                      tabIndex={-1}
                      onClick={() =>
                        setShowSecret((prev) => ({ ...prev, [field.key]: !prev[field.key] }))
                      }
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
                      title={show ? "Hide" : "Show"}
                    >
                      {show ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Feedback line ───────────────────────────────────────────────── */}
      <div className="px-5 pb-2 min-h-[20px]">
        {saveError && (
          <p className="text-[11px] text-red-600 dark:text-red-400 flex items-center gap-1">
            <AlertCircle className="w-3 h-3" /> {saveError}
          </p>
        )}
        {!saveError && testResult && (
          <p
            className={cn(
              "text-[11px] flex items-center gap-1",
              testResult.ok
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-red-600 dark:text-red-400",
            )}
          >
            {testResult.ok ? (
              <>
                <Check className="w-3 h-3" /> Test passed
                <span className="text-neutral-400 dark:text-neutral-500 ml-1">
                  ({testResult.latency_ms}ms)
                </span>
              </>
            ) : (
              <>
                <AlertCircle className="w-3 h-3" />
                {testResult.error ?? "Test failed"}
              </>
            )}
          </p>
        )}
      </div>

      {/* ── Cost copy ───────────────────────────────────────────────────── */}
      <div className="px-5 pb-3">
        <p className="text-[11px] text-neutral-400 dark:text-neutral-500 leading-relaxed">
          <span className="font-medium text-neutral-500 dark:text-neutral-400">Cost: </span>
          {guide.cost_copy}
        </p>
      </div>

      {/* ── Footer actions ──────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 px-5 pb-5">
        <button
          type="button"
          onClick={handleTest}
          disabled={testing || saving || !canTest}
          data-testid={`test-btn-${guide.id}`}
          className={cn(
            "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
            "border border-neutral-200 dark:border-neutral-700",
            "text-neutral-700 dark:text-neutral-300",
            "hover:bg-neutral-50 dark:hover:bg-neutral-800",
            "disabled:opacity-50 disabled:cursor-not-allowed",
          )}
        >
          {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
          Test
        </button>

        <button
          type="button"
          onClick={handleSave}
          disabled={saving || testing || !canSubmit}
          data-testid={`save-btn-${guide.id}`}
          className={cn(
            "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
            "bg-primary-500 text-white hover:bg-primary-600",
            "disabled:opacity-50 disabled:cursor-not-allowed",
          )}
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
          {isConnected ? "Update" : "Save"}
        </button>

        {/* Remove key */}
        {isConnected && !showRemoveConfirm && (
          <button
            type="button"
            onClick={() => setShowRemoveConfirm(true)}
            data-testid={`remove-btn-${guide.id}`}
            className={cn(
              "inline-flex items-center gap-1.5 ml-auto px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
              "border border-red-200 dark:border-red-800",
              "text-red-600 dark:text-red-400",
              "hover:bg-red-50 dark:hover:bg-red-500/10",
            )}
          >
            <Trash2 className="w-3.5 h-3.5" /> Remove key
          </button>
        )}

        {/* Confirm remove */}
        {showRemoveConfirm && (
          <div className="ml-auto flex items-center gap-1.5">
            <span className="text-[11px] text-neutral-500 dark:text-neutral-400">Remove key?</span>
            <button
              type="button"
              onClick={() => setShowRemoveConfirm(false)}
              className="text-[11px] px-2 py-1 rounded-lg border border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleRemove}
              disabled={removing}
              data-testid={`confirm-remove-btn-${guide.id}`}
              className={cn(
                "text-[11px] px-2 py-1 rounded-lg transition-colors",
                "bg-red-500 text-white hover:bg-red-600",
                "disabled:opacity-50 disabled:cursor-not-allowed",
              )}
            >
              {removing ? <Loader2 className="w-3 h-3 animate-spin" /> : "Confirm"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
