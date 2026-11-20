/**
 * SPEC-28: Glass-Box Privacy Shield & Airplane Lock
 *
 * Status-bar shield indicator that displays real-time outbound network count,
 * Airplane Lock toggle (hard-blocks non-loopback requests), and an inspectable
 * live egress ledger modal.
 */
import { useState, useEffect, useCallback } from "react";
import { Shield, Plane, RefreshCw, Trash2, CheckCircle2, Lock } from "lucide-react";
import { api } from "@/lib/transport";
import { cn } from "@/lib/utils";
import { Dialog } from "@/components/ui/dialog";

export interface EgressLedgerEntry {
  timestamp: string;
  url: string;
  host: string;
  purpose: string;
  method?: string;
  bytes_sent: number;
  blocked: boolean;
}

export interface EgressLedgerResponse {
  airplane_lock: boolean;
  total_allowed_requests?: number;
  total_blocked_requests?: number;
  external_connections_count?: number;
  blocked_connections_count?: number;
  policy_locked?: boolean;
  policy_source?: string | null;
  entries: EgressLedgerEntry[];
}

export interface PrivacyManifest {
  airplane_lock: boolean;
  policy_locked?: boolean;
  policy_source?: string | null;
  telemetry?: string;
  telemetry_enabled?: boolean;
  crash_reporting_enabled?: boolean;
  analytics_sdks: string[];
  local_storage_only?: boolean;
  allowed_outbound_purposes?: { purpose: string; destination: string; when: string }[];
  guarantees: string[];
}

export function PrivacyShield({ iconOnly = false }: { iconOnly?: boolean }) {
  const [open, setOpen] = useState(false);
  const [ledger, setLedger] = useState<EgressLedgerResponse>({
    airplane_lock: false,
    total_allowed_requests: 0,
    total_blocked_requests: 0,
    policy_locked: false,
    policy_source: null,
    entries: [],
  });
  const [manifest, setManifest] = useState<PrivacyManifest | null>(null);
  const [toggling, setToggling] = useState(false);
  const [toggleError, setToggleError] = useState<string | null>(null);

  const allowedRequests =
    ledger.total_allowed_requests ?? ledger.external_connections_count ?? 0;
  const isPolicyLocked = Boolean(ledger.policy_locked);

  const fetchStatus = useCallback(async () => {
    try {
      const { data } = await api.get<EgressLedgerResponse>("/privacy/ledger?limit=50");
      setLedger(data);
    } catch {
      // ignore if sidecar is still warming up
    }
  }, []);

  const fetchManifest = useCallback(async () => {
    try {
      const { data } = await api.get<PrivacyManifest>("/privacy/manifest");
      setManifest(data);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const timer = setInterval(fetchStatus, 10000);
    return () => clearInterval(timer);
  }, [fetchStatus]);

  useEffect(() => {
    if (open) {
      fetchStatus();
      fetchManifest();
    }
  }, [open, fetchStatus, fetchManifest]);

  const handleToggleAirplane = async () => {
    if (isPolicyLocked && ledger.airplane_lock) return;
    setToggling(true);
    setToggleError(null);
    try {
      const next = !ledger.airplane_lock;
      await api.post("/privacy/airplane-lock", { enabled: next });
      await fetchStatus();
    } catch (err) {
      setToggleError(
        err instanceof Error ? err.message : "Failed to toggle Airplane Lock"
      );
      console.error("Failed to toggle Airplane Lock:", err);
    } finally {
      setToggling(false);
    }
  };

  const handleClearLedger = async () => {
    try {
      await api.delete("/privacy/ledger");
      await fetchStatus();
    } catch {
      // ignore
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-colors border",
          ledger.airplane_lock
            ? "bg-amber-50 dark:bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/30"
            : allowedRequests === 0
              ? "bg-emerald-50 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30"
              : "bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 border-neutral-200 dark:border-neutral-700"
        )}
        title={
          isPolicyLocked
            ? "Glass-Box Privacy Shield (Airplane Lock Locked by IT Policy)"
            : "Glass-Box Privacy Shield & Egress Ledger"
        }
      >
        {ledger.airplane_lock ? (
          <>
            <Plane className="w-3.5 h-3.5 shrink-0" />
            {!iconOnly && <span className="truncate">Airplane Lock</span>}
            {!iconOnly && isPolicyLocked && <Lock className="w-3 h-3 shrink-0" />}
          </>
        ) : (
          <>
            <Shield className="w-3.5 h-3.5 shrink-0" />
            {!iconOnly && (
              <span className="truncate">
                {allowedRequests === 0
                  ? "0 External"
                  : `${allowedRequests} External`}
              </span>
            )}
          </>
        )}
      </button>

      <Dialog
        open={open}
        onClose={() => {
          setOpen(false);
          setToggleError(null);
        }}
        title="Glass-Box Privacy Shield"
        className="max-w-2xl"
        actions={
          <div className="flex items-center justify-between w-full">
            <button
              type="button"
              onClick={handleClearLedger}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Clear Log
            </button>
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                setToggleError(null);
              }}
              className="px-4 py-1.5 text-xs font-medium rounded-lg bg-primary-500 hover:bg-primary-600 text-white"
            >
              Done
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          {/* Airplane Lock Banner */}
          <div className="flex items-center justify-between gap-3 p-3.5 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-800/60">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-400">
                <Lock className="w-4 h-4" />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="text-sm font-semibold text-neutral-900 dark:text-white">
                    Airplane Lock (Zero-Egress Mode)
                  </h4>
                  {isPolicyLocked && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-amber-100 dark:bg-amber-500/20 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-500/30">
                      <Lock className="w-3 h-3" />
                      Locked by IT Policy
                    </span>
                  )}
                </div>
                <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                  {isPolicyLocked
                    ? "Enforced by enterprise IT policy. All non-loopback network connections are blocked and cannot be unlocked by the user."
                    : "When active, every non-loopback network connection (HuggingFace, Cloud APIs, Channels) is hard-blocked before any socket leaves your machine."}
                </p>
              </div>
            </div>
            <button
              type="button"
              disabled={toggling || isPolicyLocked}
              onClick={handleToggleAirplane}
              title={
                isPolicyLocked
                  ? "Locked by IT Policy"
                  : undefined
              }
              className={cn(
                "px-3.5 py-2 rounded-lg text-xs font-semibold transition-colors shrink-0",
                ledger.airplane_lock
                  ? "bg-amber-500 text-white hover:bg-amber-600"
                  : "bg-neutral-200 dark:bg-neutral-700 text-neutral-800 dark:text-neutral-200 hover:bg-neutral-300 dark:hover:bg-neutral-600",
                (toggling || isPolicyLocked) && "opacity-60 cursor-not-allowed hover:bg-amber-500"
              )}
            >
              {isPolicyLocked
                ? "Locked by IT Policy"
                : ledger.airplane_lock
                  ? "Airplane Lock: ON"
                  : "Enable Airplane Lock"}
            </button>
          </div>

          {toggleError && (
            <div className="px-3 py-2 rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-xs text-red-700 dark:text-red-300">
              {toggleError}
            </div>
          )}

          {/* Verifiable Guarantees */}
          {manifest && (
            <div className="p-3 rounded-xl border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50/50 dark:bg-emerald-950/20">
              <div className="text-xs font-semibold text-emerald-800 dark:text-emerald-300 mb-1.5 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Zero-Telemetry Architecture Guarantees
              </div>
              <ul className="space-y-1 text-xs text-emerald-700 dark:text-emerald-400">
                {manifest.guarantees.map((g, i) => (
                  <li key={i}>• {g}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Live Egress Ledger */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-neutral-800 dark:text-neutral-200">
                Outbound Network Activity Ledger ({ledger.entries.length})
              </span>
              <button
                type="button"
                onClick={fetchStatus}
                className="inline-flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300"
              >
                <RefreshCw className="w-3 h-3" /> Refresh
              </button>
            </div>
            {ledger.entries.length === 0 ? (
              <div className="text-center py-8 rounded-xl border border-dashed border-neutral-200 dark:border-neutral-800 text-xs text-neutral-500">
                0 external network requests recorded in this session.
              </div>
            ) : (
              <div className="max-h-56 overflow-y-auto rounded-xl border border-neutral-200 dark:border-neutral-800 divide-y divide-neutral-100 dark:divide-neutral-800">
                {ledger.entries.map((entry, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between px-3 py-2 text-xs"
                  >
                    <div className="truncate pr-3">
                      <span className="font-mono font-medium text-neutral-900 dark:text-white">
                        {entry.method ? `${entry.method} ` : ""}{entry.host}
                      </span>
                      <span className="ml-2 text-neutral-500">({entry.purpose})</span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span
                        className={cn(
                          "px-1.5 py-0.5 rounded text-[10px] font-semibold",
                          entry.blocked
                            ? "bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400"
                            : "bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400"
                        )}
                      >
                        {entry.blocked ? "BLOCKED" : "ALLOWED"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </Dialog>
    </>
  );
}
