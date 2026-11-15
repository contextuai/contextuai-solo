/**
 * SPEC-33: Local Server Control Panel (`/server`)
 *
 * Developer-focused control panel for `http://127.0.0.1:18741/v1` (OpenAI-compatible
 * Chat Completions + Fill-in-the-Middle `/v1/completions` code autocomplete + MCP snippets)
 * and live `/v1` request inspector.
 */
import { useState, useEffect, useCallback } from "react";
import { Server, Copy, Check, RefreshCw, Terminal, Code2, Cpu } from "lucide-react";
import { api } from "@/lib/transport";
import { cn } from "@/lib/utils";

interface V1RequestEntry {
  timestamp: string;
  endpoint: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  latency_ms: number;
  tokens_per_second: number;
}

interface ServerStatsResponse {
  loaded_model: string | null;
  loaded_context_window: number | null;
  loaded_mmproj: string | null;
  endpoint_base: string;
  recent_requests: V1RequestEntry[];
}

export default function LocalServerPage() {
  const [stats, setStats] = useState<ServerStatsResponse | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [activeSnippet, setActiveSnippet] = useState<"continue" | "cursor" | "python" | "curl">("continue");

  const fetchStats = useCallback(async () => {
    try {
      const { data } = await api.get<ServerStatsResponse>("/local-models/server-stats");
      setStats(data);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    fetchStats();
    const timer = setInterval(fetchStats, 5000);
    return () => clearInterval(timer);
  }, [fetchStats]);

  const modelId = stats?.loaded_model ? `local:${stats.loaded_model}` : "local:qwen2.5-coder-7b";
  const baseUrl = stats?.endpoint_base || "http://127.0.0.1:18741/v1";

  const snippets: Record<string, { label: string; code: string }> = {
    continue: {
      label: "Continue.dev (Chat + FIM Autocomplete)",
      code: JSON.stringify(
        {
          models: [
            {
              title: "Vesper / ContextuAI Local",
              provider: "openai",
              model: modelId,
              apiBase: baseUrl,
              apiKey: "sk-local",
            },
          ],
          tabAutocompleteModel: {
            title: "Vesper Local FIM",
            provider: "openai",
            model: modelId,
            apiBase: baseUrl,
            apiKey: "sk-local",
          },
        },
        null,
        2
      ),
    },
    cursor: {
      label: "Cursor / Aider / OpenAI-Compatible IDE",
      code: `# Base URL: ${baseUrl}\n# API Key: sk-local\n# Model: ${modelId}\n\naider --openai-api-base ${baseUrl} --openai-api-key sk-local --model openai/${modelId}`,
    },
    python: {
      label: "OpenAI Python SDK",
      code: `from openai import OpenAI\n\nclient = OpenAI(\n    base_url="${baseUrl}",\n    api_key="sk-local",\n)\n\nresp = client.chat.completions.create(\n    model="${modelId}",\n    messages=[{"role": "user", "content": "Write a fast binary search in Rust."}],\n)\nprint(resp.choices[0].message.content)`,
    },
    curl: {
      label: "cURL (Chat & FIM Completion)",
      code: `curl ${baseUrl}/chat/completions \\\n  -H "Content-Type: application/json" \\\n  -d '{"model": "${modelId}", "messages": [{"role": "user", "content": "Hello!"}]}'`,
    },
  };

  const copySnippet = (key: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(key);
    setTimeout(() => setCopiedId(null), 1800);
  };

  return (
    <div className="flex flex-col h-full bg-neutral-50 dark:bg-[#1a1b1a] overflow-y-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-neutral-900 dark:text-white flex items-center gap-2">
            <Server className="w-5 h-5 text-primary-500" />
            Local OpenAI & FIM Server
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            Drop-in local <code className="font-mono text-xs">/v1/chat/completions</code> and Fill-in-the-Middle <code className="font-mono text-xs">/v1/completions</code> server for Cursor, Continue.dev, Aider, and SDKs.
          </p>
        </div>
        <button
          type="button"
          onClick={fetchStats}
          className="p-2 rounded-lg border border-neutral-200 dark:border-neutral-800 hover:bg-neutral-100 dark:hover:bg-neutral-800"
        >
          <RefreshCw className="w-4 h-4 text-neutral-500" />
        </button>
      </div>

      {/* Status Card */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800">
          <div className="text-xs text-neutral-500 mb-1">OpenAI Endpoint</div>
          <div className="font-mono text-sm font-semibold text-neutral-900 dark:text-white">
            {baseUrl}
          </div>
        </div>
        <div className="p-4 rounded-xl bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800">
          <div className="text-xs text-neutral-500 mb-1 flex items-center gap-1">
            <Cpu className="w-3.5 h-3.5" /> Active Loaded Model
          </div>
          <div className="text-sm font-semibold text-neutral-900 dark:text-white">
            {stats?.loaded_model || "On-demand (loads automatically on first request)"}
          </div>
        </div>
        <div className="p-4 rounded-xl bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800">
          <div className="text-xs text-neutral-500 mb-1">Active Context Window</div>
          <div className="text-sm font-semibold text-neutral-900 dark:text-white">
            {stats?.loaded_context_window ? `${stats.loaded_context_window.toLocaleString()} tokens` : "Dynamic (Hardware Fit Engine)"}
          </div>
        </div>
      </div>

      {/* IDE & SDK Snippets */}
      <div className="p-5 rounded-xl bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-neutral-900 dark:text-white flex items-center gap-2">
            <Code2 className="w-4 h-4 text-primary-500" />
            1-Click IDE & SDK Configuration Snippets
          </h2>
          <div className="flex items-center gap-1">
            {(["continue", "cursor", "python", "curl"] as const).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setActiveSnippet(k)}
                className={cn(
                  "px-2.5 py-1 rounded-lg text-xs font-medium transition-colors",
                  activeSnippet === k
                    ? "bg-primary-500 text-white"
                    : "bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400"
                )}
              >
                {k === "continue" ? "Continue.dev" : k === "cursor" ? "Cursor / Aider" : k === "python" ? "Python" : "cURL"}
              </button>
            ))}
          </div>
        </div>
        <div className="relative">
          <pre className="p-4 rounded-xl bg-neutral-950 text-neutral-100 font-mono text-xs overflow-x-auto">
            {snippets[activeSnippet].code}
          </pre>
          <button
            type="button"
            onClick={() => copySnippet(activeSnippet, snippets[activeSnippet].code)}
            className="absolute top-3 right-3 inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-xs"
          >
            {copiedId === activeSnippet ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-400" /> Copied
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" /> Copy
              </>
            )}
          </button>
        </div>
      </div>

      {/* Live Request Log */}
      <div className="p-5 rounded-xl bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800">
        <h2 className="text-sm font-semibold text-neutral-900 dark:text-white flex items-center gap-2 mb-3">
          <Terminal className="w-4 h-4 text-primary-500" />
          Live <code className="font-mono text-xs">/v1</code> Request Stream
        </h2>
        {!stats?.recent_requests || stats.recent_requests.length === 0 ? (
          <div className="text-center py-8 text-xs text-neutral-500 border border-dashed border-neutral-200 dark:border-neutral-800 rounded-xl">
            No <code className="font-mono">/v1</code> requests recorded yet. Connect Cursor, Continue.dev, or run a cURL command above.
          </div>
        ) : (
          <div className="divide-y divide-neutral-100 dark:divide-neutral-800">
            {stats.recent_requests.map((req, idx) => (
              <div key={idx} className="flex items-center justify-between py-2.5 text-xs">
                <div className="flex items-center gap-3">
                  <span className="font-mono font-semibold text-primary-600 dark:text-primary-400">
                    {req.endpoint}
                  </span>
                  <span className="font-medium text-neutral-900 dark:text-white">
                    {req.model}
                  </span>
                </div>
                <div className="flex items-center gap-4 text-neutral-500 tabular-nums">
                  <span>{req.prompt_tokens} in / {req.completion_tokens} out</span>
                  <span>{req.tokens_per_second} tok/s</span>
                  <span>{req.latency_ms} ms</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
