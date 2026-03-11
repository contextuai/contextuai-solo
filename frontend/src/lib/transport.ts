const isTauri = typeof window !== "undefined" && "__TAURI__" in window;
// Desktop Solo backend runs on port 18741; override via VITE_API_URL env var
const DEV_API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:18741/api/v1";

interface ApiResponse<T = unknown> {
  data: T;
  status: number;
  ok: boolean;
}

export async function apiRequest<T = unknown>(
  method: string,
  path: string,
  body?: unknown,
  options?: { stream?: boolean; headers?: Record<string, string> }
): Promise<ApiResponse<T>> {
  if (isTauri) {
    // Desktop: route through Tauri IPC
    const { invoke } = await import("@tauri-apps/api/core");
    const result = await invoke<{ data: T; status: number }>("api_request", {
      method,
      path,
      body: body ? JSON.stringify(body) : null,
    });
    return { data: result.data, status: result.status, ok: result.status >= 200 && result.status < 300 };
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
    const data = await response.json() as T;
    return { data, status: response.status, ok: response.ok };
  }
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
  body: unknown
): AsyncGenerator<{ type: string; data: string }, void, unknown> {
  // For streaming, always use fetch (even in Tauri, SSE goes through HTTP)
  const baseUrl = isTauri ? `http://127.0.0.1:${await getSidecarPort()}` : DEV_API_URL.replace("/api/v1", "");
  const fullUrl = `${baseUrl}/api/v1${path}`;

  const response = await fetch(fullUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    yield { type: "error", data: `HTTP ${response.status}: ${response.statusText}` };
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
          if (parsed.chunk !== undefined) {
            yield { type: "chunk", data: parsed.chunk };
          } else if (parsed.is_final) {
            yield { type: "metadata", data: JSON.stringify(parsed.metadata || {}) };
          } else if (parsed.status === "error") {
            yield { type: "error", data: parsed.metadata?.error || "Stream error" };
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
