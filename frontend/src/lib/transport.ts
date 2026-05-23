const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
// Desktop Solo backend runs on port 18741; override via VITE_API_URL env var
const DEV_API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:18741/api/v1";

export interface ApiResponse<T = unknown> {
  data: T;
  status: number;
  ok: boolean;
}

/** Error thrown when an API request returns a non-2xx status. */
export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(status: number, data: unknown) {
    const detail = extractDetail(data);
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

function extractDetail(data: unknown): string {
  if (!data || typeof data !== "object") return "Request failed";
  const raw = data as Record<string, unknown>;
  const detail = raw.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return (detail as { msg?: string }[]).map((d) => d.msg).filter(Boolean).join("; ") || "Validation error";
  }
  if (typeof raw.message === "string") return raw.message;
  if (typeof raw.error === "string") return raw.error;
  return "Request failed";
}

async function _singleApiRequest<T = unknown>(
  method: string,
  path: string,
  body?: unknown,
  options?: { stream?: boolean; headers?: Record<string, string> }
): Promise<ApiResponse<T>> {
  let data: T;
  let status: number;
  let ok: boolean;

  if (isTauri) {
    // Desktop: route through Tauri IPC
    const { invoke } = await import("@tauri-apps/api/core");
    const result = await invoke<{ data: T; status: number }>("api_request", {
      method,
      path,
      body: body ? JSON.stringify(body) : null,
    });
    data = result.data;
    status = result.status;
    ok = status >= 200 && status < 300;
  } else {
    // Dev mode: direct HTTP to backend
    const url = `${DEV_API_URL}${path}`;
    const response = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    data = await response.json() as T;
    status = response.status;
    ok = response.ok;
  }

  if (!ok) {
    throw new ApiError(status, data);
  }

  return { data, status, ok };
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// Tracks whether we've ever seen a successful response from the backend.
// Used to widen retry behavior during the cold-start window: until the first
// success we treat 404 on writes as "route not yet mounted" (race with
// FastAPI's startup) instead of a real not-found.
let _backendReady = false;

function isConnectionError(err: unknown): boolean {
  const msg = String(err);
  return (
    msg.includes("connection") ||
    msg.includes("Connection") ||
    msg.includes("os error") ||
    msg.includes("Failed to fetch")
  );
}

function isColdStart404(err: unknown, method: string): boolean {
  if (_backendReady) return false;
  if (!(err instanceof ApiError) || err.status !== 404) return false;
  // Only retry creation/update verbs — GET 404 on a deleted resource is real.
  return method === "POST" || method === "PUT" || method === "PATCH";
}

export async function apiRequest<T = unknown>(
  method: string,
  path: string,
  body?: unknown,
  options?: { stream?: boolean; headers?: Record<string, string> }
): Promise<ApiResponse<T>> {
  // Dev mode: still retry connection errors + cold-start 404s — uvicorn
  // --reload has the same race window as the Tauri sidecar.
  let lastError: unknown;
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      const result = await _singleApiRequest<T>(method, path, body, options);
      _backendReady = true;
      return result;
    } catch (err) {
      lastError = err;
      if (isConnectionError(err) || isColdStart404(err, method)) {
        await sleep(1500 * (attempt + 1));
        continue;
      }
      throw err;
    }
  }
  throw lastError;
}

// Convenience methods
export const api = {
  get: <T = unknown>(path: string) => apiRequest<T>("GET", path),
  post: <T = unknown>(path: string, body?: unknown) => apiRequest<T>("POST", path, body),
  put: <T = unknown>(path: string, body?: unknown) => apiRequest<T>("PUT", path, body),
  patch: <T = unknown>(path: string, body?: unknown) => apiRequest<T>("PATCH", path, body),
  delete: <T = unknown>(path: string) => apiRequest<T>("DELETE", path),
};

// SSE streaming support for chat
export async function* streamRequest(
  path: string,
  body: unknown,
  signal?: AbortSignal
): AsyncGenerator<{ type: string; data: string }, void, unknown> {
  // For streaming, always use fetch (even in Tauri, SSE goes through HTTP)
  const baseUrl = isTauri ? `http://127.0.0.1:${await getSidecarPort()}` : DEV_API_URL.replace("/api/v1", "");
  const fullUrl = `${baseUrl}/api/v1${path}`;

  let response: Response | null = null;
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      response = await fetch(fullUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal,
      });
      break;
    } catch (err) {
      if (signal?.aborted) return;
      if (attempt < 4 && isTauri) {
        await sleep(1500 * (attempt + 1));
        continue;
      }
      yield { type: "error", data: `Connection failed: ${err}` };
      return;
    }
  }

  if (!response || !response.ok) {
    yield { type: "error", data: `HTTP ${response?.status}: ${response?.statusText}` };
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    yield { type: "error", data: "No response body" };
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
      if (!trimmed) continue;
      if (trimmed.startsWith("data: ")) {
        const content = trimmed.substring(6);
        if (content === "[DONE]") continue;
        try {
          const parsed = JSON.parse(content);
          if (parsed.thinking) {
            yield { type: "thinking", data: parsed.thinking };
          }
          if (parsed.status === "error" || parsed.error) {
            yield { type: "error", data: parsed.message || parsed.chunk || "An unexpected error occurred" };
          } else if (parsed.chunk) {
            yield { type: "chunk", data: parsed.chunk };
          } else if (parsed.is_final) {
            yield { type: "metadata", data: JSON.stringify(parsed.metadata || {}) };
          }
        } catch {
          yield { type: "chunk", data: content };
        }
      }
    }
  }
}

async function getSidecarPort(): Promise<number> {
  if (isTauri) {
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke<number>("get_sidecar_port");
  }
  return 18741;
}

/** Get the base URL for direct HTTP requests (SSE streams, downloads). */
export async function getApiBaseUrl(): Promise<string> {
  if (isTauri) {
    const port = await getSidecarPort();
    return `http://127.0.0.1:${port}/api/v1`;
  }
  return DEV_API_URL;
}

/**
 * Backend root (no /api/v1 suffix) — for OpenAI-compatible endpoints that
 * the backend mounts at the root: /v1/models, /v1/chat/completions,
 * /v1/completions. Mirrors the routing in routers/openai_compat.py.
 */
export async function getBackendRootUrl(): Promise<string> {
  if (isTauri) {
    const port = await getSidecarPort();
    return `http://127.0.0.1:${port}`;
  }
  return DEV_API_URL.replace("/api/v1", "");
}

/** GET helper for the OpenAI-compat endpoints mounted at the backend root. */
export async function fetchOpenAICompat<T = unknown>(path: string): Promise<T> {
  const baseUrl = await getBackendRootUrl();
  const resp = await fetch(`${baseUrl}${path}`);
  if (!resp.ok) throw new ApiError(resp.status, await resp.json().catch(() => ({})));
  return (await resp.json()) as T;
}
