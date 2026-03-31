import { api, getApiBaseUrl } from "@/lib/transport";

// ── Types ──────────────────────────────────────────────────────────────

export interface SystemInfo {
  total_ram_gb: number;
  available_ram_gb: number;
  capped_ram_gb: number;
  os: string;
  arch: string;
  gpu: string | null;
  gpu_vram_gb: number | null;
  max_recommended_params: string;
}

export interface ModelCategory {
  id: string;
  label: string;
  icon: string;
  description: string;
}

export interface CatalogModel {
  id: string;
  name: string;
  family: string;
  provider: string;
  parameter_size: string;
  parameter_count: number;
  size_gb: number;
  ram_required_gb: number;
  ram_recommended_gb: number;
  categories: string[];
  description: string;
  quantization: string;
  context_window: number;
  supports_vision: boolean;
  supports_tools: boolean;
  quality_tier: "basic" | "good" | "great" | "best";
  speed_tier: "fast" | "medium" | "slow";
  hf_repo: string;
  hf_filename: string;
  chat_template: string;
  installed: boolean;
  is_recommended?: boolean;
}

export interface InstalledModel {
  id: string;
  name: string;
  filename: string;
  path: string;
  size_gb: number;
  provider: string;
  parameter_size: string;
  categories: string[];
  ram_required_gb: number | null;
  hf_repo?: string;
  modified_at: string;
}

export interface DiskUsage {
  models_gb: number;
  model_count: number;
  disk_free_gb: number;
  disk_total_gb: number;
}

export interface DownloadProgress {
  status: "starting" | "connecting" | "downloading" | "done" | "error" | "cancelled";
  model_id?: string;
  completed?: number;
  total?: number;
  percent?: number;
  completed_mb?: number;
  total_mb?: number;
  path?: string;
  detail?: string;
  already_exists?: boolean;
}

// ── API calls ──────────────────────────────────────────────────────────

const BASE = "/local-models";

export async function getSystemInfo(): Promise<SystemInfo> {
  const { data } = await api.get<SystemInfo>(`${BASE}/system-info`);
  return data;
}

export async function getCatalog(params?: {
  category?: string;
  max_ram_gb?: number;
}): Promise<{
  models: CatalogModel[];
  total: number;
  system_ram_gb: number;
  max_recommended_params: string;
  categories: ModelCategory[];
}> {
  const query = new URLSearchParams();
  if (params?.category) query.set("category", params.category);
  if (params?.max_ram_gb) query.set("max_ram_gb", String(params.max_ram_gb));
  const qs = query.toString();
  const path = qs ? `${BASE}/catalog?${qs}` : `${BASE}/catalog`;
  const { data } = await api.get<{
    models: CatalogModel[];
    total: number;
    system_ram_gb: number;
    max_recommended_params: string;
    categories: ModelCategory[];
  }>(path);
  return data;
}

export async function getRecommended(limit = 3): Promise<{
  models: CatalogModel[];
  system_ram_gb: number;
  max_recommended_params: string;
}> {
  const { data } = await api.get<{
    models: CatalogModel[];
    system_ram_gb: number;
    max_recommended_params: string;
  }>(`${BASE}/recommended?limit=${limit}`);
  return data;
}

export async function getInstalledModels(): Promise<{
  models: InstalledModel[];
  count: number;
  disk_usage: DiskUsage;
}> {
  const { data } = await api.get<{
    models: InstalledModel[];
    count: number;
    disk_usage: DiskUsage;
  }>(`${BASE}/installed`);
  return data;
}

export async function deleteModel(
  modelId: string
): Promise<{ status: string; freed_gb?: number }> {
  const { data } = await api.delete<{ status: string; freed_gb?: number }>(
    `${BASE}/${modelId}`
  );
  return data;
}

export async function getDiskUsage(): Promise<DiskUsage> {
  const { data } = await api.get<DiskUsage>(`${BASE}/disk-usage`);
  return data;
}

export async function getLoadedModel(): Promise<{
  loaded: boolean;
  model_id?: string;
  idle_seconds?: number;
}> {
  const { data } = await api.get<{
    loaded?: boolean;
    model_id?: string;
    idle_seconds?: number;
  }>(`${BASE}/loaded`);
  return { loaded: !!data.model_id, ...data };
}

// ── Download with SSE progress ─────────────────────────────────────────

export async function downloadModel(
  modelId: string,
  onProgress: (progress: DownloadProgress) => void,
  signal?: AbortSignal
): Promise<void> {
  const baseUrl = await getApiBaseUrl();
  const url = `${baseUrl}${BASE}/download`;

  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model_id: modelId }),
    signal,
  });

  if (!response.ok) {
    onProgress({ status: "error", detail: `HTTP ${response.status}` });
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    onProgress({ status: "error", detail: "No response body" });
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith("data: ")) {
        try {
          const parsed = JSON.parse(trimmed.substring(6)) as DownloadProgress;
          onProgress(parsed);
        } catch {
          // skip malformed lines
        }
      }
    }
  }
}

export async function cancelDownload(
  modelId: string
): Promise<{ status: string }> {
  const { data } = await api.post<{ status: string }>(
    `${BASE}/download/cancel`,
    { model_id: modelId }
  );
  return data;
}

/** Sync downloaded models into the DB so they appear in the chat dropdown. */
export async function syncLocalModels(): Promise<{ synced: number }> {
  const { data } = await api.post<{ synced: number }>("/local-models/sync");
  return data;
}
