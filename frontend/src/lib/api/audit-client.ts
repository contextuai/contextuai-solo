import { api, getApiBaseUrl, getSidecarToken } from "@/lib/transport";

export interface AuditEvent {
  id: string;
  timestamp: string;
  action: string;
  severity: "info" | "warning" | "error" | "critical" | string;
  user_id?: string | null;
  user_email?: string | null;
  auth_type?: string | null;
  ip_address?: string | null;
  user_agent?: string | null;
  resource_type?: string | null;
  resource_id?: string | null;
  details?: Record<string, unknown> | null;
  request_method?: string | null;
  request_path?: string | null;
  response_status?: number | null;
  airplane_lock?: boolean;
}

export interface AuditEventsQuery {
  action?: string;
  severity?: string;
  resource_type?: string;
  resource_id?: string;
  user_id?: string;
  from_date?: string;
  to_date?: string;
  page?: number;
  page_size?: number;
}

export interface AuditEventsResponse {
  events: AuditEvent[];
  total: number;
  page: number;
  page_size: number;
}

export interface AbomInstalledModel {
  id: string;
  name: string;
  filename: string;
  path: string;
  size_gb?: number;
  modified_at?: string;
  provider?: string;
  parameter_size?: string;
  sha256?: string;
  expected_sha256?: string | null;
  integrity_verified?: boolean | null;
  [key: string]: unknown;
}

export interface AbomReport {
  generated_at: string;
  app_name: string;
  app_version: string;
  privacy_posture: {
    airplane_lock?: boolean;
    policy_locked?: boolean;
    policy_source?: string | null;
    external_connections_count?: number;
    blocked_connections_count?: number;
    total_allowed_requests?: number;
    total_blocked_requests?: number;
    zero_egress_verified?: boolean;
    [key: string]: unknown;
  };
  dlp_posture: {
    available?: boolean;
    enabled?: boolean;
    redact_logs?: boolean;
    categories?: Record<string, boolean>;
    custom_rules?: unknown[];
    [key: string]: unknown;
  };
  catalog_policy: {
    available?: boolean;
    catalog_url?: string | null;
    catalog_exclusive?: boolean;
    require_sha256?: boolean;
    airplane_lock_enforced?: boolean;
    locked_fields?: string[];
    policy_source?: string | null;
    [key: string]: unknown;
  };
  installed_models: AbomInstalledModel[];
  active_model: {
    loaded?: boolean;
    model_id?: string | null;
    model_path?: string | null;
    n_ctx?: number | null;
    [key: string]: unknown;
  };
  audit_summary: {
    total: number;
    by_action: Record<string, number>;
    by_severity: Record<string, number>;
    airplane_lock_events?: number;
    latest_timestamp?: string | null;
  };
}

export async function listAuditEvents(
  params?: AuditEventsQuery,
): Promise<AuditEventsResponse> {
  const search = new URLSearchParams();
  if (params?.action) search.set("action", params.action);
  if (params?.severity) search.set("severity", params.severity);
  if (params?.resource_type) search.set("resource_type", params.resource_type);
  if (params?.resource_id) search.set("resource_id", params.resource_id);
  if (params?.user_id) search.set("user_id", params.user_id);
  if (params?.from_date) search.set("from_date", params.from_date);
  if (params?.to_date) search.set("to_date", params.to_date);
  if (params?.page) search.set("page", String(params.page));
  if (params?.page_size) search.set("page_size", String(params.page_size));

  const qs = search.toString();
  const { data } = await api.get<AuditEventsResponse>(
    `/audit/events${qs ? `?${qs}` : ""}`,
  );
  return data;
}

export async function getAbom(): Promise<AbomReport> {
  const { data } = await api.get<AbomReport>("/audit/abom");
  return data;
}

function _parseDispositionFilename(
  header: string | null,
  fallback: string,
): string {
  if (!header) return fallback;
  const match = header.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)["']?/i);
  return match?.[1]?.trim() || fallback;
}

export async function downloadAuditExport(
  format: "json" | "csv",
): Promise<string> {
  const baseUrl = await getApiBaseUrl();
  const token = await getSidecarToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers["X-ContextuAI-Token"] = token;
  }

  const response = await fetch(`${baseUrl}/audit/export?format=${format}`, {
    method: "GET",
    headers,
  });

  if (!response.ok) {
    let message = `Export failed (HTTP ${response.status})`;
    try {
      const errData = (await response.json()) as { detail?: string };
      if (errData?.detail) message = errData.detail;
    } catch {
      // keep HTTP error message
    }
    throw new Error(message);
  }

  const content = await response.text();
  const mimeType =
    format === "csv" ? "text/csv;charset=utf-8" : "application/json";
  const blob = new Blob([content], { type: mimeType });
  const filename = _parseDispositionFilename(
    response.headers.get("content-disposition"),
    `vesper-audit-abom.${format}`,
  );

  const objectUrl = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  } finally {
    URL.revokeObjectURL(objectUrl);
  }

  return filename;
}
