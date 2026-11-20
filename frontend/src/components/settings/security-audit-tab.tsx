import { useState, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import { Badge, Button, M3Card, M3StatTile } from "@/components/ui";
import {
  listAuditEvents,
  getAbom,
  downloadAuditExport,
  type AuditEvent,
  type AbomReport,
} from "@/lib/api/audit-client";
import {
  ShieldCheck,
  Plane,
  Cpu,
  Download,
  FileSpreadsheet,
  RefreshCw,
  Copy,
  Check,
  Lock,
  Activity,
  AlertCircle,
  Loader2,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

type CategoryFilterId = "all" | "models" | "privacy" | "dlp" | "tools";

const CATEGORY_FILTERS: {
  id: CategoryFilterId;
  label: string;
  actionPrefix?: string;
}[] = [
  { id: "all", label: "All" },
  { id: "models", label: "Models", actionPrefix: "model.*" },
  { id: "privacy", label: "Privacy", actionPrefix: "privacy.*" },
  { id: "dlp", label: "DLP", actionPrefix: "dlp.*" },
  { id: "tools", label: "Tools", actionPrefix: "tool.*" },
];

const SEVERITY_BADGE_MAP: Record<
  string,
  "info" | "warning" | "error" | "default"
> = {
  info: "info",
  warning: "warning",
  error: "error",
  critical: "error",
};

const PAGE_SIZE = 20;

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function truncateHash(hash?: string): string {
  if (!hash) return "—";
  if (hash.length <= 20) return hash;
  return `${hash.slice(0, 12)}…${hash.slice(-8)}`;
}

export function SecurityAuditTab() {
  const [abom, setAbom] = useState<AbomReport | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [totalEvents, setTotalEvents] = useState(0);
  const [page, setPage] = useState(1);
  const [category, setCategory] = useState<CategoryFilterId>("all");
  const [severityFilter, setSeverityFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [exportingFormat, setExportingFormat] = useState<"json" | "csv" | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [exportNotice, setExportNotice] = useState<string | null>(null);
  const [copiedSha, setCopiedSha] = useState<string | null>(null);
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null);

  const activeFilter = CATEGORY_FILTERS.find((f) => f.id === category);

  const loadData = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!opts?.silent) setLoading(true);
      else setRefreshing(true);

      try {
        const [abomData, eventsData] = await Promise.all([
          getAbom(),
          listAuditEvents({
            action: activeFilter?.actionPrefix,
            severity: severityFilter || undefined,
            page,
            page_size: PAGE_SIZE,
          }),
        ]);
        setAbom(abomData);
        setEvents(eventsData.events || []);
        setTotalEvents(eventsData.total ?? 0);
        setError(null);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to load audit log & ABOM report",
        );
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [activeFilter?.actionPrefix, severityFilter, page],
  );

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleExport = async (format: "json" | "csv") => {
    setExportingFormat(format);
    setExportNotice(null);
    setError(null);
    try {
      const filename = await downloadAuditExport(format);
      setExportNotice(`Downloaded ${filename}`);
      await loadData({ silent: true });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : `Failed to export ${format}`,
      );
    } finally {
      setExportingFormat(null);
    }
  };

  const handleCopySha = async (sha: string) => {
    try {
      await navigator.clipboard.writeText(sha);
      setCopiedSha(sha);
      setTimeout(() => {
        setCopiedSha((prev) => (prev === sha ? null : prev));
      }, 1800);
    } catch {
      // clipboard unavailable
    }
  };

  const totalPages = Math.max(1, Math.ceil(totalEvents / PAGE_SIZE));
  const airplaneLocked = Boolean(abom?.privacy_posture?.airplane_lock);
  const policyLocked = Boolean(abom?.privacy_posture?.policy_locked);
  const externalCount =
    abom?.privacy_posture?.total_allowed_requests ??
    abom?.privacy_posture?.external_connections_count ??
    0;
  const installedModels = abom?.installed_models ?? [];
  const auditTotal = abom?.audit_summary?.total ?? totalEvents;
  const bySeverity = abom?.audit_summary?.by_severity ?? {};
  const warnAndErrorCount =
    (bySeverity.warning ?? 0) +
    (bySeverity.error ?? 0) +
    (bySeverity.critical ?? 0);

  return (
    <div className="space-y-6">
      {/* Header & Export Actions */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-neutral-900 dark:text-white flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-primary-500" />
            Security Audit Log &amp; ABOM
          </h3>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Local SQLite audit trail, verifiable AI Bill of Materials (ABOM), and
            SHA-256 model inventory.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void loadData({ silent: true })}
            disabled={loading || refreshing}
          >
            <RefreshCw
              className={cn("w-3.5 h-3.5", refreshing && "animate-spin")}
            />
            Refresh
          </Button>
          <Button
            variant="tonal"
            size="sm"
            onClick={() => void handleExport("json")}
            disabled={exportingFormat !== null}
          >
            {exportingFormat === "json" ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Download className="w-3.5 h-3.5" />
            )}
            Export JSON (ABOM + Audit)
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void handleExport("csv")}
            disabled={exportingFormat !== null}
          >
            {exportingFormat === "csv" ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <FileSpreadsheet className="w-3.5 h-3.5" />
            )}
            Export CSV
          </Button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-800/50 text-xs text-red-600 dark:text-red-400">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {exportNotice && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-800/50 text-xs text-emerald-700 dark:text-emerald-300">
          <Check className="w-4 h-4 shrink-0" />
          <span>{exportNotice}</span>
        </div>
      )}

      {/* ABOM Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <M3StatTile
          label="Installed Models (SHA-256)"
          value={`${installedModels.length} ${installedModels.length === 1 ? "model" : "models"}`}
          sublabel={
            abom?.active_model?.loaded
              ? `Active: ${abom.active_model.model_id || "local model"}`
              : "No active GGUF loaded in memory"
          }
          icon={<Cpu className="w-4 h-4" />}
        />

        <M3StatTile
          label="Airplane Lock Posture"
          value={
            <div className="flex items-center gap-2 flex-wrap">
              <span>{airplaneLocked ? "Active (Zero-Egress)" : "Off"}</span>
              {policyLocked && (
                <Badge variant="warning">
                  <Lock className="w-3 h-3" />
                  IT Policy
                </Badge>
              )}
            </div>
          }
          sublabel={`${externalCount} external request${externalCount === 1 ? "" : "s"} in session`}
          icon={<Plane className="w-4 h-4" />}
          accent={airplaneLocked}
        />

        <M3StatTile
          label="Audit Event Totals"
          value={auditTotal.toLocaleString()}
          sublabel={
            warnAndErrorCount > 0
              ? `${warnAndErrorCount} warning / error / critical`
              : "All recorded events healthy"
          }
          icon={<Activity className="w-4 h-4" />}
        />
      </div>

      {/* Installed Models & SHA-256 Inventory */}
      <M3Card className="p-5 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h4 className="text-sm font-semibold text-neutral-900 dark:text-white">
              ABOM Model Integrity Inventory
            </h4>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
              {abom
                ? `${abom.app_name} v${abom.app_version} · Snapshot generated ${formatTimestamp(abom.generated_at)}`
                : "Loading ABOM snapshot…"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={abom?.dlp_posture?.enabled ? "success" : "default"} dot>
              DLP: {abom?.dlp_posture?.enabled ? "Enabled" : "Off"}
            </Badge>
            {abom?.catalog_policy?.require_sha256 && (
              <Badge variant="info">SHA-256 Enforced</Badge>
            )}
          </div>
        </div>

        {installedModels.length === 0 ? (
          <div className="py-5 text-center rounded-xl border border-dashed border-neutral-200 dark:border-neutral-800 text-xs text-neutral-500 dark:text-neutral-400">
            No local GGUF models installed in the models directory yet.
          </div>
        ) : (
          <div className="divide-y divide-neutral-100 dark:divide-neutral-800 rounded-xl border border-neutral-200/80 dark:border-neutral-800 overflow-hidden">
            {installedModels.map((model) => (
              <div
                key={model.path || model.id}
                className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 bg-white/60 dark:bg-neutral-900/50 text-xs"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-neutral-900 dark:text-white">
                      {model.name || model.filename}
                    </span>
                    {model.parameter_size && (
                      <span className="text-neutral-500 dark:text-neutral-400">
                        ({model.parameter_size})
                      </span>
                    )}
                    {model.size_gb != null && (
                      <span className="text-neutral-400">
                        {model.size_gb} GB
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-neutral-500 dark:text-neutral-400 font-mono truncate mt-0.5">
                    {model.filename}
                  </p>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {model.integrity_verified === true && (
                    <Badge variant="success" dot>
                      Verified
                    </Badge>
                  )}
                  {model.integrity_verified === false && (
                    <Badge variant="error" dot>
                      Hash Mismatch
                    </Badge>
                  )}
                  <code
                    title={
                      model.sha256 ||
                      (model.hash_status === "computing"
                        ? "Computing SHA-256 in background…"
                        : "Unavailable")
                    }
                    className="px-2 py-1 rounded-lg bg-neutral-100 dark:bg-neutral-800 font-mono text-[11px] text-neutral-700 dark:text-neutral-300"
                  >
                    {!model.sha256 && model.hash_status === "computing"
                      ? "Hashing…"
                      : truncateHash(model.sha256)}
                  </code>
                  {model.sha256 && (
                    <button
                      type="button"
                      onClick={() => void handleCopySha(model.sha256!)}
                      className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
                      title="Copy full SHA-256"
                    >
                      {copiedSha === model.sha256 ? (
                        <Check className="w-3.5 h-3.5 text-emerald-500" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </M3Card>

      {/* Audit Event Table + Filters */}
      <M3Card className="p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* Category Filter Pills */}
          <div className="flex flex-wrap items-center gap-1.5">
            {CATEGORY_FILTERS.map((item) => {
              const active = category === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    setCategory(item.id);
                    setPage(1);
                  }}
                  className={cn(
                    "px-3 py-1.5 rounded-xl text-xs font-medium transition-all",
                    active
                      ? "bg-primary-500 text-white shadow-sm"
                      : "bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-700",
                  )}
                >
                  {item.label}
                </button>
              );
            })}
          </div>

          {/* Severity Filter */}
          <div className="flex items-center gap-2">
            <label
              htmlFor="audit-severity-filter"
              className="text-xs text-neutral-500 dark:text-neutral-400"
            >
              Severity:
            </label>
            <select
              id="audit-severity-filter"
              value={severityFilter}
              onChange={(e) => {
                setSeverityFilter(e.target.value);
                setPage(1);
              }}
              className="px-3 py-1.5 rounded-xl text-xs bg-neutral-50 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 text-neutral-800 dark:text-neutral-200 focus:outline-none focus:ring-2 focus:ring-primary-500/40"
            >
              <option value="">All severities</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="error">Error</option>
              <option value="critical">Critical</option>
            </select>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12 text-xs text-neutral-500">
            <Loader2 className="w-5 h-5 animate-spin mr-2 text-primary-500" />
            Loading audit events...
          </div>
        ) : events.length === 0 ? (
          <div className="text-center py-10 rounded-xl border border-dashed border-neutral-200 dark:border-neutral-800 text-xs text-neutral-500 dark:text-neutral-400">
            No audit events match the selected filters.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-neutral-200 dark:border-neutral-800">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-neutral-50 dark:bg-neutral-800/70 text-neutral-500 dark:text-neutral-400 border-b border-neutral-200 dark:border-neutral-800">
                  <th className="py-2.5 px-3 font-medium">Timestamp</th>
                  <th className="py-2.5 px-3 font-medium">Action</th>
                  <th className="py-2.5 px-3 font-medium">Severity</th>
                  <th className="py-2.5 px-3 font-medium">Resource</th>
                  <th className="py-2.5 px-3 font-medium">Airplane Lock</th>
                  <th className="py-2.5 px-3 font-medium">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                {events.map((ev) => {
                  const isExpanded = expandedEventId === ev.id;
                  const detailsText = ev.details
                    ? JSON.stringify(ev.details)
                    : "—";
                  return (
                    <tr
                      key={ev.id}
                      onClick={() =>
                        setExpandedEventId(isExpanded ? null : ev.id)
                      }
                      className="hover:bg-neutral-50/80 dark:hover:bg-neutral-800/40 cursor-pointer transition-colors"
                    >
                      <td className="py-2.5 px-3 whitespace-nowrap text-neutral-500 dark:text-neutral-400">
                        {formatTimestamp(ev.timestamp)}
                      </td>
                      <td className="py-2.5 px-3 whitespace-nowrap">
                        <code className="px-2 py-0.5 rounded-md bg-neutral-100 dark:bg-neutral-800 font-mono text-[11px] text-neutral-800 dark:text-neutral-200">
                          {ev.action}
                        </code>
                      </td>
                      <td className="py-2.5 px-3 whitespace-nowrap">
                        <Badge
                          variant={SEVERITY_BADGE_MAP[ev.severity] ?? "default"}
                          dot
                        >
                          {ev.severity}
                        </Badge>
                      </td>
                      <td className="py-2.5 px-3 text-neutral-700 dark:text-neutral-300 max-w-[180px] truncate">
                        {ev.resource_type || ev.resource_id
                          ? `${ev.resource_type ?? "resource"}: ${ev.resource_id ?? "—"}`
                          : "—"}
                      </td>
                      <td className="py-2.5 px-3 whitespace-nowrap">
                        {ev.airplane_lock ? (
                          <Badge variant="warning">Locked</Badge>
                        ) : (
                          <span className="text-neutral-400">Off</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 font-mono text-[11px] text-neutral-500 dark:text-neutral-400 max-w-[260px]">
                        <div className={isExpanded ? "whitespace-pre-wrap break-all" : "truncate"}>
                          {isExpanded && ev.details
                            ? JSON.stringify(ev.details, null, 2)
                            : detailsText}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        <div className="flex items-center justify-between text-xs text-neutral-500 dark:text-neutral-400 pt-1">
          <span>
            Showing {events.length} of {totalEvents.toLocaleString()} events
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={page <= 1 || loading}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              Prev
            </Button>
            <span className="tabular-nums">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="secondary"
              size="sm"
              disabled={page >= totalPages || loading}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Next
              <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      </M3Card>
    </div>
  );
}
