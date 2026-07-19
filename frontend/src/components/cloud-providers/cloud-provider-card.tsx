import { useState, useEffect, useMemo } from "react";
import { cn } from "@/lib/utils";
import {
  Check,
  ExternalLink,
  Loader2,
  Eye,
  EyeOff,
  AlertCircle,
  Trash2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import type {
  CloudProvider,
  CloudProviderType,
  TestResult,
} from "@/lib/api/cloud-providers-client";

// ---------------------------------------------------------------------------
// Catalog field type (mirrored in cloud-providers-tab.tsx)
// ---------------------------------------------------------------------------

export interface CatalogField {
  key: string;
  label: string;
  placeholder?: string;
  secret: boolean;
}

export interface CatalogProvider {
  type: CloudProviderType;
  name: string;
  tagline: string;
  portalUrl: string;
  portalLabel: string;
  brand: string;
  fields: readonly CatalogField[];
}

// ---------------------------------------------------------------------------
// Card props
// ---------------------------------------------------------------------------

interface CloudProviderCardProps {
  provider: CatalogProvider;
  saved?: CloudProvider;
  onConnect: (input: {
    provider_type: CloudProviderType;
    display_name?: string;
    config: Record<string, string>;
  }) => Promise<void>;
  onDisconnect: () => Promise<void>;
  /**
   * If `saved` exists, called with no args (parent should call the saved-test
   * endpoint). If not saved, called with the freshly-built config so the
   * parent can hit the unsaved-test endpoint.
   */
  onTest: (config?: Record<string, string>) => Promise<TestResult>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MASKED_VALUE = "***";

function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diff = Math.max(0, now - then);
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const days = Math.floor(hr / 24);
  return `${days}d ago`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CloudProviderCard({
  provider,
  saved,
  onConnect,
  onDisconnect,
  onTest,
}: CloudProviderCardProps) {
  const isConnected = !!saved && saved.connected;

  // Collapsed by default once connected; expanded when first setting up.
  // Mirrors the Distributions card pattern in routes/connections.tsx.
  const [isExpanded, setIsExpanded] = useState(!isConnected);

  // Local form state — initialised empty; saved secrets show "(saved)" placeholder
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [showSecret, setShowSecret] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Reset form whenever the saved row changes (e.g. after refetch)
  useEffect(() => {
    setFormData({});
    setTestResult(null);
    setError(null);
  }, [saved?.provider_id, saved?.updated_at]);

  // Are non-secret fields prefilled from saved config?
  const prefilledFromSaved = useMemo(() => {
    const vals: Record<string, string> = {};
    if (!saved) return vals;
    for (const f of provider.fields) {
      const v = saved.config?.[f.key];
      if (!f.secret && v && v !== MASKED_VALUE) {
        vals[f.key] = v;
      }
    }
    return vals;
  }, [saved, provider.fields]);

  // Current value for a field — formData wins over prefilled
  const valueOf = (key: string) => formData[key] ?? prefilledFromSaved[key] ?? "";

  const setField = (key: string, value: string) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
    setTestResult(null);
    setError(null);
  };

  const buildConfig = (): Record<string, string> => {
    // Merge: prefilled (from saved) + any user-entered values.
    // For secrets: only include if user typed something (otherwise backend keeps existing).
    const cfg: Record<string, string> = {};
    for (const f of provider.fields) {
      const userVal = formData[f.key]?.trim();
      if (f.secret) {
        if (userVal) cfg[f.key] = userVal;
      } else {
        const v = userVal ?? prefilledFromSaved[f.key] ?? "";
        if (v) cfg[f.key] = v;
      }
    }
    return cfg;
  };

  // For initial connect: require all secrets + non-secrets.
  // For update: secrets are optional (existing one is kept).
  const canSubmit = useMemo(() => {
    for (const f of provider.fields) {
      const userVal = formData[f.key]?.trim();
      if (f.secret) {
        if (!isConnected && !userVal) return false;
      } else {
        const v = userVal ?? prefilledFromSaved[f.key] ?? "";
        if (!v.trim()) return false;
      }
    }
    return true;
  }, [formData, prefilledFromSaved, provider.fields, isConnected]);

  // Test requires either freshly typed creds OR an existing saved provider.
  const canTest = useMemo(() => {
    if (isConnected) return true;
    return canSubmit;
  }, [isConnected, canSubmit]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setTestResult(null);
    try {
      await onConnect({
        provider_type: provider.type,
        display_name: provider.name,
        config: buildConfig(),
      });
      setFormData({});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setError(null);
    setTestResult(null);
    try {
      // If a row is already saved AND the user hasn't typed any new values, hit
      // the saved-provider endpoint so the test persists `connected`. (Gating on
      // `isConnected` here created a chicken-and-egg: a saved-but-not-yet-
      // connected provider could never flip to connected.) Otherwise build a
      // fresh config (covers first-time-test and update flows).
      const userTouched = Object.values(formData).some((v) => v.trim());
      const cfg = !!saved && !userTouched ? undefined : buildConfig();
      const result = await onTest(cfg);
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

  const handleDisconnect = async () => {
    if (!confirm(`Disconnect ${provider.name}? You'll need to re-enter credentials to reconnect.`)) {
      return;
    }
    setDisconnecting(true);
    setError(null);
    try {
      await onDisconnect();
      setFormData({});
      setTestResult(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to disconnect");
    } finally {
      setDisconnecting(false);
    }
  };

  // Last-test status from saved row (server-side)
  const savedTestStatus = saved?.last_test_status;
  const savedTestError = saved?.last_test_error;
  const lastTestedRel = relativeTime(saved?.last_tested_at ?? null);

  return (
    <div
      className={cn(
        "flex flex-col rounded-2xl border bg-white dark:bg-neutral-900 transition-all",
        isConnected
          ? "border-green-200 dark:border-green-800/50"
          : "border-neutral-200 dark:border-neutral-800",
      )}
    >
      {/* Header */}
      <button
        type="button"
        onClick={() => setIsExpanded((v) => !v)}
        className="px-5 pt-5 pb-3 text-left w-full hover:bg-neutral-50/50 dark:hover:bg-neutral-800/40 transition-colors rounded-t-2xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span
              className="w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: provider.brand }}
            />
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">
              {provider.name}
            </h3>
            {isConnected && (
              <span className="flex items-center gap-1 text-[10px] font-medium text-green-600 dark:text-green-400 bg-green-100 dark:bg-green-500/20 px-2 py-0.5 rounded-full">
                <Check className="w-3 h-3" /> Connected
              </span>
            )}
          </div>
          <span className="flex items-center gap-1 text-[11px] font-medium text-neutral-500 dark:text-neutral-400 shrink-0">
            {isConnected ? (isExpanded ? "Hide" : "Update") : (isExpanded ? "Hide" : "Configure")}
            {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </span>
        </div>
        <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1.5">
          {provider.tagline}
        </p>
      </button>

      {/* Collapsed summary — last-tested line when connected and panel is hidden */}
      {!isExpanded && isConnected && savedTestStatus && (
        <div className="px-5 pb-4">
          <p
            className={cn(
              "text-[11px] flex items-center gap-1",
              savedTestStatus === "ok"
                ? "text-neutral-500 dark:text-neutral-400"
                : "text-red-600 dark:text-red-400",
            )}
          >
            {savedTestStatus === "ok" ? (
              <>
                <Check className="w-3 h-3 text-green-500" /> Last tested {lastTestedRel}
              </>
            ) : (
              <>
                <AlertCircle className="w-3 h-3" />
                Last test failed {lastTestedRel}
              </>
            )}
          </p>
        </div>
      )}

      {/* Expanded body */}
      {isExpanded && (
      <>
      {/* Get-key link + steps */}
      <div className="px-5 pb-3">
        <a
          href={provider.portalUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[11px] font-medium text-primary-600 dark:text-primary-400 hover:text-primary-500 underline underline-offset-2"
        >
          Get API key
          <ExternalLink className="w-3 h-3" />
        </a>
        <ol className="mt-2 space-y-0.5 text-[11px] text-neutral-500 dark:text-neutral-400 leading-snug">
          <li>1. Sign in to {provider.portalLabel}</li>
          <li>2. Create API key</li>
          <li>3. Paste below</li>
        </ol>
      </div>

      {/* Fields */}
      <div className="px-5 pb-3 space-y-3">
        {provider.fields.map((field) => {
          const isSecret = field.secret;
          const show = showSecret[field.key] === true;
          const savedHasValue =
            isSecret &&
            !!saved &&
            !!saved.config?.[field.key] &&
            !formData[field.key];
          const placeholder = savedHasValue
            ? "(saved — leave blank to keep)"
            : field.placeholder ?? "";

          return (
            <div key={field.key}>
              <label className="block text-[11px] font-medium text-neutral-600 dark:text-neutral-400 mb-1">
                {field.label}
              </label>
              <div className="relative">
                <input
                  type={isSecret && !show ? "password" : "text"}
                  value={valueOf(field.key)}
                  onChange={(e) => setField(field.key, e.target.value)}
                  placeholder={placeholder}
                  spellCheck={false}
                  autoComplete="off"
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
                      setShowSecret((prev) => ({
                        ...prev,
                        [field.key]: !prev[field.key],
                      }))
                    }
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
                    title={show ? "Hide" : "Show"}
                  >
                    {show ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Test result line / error line / saved status */}
      <div className="px-5 pb-3 min-h-[20px]">
        {error && (
          <p className="text-[11px] text-red-600 dark:text-red-400 flex items-center gap-1">
            <AlertCircle className="w-3 h-3" /> {error}
          </p>
        )}
        {!error && testResult && (
          <p
            className={cn(
              "text-[11px] flex items-center gap-1",
              testResult.ok
                ? "text-green-600 dark:text-green-400"
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
                {testResult.error || "Test failed"}
              </>
            )}
          </p>
        )}
        {!error && !testResult && saved && savedTestStatus && (
          <p
            className={cn(
              "text-[11px] flex items-center gap-1",
              savedTestStatus === "ok"
                ? "text-neutral-500 dark:text-neutral-400"
                : "text-red-600 dark:text-red-400",
            )}
          >
            {savedTestStatus === "ok" ? (
              <>
                <Check className="w-3 h-3 text-green-500" /> Last tested {lastTestedRel}
                <span className="text-neutral-400 ml-1">— OK</span>
              </>
            ) : (
              <>
                <AlertCircle className="w-3 h-3" />
                Last test failed {lastTestedRel}
                {savedTestError && (
                  <span className="text-neutral-400 ml-1 truncate">
                    — {savedTestError}
                  </span>
                )}
              </>
            )}
          </p>
        )}
      </div>

      {/* Footer actions */}
      <div className="flex items-center gap-2 px-5 pb-5 mt-auto">
        <button
          type="button"
          onClick={handleTest}
          disabled={testing || saving || !canTest}
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
          className={cn(
            "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
            "bg-primary-500 text-white hover:bg-primary-600",
            "disabled:opacity-50 disabled:cursor-not-allowed",
          )}
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
          {isConnected ? "Update" : "Save"}
        </button>
        {isConnected && (
          <button
            type="button"
            onClick={handleDisconnect}
            disabled={disconnecting || saving || testing}
            className={cn(
              "inline-flex items-center gap-1.5 ml-auto px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
              "border border-red-200 dark:border-red-800",
              "text-red-600 dark:text-red-400",
              "hover:bg-red-50 dark:hover:bg-red-500/10",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            )}
          >
            {disconnecting ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Trash2 className="w-3.5 h-3.5" />
            )}
            Disconnect
          </button>
        )}
      </div>
      </>
      )}
    </div>
  );
}
