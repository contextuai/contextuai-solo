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
  const [testPrompt, setTestPrompt] = useState("Reply in one sentence: confirm that the local /v1 OpenAI server is operational.");
  const [testingChat, setTestingChat] = useState(false);
  const [testChatOutput, setTestChatOutput] = useState<{
    reply: string;
    latencyMs: number;
    model: string;
  } | null>(null);

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

  const runLiveChatCompletionTest = async () => {
    if (!testPrompt.trim()) return;
    setTestingChat(true);
    setTestChatOutput(null);
    const t0 = performance.now();
    try {
      const resp = await fetch(`${baseUrl}/chat/completions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: modelId,
          messages: [{ role: "user", content: testPrompt.trim() }],
          max_tokens: 128,
        }),
      });
      const json = await resp.json();
      const latencyMs = Math.round(performance.now() - t0);
      if (!resp.ok) {
        setTestChatOutput({
          reply: `HTTP ${resp.status}: ${json?.detail || JSON.stringify(json)}`,
          latencyMs,
          model: modelId,
        });
      } else {
        const content =
          json?.choices?.[0]?.message?.content ||
          JSON.stringify(json, null, 2);
        setTestChatOutput({
          reply: content,
          latencyMs,
          model: json?.model || modelId,
        });
      }
      fetchStats();
    } catch (err) {
      setTestChatOutput({
        reply: `Request error: ${err instanceof Error ? err.message : String(err)}`,
        latencyMs: Math.round(performance.now() - t0),
        model: modelId,
      });
    } finally {
      setTestingChat(false);
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
    <div className="flex flex-col h-full overflow-y-auto">
      {/* M3 Page Header */}
      <header className="px-6 pt-6 pb-4 border-b border-neutral-200/75 dark:border-neutral-800/90 bg-white/80 dark:bg-neutral-900/75 backdrop-blur-md">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3.5">
            <div className="flex items-center justify-center w-11 h-11 rounded-2xl bg-primary-500/12 text-primary-600 dark:text-primary-400 border border-primary-500/20 shrink-0">
              <Server className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white flex items-center gap-2">
                Local OpenAI <code className="text-base font-mono text-primary-600 dark:text-primary-400">/v1</code> & MCP Server
              </h1>
              <p className="text-xs sm:text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
                Drop-in local <code className="font-mono text-xs">/v1/chat/completions</code> & Fill-in-the-Middle <code className="font-mono text-xs">/v1/completions</code> for Cursor, Continue.dev, Aider, Claude Code & Python SDKs.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={testV1ModelsEndpoint}
              disabled={pinging}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-semibold bg-primary-500/15 text-primary-700 dark:text-primary-300 border border-primary-500/25 hover:bg-primary-500/25 transition-colors"
            >
              <Play className="w-3.5 h-3.5" />
              {pinging ? "Testing /v1/models..." : "Test /v1/models Live"}
            </button>
            <button
              type="button"
              onClick={fetchStats}
              className="p-2 rounded-full border border-neutral-200/80 dark:border-neutral-700/80 bg-white/80 dark:bg-neutral-800/80 hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors"
              title="Refresh server stats"
            >
              <RefreshCw className="w-4 h-4 text-neutral-500" />
            </button>
          </div>
        </div>
      </header>

      <div className="p-6 space-y-6">
        {pingResult && (
          <div className="flex items-center gap-2 px-4 py-2.5 rounded-2xl m3-card-tonal text-xs font-medium text-primary-700 dark:text-primary-300">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
            <span>{pingResult}</span>
          </div>
        )}

        {/* M3 Status Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-4 m3-card">
            <div className="text-xs font-medium text-neutral-500 mb-1">Local OpenAI Base URL</div>
            <div className="font-mono text-sm font-semibold text-neutral-900 dark:text-white flex items-center justify-between">
              <span>{baseUrl}</span>
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-primary-500/15 text-primary-700 dark:text-primary-300">
                Listening
              </span>
            </div>
            {loadedObj?.models_dir && (
              <div className="text-[11px] text-neutral-400 mt-1.5 truncate" title={loadedObj.models_dir}>
                Models Dir: {loadedObj.models_dir}
              </div>
            )}
          </div>

          <div className="p-4 m3-card">
            <div className="text-xs font-medium text-neutral-500 mb-1 flex items-center gap-1">
              <Cpu className="w-3.5 h-3.5 text-primary-500" /> Active Loaded GGUF Model
            </div>
            <div className="text-sm font-semibold text-neutral-900 dark:text-white">
              {activeModelName || "On-demand (loads automatically on first request)"}
            </div>
            <div className="text-[11px] text-neutral-400 mt-1.5">
              llama-cpp-python: {loadedObj?.llama_cpp_available ? "Installed & Ready" : "Not detected"}
            </div>
          </div>

          <div className="p-4 m3-card">
            <div className="text-xs font-medium text-neutral-500 mb-1">Active Context Window</div>
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
        <div className="p-5 m3-card">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <h2 className="text-sm font-semibold text-neutral-900 dark:text-white flex items-center gap-2">
              <Code2 className="w-4 h-4 text-primary-500" />
              1-Click IDE & SDK Configuration Snippets
            </h2>
            <div className="inline-flex flex-wrap items-center gap-1 p-1 rounded-2xl bg-neutral-100/80 dark:bg-neutral-950/70 border border-neutral-200/70 dark:border-neutral-800">
              {(["continue", "cursor", "claude_mcp", "python", "curl"] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setActiveSnippet(k)}
                  className={cn(
                    "px-3 py-1 rounded-xl text-xs font-medium transition-all",
                    activeSnippet === k
                      ? "bg-primary-500/15 text-primary-700 dark:text-primary-300 shadow-sm ring-1 ring-primary-500/25"
                      : "text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-200"
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

      {/* Interactive /v1 Live Inference Playground */}
      <div className="p-5 rounded-xl bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-neutral-900 dark:text-white flex items-center gap-2">
            <Play className="w-4 h-4 text-emerald-500" />
            Interactive <code className="font-mono text-xs">/v1/chat/completions</code> Sandbox
          </h2>
          <span className="text-[11px] font-mono text-neutral-400">
            Target: {modelId}
          </span>
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            value={testPrompt}
            onChange={(e) => setTestPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") runLiveChatCompletionTest();
            }}
            placeholder="Send a test prompt to /v1/chat/completions..."
            className="flex-1 px-3 py-2 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-xs text-neutral-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500/40"
          />
          <button
            type="button"
            onClick={runLiveChatCompletionTest}
            disabled={testingChat || !testPrompt.trim()}
            className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium bg-primary-500 hover:bg-primary-600 text-white disabled:opacity-50 transition-colors"
          >
            <Play className="w-3.5 h-3.5" />
            {testingChat ? "Running..." : "Send /v1 Request"}
          </button>
        </div>
        {testChatOutput && (
          <div className="p-3.5 rounded-xl bg-neutral-950 text-neutral-100 text-xs font-mono space-y-1.5">
            <div className="flex items-center justify-between text-[11px] text-neutral-400 border-b border-neutral-800 pb-1.5">
              <span>Model: {testChatOutput.model}</span>
              <span className="text-emerald-400">{testChatOutput.latencyMs} ms</span>
            </div>
            <div className="whitespace-pre-wrap leading-relaxed text-neutral-200">
              {testChatOutput.reply}
            </div>
          </div>
        )}
      </div>

      {/* Live Request Log */}
      <div className="p-5 m3-card">
        <h2 className="text-sm font-semibold text-neutral-900 dark:text-white flex items-center gap-2 mb-3">
          <Terminal className="w-4 h-4 text-primary-500" />
          Live <code className="font-mono text-xs">/v1</code> Request Telemetry Stream
        </h2>
        {!stats?.recent_requests || stats.recent_requests.length === 0 ? (
          <div className="text-center py-8 text-xs text-neutral-500 border border-dashed border-neutral-200 dark:border-neutral-800 rounded-2xl">
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
    </div>
  );
}
