import { useState, useEffect, useCallback } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  Plus,
  Trash2,
  Play,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Terminal,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button, Input, Textarea, Badge } from "@/components/ui";
import { Switch } from "@/components/ui/switch";
import {
  getDlpSettings,
  updateDlpSettings,
  testDlpRedaction,
  type DlpCategoryKey,
  type DlpCustomRule,
  type DlpSettings,
  type DlpTestResponse,
} from "@/lib/api/dlp-client";

const CATEGORY_META: Array<{
  key: DlpCategoryKey;
  label: string;
  description: string;
}> = [
  {
    key: "api_keys",
    label: "API Keys & Private Keys",
    description:
      "OpenAI, Anthropic, AWS, GitHub, Slack, Google keys, PEM private keys, and Bearer/secret assignments",
  },
  {
    key: "emails",
    label: "Email Addresses",
    description: "Personal and corporate email addresses",
  },
  {
    key: "phones",
    label: "Phone Numbers",
    description:
      "US and international E.164 phone numbers (ignores ISO dates, semver, and UUIDs)",
  },
  {
    key: "ssns",
    label: "Social Security Numbers",
    description: "US SSN patterns (XXX-XX-XXXX)",
  },
  {
    key: "credit_cards",
    label: "Credit Card Numbers",
    description: "13–19 digit card numbers validated via Luhn checksum",
  },
  {
    key: "custom",
    label: "Custom Regex Rules",
    description: "Organization-specific patterns configured below",
  },
];

const SAMPLE_DRY_RUN_TEXT =
  "Deploy key sk-proj-abc1234567890xyz9876 for alice@acme.com on 2026-11-19. Call +1-415-555-0199.";

export function SecurityDlpPanel() {
  const [settings, setSettings] = useState<DlpSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Custom rule form state
  const [ruleName, setRuleName] = useState("");
  const [rulePattern, setRulePattern] = useState("");
  const [rulePlaceholder, setRulePlaceholder] = useState("[REDACTED:CUSTOM]");
  const [ruleError, setRuleError] = useState<string | null>(null);

  // Dry-run test box state
  const [testInput, setTestInput] = useState("");
  const [testing, setTesting] = useState(false);
  const [testError, setTestError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<DlpTestResponse | null>(null);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await getDlpSettings();
      setSettings(data);
    } catch (err) {
      setLoadError(
        err instanceof Error ? err.message : "Failed to load DLP settings"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  const applyUpdate = async (
    patch: Parameters<typeof updateDlpSettings>[0]
  ): Promise<boolean> => {
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await updateDlpSettings(patch);
      setSettings(updated);
      return true;
    } catch (err) {
      setSaveError(
        err instanceof Error ? err.message : "Failed to save DLP settings"
      );
      return false;
    } finally {
      setSaving(false);
    }
  };

  const handleToggleMaster = (next: boolean) => {
    void applyUpdate({ enabled: next });
  };

  const handleToggleRedactLogs = (next: boolean) => {
    void applyUpdate({ redact_logs: next });
  };

  const handleToggleCategory = (key: DlpCategoryKey, next: boolean) => {
    void applyUpdate({ categories: { [key]: next } });
  };

  const handlePatternChange = (val: string) => {
    setRulePattern(val);
    if (!val.trim()) {
      setRuleError(null);
      return;
    }
    try {
      new RegExp(val);
      setRuleError(null);
    } catch (err) {
      setRuleError(
        err instanceof Error ? `Invalid regex: ${err.message}` : "Invalid regex"
      );
    }
  };

  const handleAddRule = async () => {
    if (!settings) return;
    const trimmedName = ruleName.trim();
    const trimmedPattern = rulePattern;
    if (!trimmedName) {
      setRuleError("Rule name is required.");
      return;
    }
    if (!trimmedPattern) {
      setRuleError("Regex pattern is required.");
      return;
    }
    try {
      new RegExp(trimmedPattern);
    } catch (err) {
      setRuleError(
        err instanceof Error ? `Invalid regex: ${err.message}` : "Invalid regex"
      );
      return;
    }

    setRuleError(null);
    const newRule: DlpCustomRule = {
      id: `rule-${Date.now().toString(36)}`,
      name: trimmedName,
      pattern: trimmedPattern,
      placeholder: rulePlaceholder.trim() || "[REDACTED:CUSTOM]",
      enabled: true,
    };

    const nextRules = [...(settings.custom_rules || []), newRule];
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await updateDlpSettings({ custom_rules: nextRules });
      setSettings(updated);
      setRuleName("");
      setRulePattern("");
      setRulePlaceholder("[REDACTED:CUSTOM]");
    } catch (err) {
      setRuleError(
        err instanceof Error ? err.message : "Failed to add custom rule"
      );
    } finally {
      setSaving(false);
    }
  };

  const handleToggleCustomRule = (id: string, enabled: boolean) => {
    if (!settings) return;
    const nextRules = settings.custom_rules.map((r) =>
      r.id === id ? { ...r, enabled } : r
    );
    void applyUpdate({ custom_rules: nextRules });
  };

  const handleRemoveRule = (id: string) => {
    if (!settings) return;
    const nextRules = settings.custom_rules.filter((r) => r.id !== id);
    void applyUpdate({ custom_rules: nextRules });
  };

  const handleRunTest = async (inputOverride?: string) => {
    const text = inputOverride ?? testInput;
    setTesting(true);
    setTestError(null);
    try {
      const res = await testDlpRedaction(text);
      setTestResult(res);
    } catch (err) {
      setTestError(
        err instanceof Error ? err.message : "Dry-run DLP test failed"
      );
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 flex items-center gap-2 text-xs text-neutral-500">
        <Loader2 className="w-4 h-4 animate-spin" />
        Loading Local DLP settings...
      </div>
    );
  }

  if (loadError || !settings) {
    return (
      <div className="rounded-2xl border border-red-200 dark:border-red-500/30 bg-red-50/50 dark:bg-red-500/10 p-5 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs text-red-700 dark:text-red-300">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{loadError || "Unable to load DLP policy"}</span>
        </div>
        <Button variant="secondary" size="sm" onClick={() => void loadSettings()}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Master DLP & Log Redaction Card */}
      <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div
              className={cn(
                "w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0",
                settings.enabled
                  ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                  : "bg-amber-500/10 text-amber-600 dark:text-amber-400"
              )}
            >
              {settings.enabled ? (
                <ShieldCheck className="w-5 h-5" />
              ) : (
                <ShieldAlert className="w-5 h-5" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">
                  On-Device DLP & Secret Redaction
                </h3>
                <Badge variant={settings.enabled ? "success" : "warning"} dot>
                  {settings.enabled ? "Active" : "Paused"}
                </Badge>
              </div>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                Scans and redacts secrets and PII locally before messages leave
                your device to non-loopback cloud providers. Local GGUF and
                localhost models stay untouched.
              </p>
            </div>
          </div>
          <Switch
            checked={settings.enabled}
            onChange={handleToggleMaster}
            disabled={saving}
            label="Enable Local DLP"
          />
        </div>

        {saveError && (
          <div
            role="alert"
            className="flex items-center gap-2 px-3 py-2 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-xs text-red-700 dark:text-red-300"
          >
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{saveError}</span>
          </div>
        )}

        {/* Per-category toggles */}
        <div
          className={cn(
            "pt-3 border-t border-neutral-100 dark:border-neutral-800 space-y-2.5",
            !settings.enabled && "opacity-60"
          )}
        >
          <p className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
            Detection Categories
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
            {CATEGORY_META.map((cat) => (
              <div
                key={cat.key}
                className="flex items-start justify-between gap-3 p-3 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50/70 dark:bg-neutral-800/40"
              >
                <div className="min-w-0">
                  <p className="text-xs font-medium text-neutral-900 dark:text-white">
                    {cat.label}
                  </p>
                  <p className="text-[11px] text-neutral-500 dark:text-neutral-400 mt-0.5 leading-relaxed">
                    {cat.description}
                  </p>
                </div>
                <Switch
                  size="sm"
                  checked={!!settings.categories[cat.key]}
                  onChange={(next) => handleToggleCategory(cat.key, next)}
                  disabled={saving}
                  label={`Toggle ${cat.label}`}
                />
              </div>
            ))}
          </div>
        </div>

        {/* Local Log Redaction Toggle */}
        <div className="pt-3 border-t border-neutral-100 dark:border-neutral-800 flex items-center justify-between gap-4">
          <div className="flex items-start gap-2.5">
            <Terminal className="w-4 h-4 text-neutral-400 mt-0.5 flex-shrink-0" />
            <div>
              <p className="text-xs font-medium text-neutral-900 dark:text-white">
                Redact Local Application Logs
              </p>
              <p className="text-[11px] text-neutral-500 dark:text-neutral-400 mt-0.5">
                Scrub matched secrets and PII from local diagnostic logs via{" "}
                <code className="font-mono">DlpLogFilter</code> (off by default).
              </p>
            </div>
          </div>
          <Switch
            size="sm"
            checked={settings.redact_logs}
            onChange={handleToggleRedactLogs}
            disabled={saving}
            label="Redact local logs"
          />
        </div>
      </div>

      {/* Custom Regex Rules Card */}
      <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 space-y-4">
        <div>
          <h4 className="text-sm font-semibold text-neutral-900 dark:text-white">
            Custom Regex Rules
          </h4>
          <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
            Add organization-specific secret or identifier patterns (e.g.
            internal employee IDs, project codes, or proprietary tokens).
          </p>
        </div>

        {settings.custom_rules.length > 0 ? (
          <div className="space-y-2">
            {settings.custom_rules.map((rule) => (
              <div
                key={rule.id}
                className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50/70 dark:bg-neutral-800/40"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-medium text-neutral-900 dark:text-white">
                      {rule.name}
                    </span>
                    <Badge variant="default">{rule.placeholder}</Badge>
                  </div>
                  <p className="text-[11px] font-mono text-neutral-500 dark:text-neutral-400 truncate mt-0.5">
                    /{rule.pattern}/
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <Switch
                    size="sm"
                    checked={rule.enabled}
                    onChange={(next) => handleToggleCustomRule(rule.id, next)}
                    disabled={saving}
                    label={`Toggle rule ${rule.name}`}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => handleRemoveRule(rule.id)}
                    disabled={saving}
                    aria-label={`Remove rule ${rule.name}`}
                  >
                    <Trash2 className="w-3.5 h-3.5 text-neutral-500 hover:text-red-500" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-neutral-400 dark:text-neutral-500">
            No custom rules configured yet.
          </p>
        )}

        {/* Add Custom Rule Form */}
        <div className="pt-3 border-t border-neutral-100 dark:border-neutral-800 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
            <Input
              label="Rule Name"
              placeholder="e.g. Employee ID"
              value={ruleName}
              onChange={(e) => setRuleName(e.target.value)}
            />
            <Input
              label="Regex Pattern"
              placeholder="e.g. EMP-\d{6}"
              value={rulePattern}
              onChange={(e) => handlePatternChange(e.target.value)}
              error={ruleError || undefined}
              className="font-mono"
            />
            <Input
              label="Placeholder"
              placeholder="[REDACTED:CUSTOM]"
              value={rulePlaceholder}
              onChange={(e) => setRulePlaceholder(e.target.value)}
              className="font-mono"
            />
          </div>
          <div className="flex justify-end">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => void handleAddRule()}
              disabled={saving || !!ruleError}
            >
              <Plus className="w-3.5 h-3.5" />
              Add Custom Rule
            </Button>
          </div>
        </div>
      </div>

      {/* Live Dry-Run Test Box */}
      <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold text-neutral-900 dark:text-white">
              Live Dry-Run Redaction Tester
            </h4>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
              Test your active DLP rules locally without calling any cloud model.
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              setTestInput(SAMPLE_DRY_RUN_TEXT);
              void handleRunTest(SAMPLE_DRY_RUN_TEXT);
            }}
          >
            Insert Sample
          </Button>
        </div>

        <Textarea
          rows={3}
          placeholder="Paste text containing API keys, emails, phones, SSNs, cards, or custom patterns..."
          value={testInput}
          onChange={(e) => setTestInput(e.target.value)}
          className="font-mono text-xs"
        />

        <div className="flex items-center justify-between gap-3">
          <span className="text-[11px] text-neutral-400">
            Runs 100% locally via <code className="font-mono">/api/v1/dlp/test</code>
          </span>
          <Button
            type="button"
            variant="primary"
            size="sm"
            onClick={() => void handleRunTest()}
            disabled={testing}
          >
            {testing ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Play className="w-3.5 h-3.5" />
            )}
            Test Redaction
          </Button>
        </div>

        {testError && (
          <div
            role="alert"
            className="flex items-center gap-2 px-3 py-2 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-xs text-red-700 dark:text-red-300"
          >
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{testError}</span>
          </div>
        )}

        {testResult && (
          <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-800/50 p-3.5 space-y-2.5">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-2">
                {testResult.total_redactions > 0 ? (
                  <Badge variant="success" dot>
                    {testResult.total_redactions} redacted (
                    {testResult.categories.join(", ")})
                  </Badge>
                ) : (
                  <Badge variant="default">
                    <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                    Clean — 0 redactions
                  </Badge>
                )}
              </div>
              <div className="flex items-center gap-1.5 flex-wrap">
                {Object.entries(testResult.counts_by_category).map(
                  ([cat, count]) => (
                    <span
                      key={cat}
                      className="text-[11px] px-2 py-0.5 rounded-md bg-neutral-200/70 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-200 font-mono"
                    >
                      {cat}: {count}
                    </span>
                  )
                )}
              </div>
            </div>
            <pre className="text-xs font-mono text-neutral-800 dark:text-neutral-200 whitespace-pre-wrap break-words bg-white dark:bg-neutral-900 rounded-lg p-2.5 border border-neutral-200 dark:border-neutral-800">
              {testResult.redacted_text || "(empty)"}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
