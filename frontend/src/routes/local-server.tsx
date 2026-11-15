/**
 * SPEC-33: Local Server Control Panel (`/server`)
 *
 * Developer-focused control panel for `http://127.0.0.1:18741/v1` (OpenAI-compatible
 * Chat Completions + Fill-in-the-Middle `/v1/completions` code autocomplete + MCP snippets)
 * and live `/v1` request inspector.
 */
import { useState, useEffect, useCallback } from "react";
import { Server, Copy, Check, RefreshCw, Terminal, Code2, Cpu, Play, CheckCircle2 } from "lucide-react";
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

interface LoadedModelInfo {
  loaded?: boolean;
  model_id?: string | null;
  context_window?: number | null;
  mmproj_path?: string | null;
  llama_cpp_available?: boolean;
  gpu_offload_supported?: boolean;
  models_dir?: string;
}

interface ServerStatsResponse {
  loaded_model: LoadedModelInfo | string | null;
  loaded_context_window?: number | null;
  loaded_mmproj?: string | null;
  endpoint_base?: string;
  recent_requests: V1RequestEntry[];
}

export default function LocalServerPage() {
  const [stats, setStats] = useState<ServerStatsResponse | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [activeSnippet, setActiveSnippet] = useState<"continue" | "cursor" | "claude_mcp" | "python" | "curl">("continue");
  const [pingResult, setPingResult] = useState<string | null>(null);
  const [pinging, setPinging] = useState(false);

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

  const loadedObj: LoadedModelInfo | null =
    stats?.loaded_model && typeof stats.loaded_model === "object"
      ? stats.loaded_model
      : typeof stats?.loaded_model === "string"
        ? { loaded: true, model_id: stats.loaded_model }
        : null;

  const activeModelName = loadedObj?.model_id || null;
  const activeContextWindow =
    loadedObj?.context_window || stats?.loaded_context_window || null;
  const modelId = activeModelName ? `local:${activeModelName}` : "local:qwen2.5-coder-7b";
  const baseUrl = stats?.endpoint_base || "http://127.0.0.1:18741/v1";

  const testV1ModelsEndpoint = async () => {
    setPinging(true);
    try {
      const resp = await fetch(`${baseUrl}/models`);
      const json = await resp.json();
      const count = Array.isArray(json?.data) ? json.data.length : 0;
      setPingResult(`200 OK · ${count} model(s) exposed on ${baseUrl}/models`);
    } catch (err) {
      setPingResult(`Failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setPinging(false);
    }
  };

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
    claude_mcp: {
      label: "Claude Code / Cursor MCP Server (Local Docs & Memory)",
      code: JSON.stringify(
        {
          mcpServers: {
            "vesper-local-engine": {
              url: "http://127.0.0.1:18741/api/v1/mcp",
              description: "Query local GGUF models, Folder RAG knowledge base, and local memory",
            },
          },
        },
        null,
        2
      ),
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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-neutral-900 dark:text-white flex items-center gap-2">
            <Server className="w-5 h-5 text-primary-500" />
            Local OpenAI <code className="text-base font-mono">/v1</code> & MCP Server
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
            Turns your machine into a drop-in local OpenAI API (<code className="font-mono text-xs">/v1/chat/completions</code> & Fill-in-the-Middle <code className="font-mono text-xs">/v1/completions</code>) so external coding tools like <strong>Cursor</strong>, <strong>Continue.dev</strong>, <strong>Aider</strong>, <strong>Claude Code</strong>, or your own Python scripts can use your downloaded GGUF models for free.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={testV1ModelsEndpoint}
            disabled={pinging}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20"
          >
            <Play className="w-3.5 h-3.5" />
            {pinging ? "Testing /v1/models..." : "Test /v1/models Live"}
          </button>
          <button
            type="button"
            onClick={fetchStats}
            className="p-2 rounded-lg border border-neutral-200 dark:border-neutral-800 hover:bg-neutral-100 dark:hover:bg-neutral-800"
            title="Refresh server stats"
          >
            <RefreshCw className="w-4 h-4 text-neutral-500" />
          </button>
        </div>
      </div>

      {pingResult && (
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/25 text-xs font-medium text-emerald-700 dark:text-emerald-300">
          <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
          <span>{pingResult}</span>
        </div>
      )}

      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800">
          <div className="text-xs text-neutral-500 mb-1">Local OpenAI Base URL</div>
          <div className="font-mono text-sm font-semibold text-neutral-900 dark:text-white flex items-center justify-between">
            <span>{baseUrl}</span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
              Listening
            </span>
          </div>
          {loadedObj?.models_dir && (
            <div className="text-[11px] text-neutral-400 mt-1.5 truncate" title={loadedObj.models_dir}>
              Models Dir: {loadedObj.models_dir}
            </div>
          )}
        </div>

        <div className="p-4 rounded-xl bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800">
          <div className="text-xs text-neutral-500 mb-1 flex items-center gap-1">
            <Cpu className="w-3.5 h-3.5" /> Active Loaded GGUF Model
          </div>
          <div className="text-sm font-semibold text-neutral-900 dark:text-white">
            {activeModelName || "On-demand (loads automatically on first request)"}
          </div>
          <div className="text-[11px] text-neutral-400 mt-1.5">
            llama-cpp-python: {loadedObj?.llama_cpp_available ? "Installed & Ready" : "Not detected"}
          </div>
        </div>

        <div className="p-4 rounded-xl bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800">
          <div className="text-xs text-neutral-500 mb-1">Active Context Window</div>
          <div className="text-sm font-semibold text-neutral-900 dark:text-white">
            {activeContextWindow
              ? `${activeContextWindow.toLocaleString()} tokens`
              : "Dynamic (Auto-sized by Hardware Fit Engine)"}
          </div>
          <div className="text-[11px] text-neutral-400 mt-1.5">
            Supports Chat, Tool Calling (GBNF) & FIM Code Completion
          </div>
        </div>
      </div>

      {/* IDE & SDK Snippets */}
      <div className="p-5 rounded-xl bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <h2 className="text-sm font-semibold text-neutral-900 dark:text-white flex items-center gap-2">
            <Code2 className="w-4 h-4 text-primary-500" />
            1-Click IDE & SDK Configuration Snippets
          </h2>
          <div className="flex flex-wrap items-center gap-1">
            {(["continue", "cursor", "claude_mcp", "python", "curl"] as const).map((k) => (
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
                {k === "continue"
                  ? "Continue.dev"
                  : k === "cursor"
                    ? "Cursor / Aider"
                    : k === "claude_mcp"
                      ? "Claude / MCP"
                      : k === "python"
                        ? "Python SDK"
                        : "cURL"}
              </button>
            ))}
          </div>
        </div>
        <div className="text-xs text-neutral-500 dark:text-neutral-400 mb-2">
          {snippets[activeSnippet].label}
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
          Live <code className="font-mono text-xs">/v1</code> Request Telemetry Stream
        </h2>
        {!stats?.recent_requests || stats.recent_requests.length === 0 ? (
          <div className="text-center py-8 text-xs text-neutral-500 border border-dashed border-neutral-200 dark:border-neutral-800 rounded-xl">
            No <code className="font-mono">/v1</code> inference requests recorded yet. Connect Cursor, Continue.dev, or run the cURL snippet above to watch real-time token/sec speed and latency here.
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
