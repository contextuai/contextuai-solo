import { api } from "@/lib/transport";

export interface LocalModel {
  id: string;
  name: string;
  file: string;
  size_bytes: number;
  ram_gb: number;
  supports_tools: boolean;
  tier: "basic" | "recommended" | "best";
  downloaded: boolean;
  loaded: boolean;
}

export interface DownloadProgress {
  model_id: string;
  percent: number;
  bytes_downloaded: number;
  bytes_total: number;
  status: "downloading" | "verifying" | "complete" | "error";
  error?: string;
}

export interface ModelStatus {
  loaded: boolean;
  model_id: string | null;
  model_file: string | null;
  ram_mb: number | null;
}

export async function getAvailableModels(): Promise<LocalModel[]> {
  const { data } = await api.get<LocalModel[]>("/local-models/available");
  return Array.isArray(data) ? data : [];
}

export async function getDownloadedModels(): Promise<LocalModel[]> {
  const { data } = await api.get<LocalModel[]>("/local-models/downloaded");
  return Array.isArray(data) ? data : [];
}

export async function getModelStatus(): Promise<ModelStatus> {
  const { data } = await api.get<ModelStatus>("/local-models/status");
  return data;
}

export async function startDownload(modelId: string): Promise<void> {
  await api.post("/local-models/download", { model_id: modelId });
}

export async function loadModel(modelId: string): Promise<void> {
  await api.post("/local-models/load", { model_id: modelId });
}

export async function unloadModel(): Promise<void> {
  await api.post("/local-models/unload");
}

export async function deleteModel(modelId: string): Promise<void> {
  await api.delete(`/local-models/${modelId}`);
}

/**
 * Poll download progress via SSE.
 * Returns an EventSource-like interface using fetch (works in Tauri).
 */
export function streamDownloadProgress(
  onProgress: (progress: DownloadProgress) => void,
  onError?: (error: string) => void
): { cancel: () => void } {
  const controller = new AbortController();

  const baseUrl = import.meta.env.VITE_API_URL || "http://127.0.0.1:18741/api/v1";

  (async () => {
    try {
      const response = await fetch(`${baseUrl}/local-models/download/progress`, {
        signal: controller.signal,
      });
      if (!response.ok) {
        onError?.(`HTTP ${response.status}`);
        return;
      }
      const reader = response.body?.getReader();
      if (!reader) return;

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
              // skip parse errors
            }
          }
        }
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        onError?.(String(err));
      }
    }
  })();

  return { cancel: () => controller.abort() };
}
