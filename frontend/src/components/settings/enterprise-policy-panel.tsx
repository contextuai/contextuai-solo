import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  Building2,
  CheckCircle2,
  Loader2,
  Lock,
  Plane,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { Badge, Button, Input } from "@/components/ui";
import { Switch } from "@/components/ui/switch";
import {
  getEnterprisePolicy,
  syncEnterpriseCatalog,
  updateEnterprisePolicy,
  type CatalogSyncResult,
  type EnterprisePolicy,
  type EnterprisePolicyUpdate,
} from "@/lib/api/enterprise-client";

function PolicySourceBadge({ source }: { source: string }) {
  if (source === "env") {
    return (
      <Badge variant="info" dot>
        Environment Policy
      </Badge>
    );
  }
  if (source === "admin_policy") {
    return (
      <Badge variant="warning" dot>
        IT Admin Policy
      </Badge>
    );
  }
  if (source === "user_settings") {
    return (
      <Badge variant="success" dot>
        Custom Configured
      </Badge>
    );
  }
  return <Badge variant="default">Default</Badge>;
}

function LockedBadge() {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-500/30">
      <Lock className="w-3 h-3" />
      IT-Managed
    </span>
  );
}

export function EnterprisePolicyPanel() {
  const [policy, setPolicy] = useState<EnterprisePolicy | null>(null);
  const [catalogUrl, setCatalogUrl] = useState("");
  const [catalogExclusive, setCatalogExclusive] = useState(false);
  const [requireSha256, setRequireSha256] = useState(false);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<CatalogSyncResult | null>(null);

  const applyPolicy = useCallback((p: EnterprisePolicy) => {
    setPolicy(p);
    setCatalogUrl(p.catalog_url ?? "");
    setCatalogExclusive(p.catalog_exclusive);
    setRequireSha256(p.require_sha256);
  }, []);

  const loadPolicy = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getEnterprisePolicy();
      applyPolicy(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load enterprise policy"
      );
    } finally {
      setLoading(false);
    }
  }, [applyPolicy]);

  useEffect(() => {
    void loadPolicy();
  }, [loadPolicy]);

  const lockedSet = new Set(policy?.locked_fields ?? []);
  const urlLocked = lockedSet.has("catalog_url");
  const exclusiveLocked = lockedSet.has("catalog_exclusive");
  const shaLocked = lockedSet.has("require_sha256");
  const airplaneLocked =
    lockedSet.has("airplane_lock_enforced") ||
    Boolean(policy?.airplane_lock_enforced);

  const hasUnlockedChanges =
    !!policy &&
    ((!urlLocked && (catalogUrl.trim() || null) !== (policy.catalog_url ?? null)) ||
      (!exclusiveLocked && catalogExclusive !== policy.catalog_exclusive) ||
      (!shaLocked && requireSha256 !== policy.require_sha256));

  const handleSave = async () => {
    if (!policy) return;
    setSaving(true);
    setError(null);
    setSaveMessage(null);
    try {
      const patch: EnterprisePolicyUpdate = {};
      if (!urlLocked) {
        patch.catalog_url = catalogUrl.trim() || null;
      }
      if (!exclusiveLocked) {
        patch.catalog_exclusive = catalogExclusive;
      }
      if (!shaLocked) {
        patch.require_sha256 = requireSha256;
      }
      const updated = await updateEnterprisePolicy(patch);
      applyPolicy(updated);
      setSaveMessage("Enterprise policy settings saved.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to save enterprise policy"
      );
    } finally {
      setSaving(false);
    }
  };

  const handleSyncCatalog = async () => {
    setSyncing(true);
    setError(null);
    setSyncResult(null);
    try {
      // Save any pending unlocked URL / exclusive changes before syncing
      if (hasUnlockedChanges) {
        const patch: EnterprisePolicyUpdate = {};
        if (!urlLocked) patch.catalog_url = catalogUrl.trim() || null;
        if (!exclusiveLocked) patch.catalog_exclusive = catalogExclusive;
        if (!shaLocked) patch.require_sha256 = requireSha256;
        const updated = await updateEnterprisePolicy(patch);
        applyPolicy(updated);
      }
      const result = await syncEnterpriseCatalog();
      setSyncResult(result);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Catalog sync failed"
      );
    } finally {
      setSyncing(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-8 justify-center text-xs text-neutral-500">
        <Loader2 className="w-4 h-4 animate-spin text-primary-500" />
        Loading enterprise policy...
      </div>
    );
  }

  return (
    <div className="space-y-5" data-testid="enterprise-policy-panel">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-primary-50 dark:bg-primary-500/10 shrink-0">
            <Building2 className="w-5 h-5 text-primary-500" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-neutral-900 dark:text-white">
              Enterprise Model Catalog &amp; Integrity Policy
            </h3>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
              Override the model catalog with an internal mirror or local manifest, enforce SHA-256 verification, and inspect IT-locked controls.
            </p>
          </div>
        </div>
        {policy && <PolicySourceBadge source={policy.policy_source} />}
      </div>

      {policy?.policy_file && (
        <div className="flex items-center gap-2 px-3.5 py-2.5 rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50/60 dark:bg-amber-500/10 text-xs text-amber-800 dark:text-amber-200">
          <Lock className="w-3.5 h-3.5 shrink-0" />
          <span>
            Active admin policy file:{" "}
            <code className="font-mono">{policy.policy_file}</code>
          </span>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-xs text-red-700 dark:text-red-300">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {saveMessage && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 text-xs text-emerald-700 dark:text-emerald-300">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{saveMessage}</span>
        </div>
      )}

      {syncResult && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 text-xs text-emerald-700 dark:text-emerald-300">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>
            Synced {syncResult.merged_count} model(s) from{" "}
            <span className="font-semibold">{syncResult.source}</span> (total in
            catalog: {syncResult.total_catalog_models}).
          </span>
        </div>
      )}

      {/* Custom Catalog Source */}
      <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 space-y-4">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h4 className="text-sm font-semibold text-neutral-900 dark:text-white">
              Custom Model Catalog URL or Local File Path
            </h4>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
              Accepts <code className="font-mono">https://</code> mirror URLs,{" "}
              <code className="font-mono">file://</code> URIs, or local filesystem paths (works offline under Airplane Lock).
            </p>
          </div>
          {urlLocked && <LockedBadge />}
        </div>

        <Input
          value={catalogUrl}
          onChange={(e) => {
            setCatalogUrl(e.target.value);
            setSaveMessage(null);
          }}
          disabled={urlLocked || saving}
          placeholder="https://internal.corp/vesper/models.json or /etc/vesper/models.json"
          aria-label="Custom models.json URL or local file path"
        />

        {/* Exclusive Mode Toggle */}
        <div className="flex items-center justify-between gap-4 pt-3 border-t border-neutral-100 dark:border-neutral-800">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-neutral-900 dark:text-white">
                Exclusive Catalog Mode
              </span>
              {exclusiveLocked && <LockedBadge />}
            </div>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
              Hide built-in community models and expose only models approved in your enterprise catalog.
            </p>
          </div>
          <Switch
            checked={catalogExclusive}
            onChange={(checked) => {
              setCatalogExclusive(checked);
              setSaveMessage(null);
            }}
            disabled={exclusiveLocked || saving}
            label="Exclusive Catalog Mode"
          />
        </div>

        {/* Require SHA-256 Toggle */}
        <div className="flex items-center justify-between gap-4 pt-3 border-t border-neutral-100 dark:border-neutral-800">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0" />
              <span className="text-sm font-medium text-neutral-900 dark:text-white">
                Require SHA-256 Verification
              </span>
              {shaLocked && <LockedBadge />}
            </div>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
              Block loading or downloading any GGUF file that lacks a verified SHA-256 checksum or fails verification.
            </p>
          </div>
          <Switch
            checked={requireSha256}
            onChange={(checked) => {
              setRequireSha256(checked);
              setSaveMessage(null);
            }}
            disabled={shaLocked || saving}
            label="Require SHA-256 Verification"
          />
        </div>

        {/* Airplane Lock Policy Status */}
        <div className="flex items-center justify-between gap-4 pt-3 border-t border-neutral-100 dark:border-neutral-800">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Plane className="w-4 h-4 text-amber-500 shrink-0" />
              <span className="text-sm font-medium text-neutral-900 dark:text-white">
                Policy-Enforced Airplane Lock
              </span>
              {airplaneLocked && <LockedBadge />}
            </div>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
              {policy?.airplane_lock_enforced
                ? "Airplane Lock is enforced by IT policy and cannot be disabled by users."
                : "Not enforced by IT policy. Users may toggle Airplane Lock from the Privacy Shield."}
            </p>
          </div>
          <Badge variant={policy?.airplane_lock_enforced ? "warning" : "default"} dot>
            {policy?.airplane_lock_enforced ? "Enforced" : "Not Enforced"}
          </Badge>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-neutral-100 dark:border-neutral-800">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleSyncCatalog}
            disabled={syncing || saving}
          >
            {syncing ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RefreshCw className="w-3.5 h-3.5" />
            )}
            Sync Catalog Now
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={handleSave}
            disabled={saving || syncing || !hasUnlockedChanges}
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            Save Policy Settings
          </Button>
        </div>
      </div>
    </div>
  );
}
