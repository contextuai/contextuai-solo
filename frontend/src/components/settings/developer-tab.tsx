import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Server, Copy, Check, ExternalLink, Sliders, Loader2 } from "lucide-react";
import { api } from "@/lib/transport";
import { useAdvancedMode } from "@/hooks/use-advanced-mode";
import { Button, Badge } from "@/components/ui";
import { Switch } from "@/components/ui/switch";

const DEFAULT_ENDPOINT_BASE = "http://127.0.0.1:18741/v1";

interface ServerConfigResponse {
  enabled?: boolean;
  server_enabled?: boolean;
  endpoint_base?: string;
}

export function DeveloperTab() {
  const navigate = useNavigate();
  const { advancedMode, setAdvancedMode } = useAdvancedMode();

  const [serverEnabled, setServerEnabled] = useState<boolean>(true);
  const [endpointBase, setEndpointBase] = useState<string>(DEFAULT_ENDPOINT_BASE);
  const [loadingConfig, setLoadingConfig] = useState<boolean>(true);
  const [savingServer, setSavingServer] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  const loadServerConfig = useCallback(async () => {
    setLoadingConfig(true);
    try {
      const { data } = await api.get<ServerConfigResponse>("/local-models/server-config");
      const enabled = data?.enabled ?? data?.server_enabled ?? true;
      setServerEnabled(Boolean(enabled));
      if (data?.endpoint_base) {
        setEndpointBase(data.endpoint_base);
      }
    } catch {
      // Graceful default when endpoint isn't wired yet or sidecar is warming up
      setServerEnabled(true);
      setEndpointBase(DEFAULT_ENDPOINT_BASE);
    } finally {
      setLoadingConfig(false);
    }
  }, []);

  useEffect(() => {
    loadServerConfig();
  }, [loadServerConfig]);

  const handleToggleServer = async (next: boolean) => {
    setServerEnabled(next);
    setSavingServer(true);
    try {
      const { data } = await api.post<ServerConfigResponse>(
        "/local-models/server-config",
        { enabled: next }
      );
      const confirmed = data?.enabled ?? data?.server_enabled;
      if (typeof confirmed === "boolean") {
        setServerEnabled(confirmed);
      }
    } catch {
      // Keep optimistic toggle state if backend route is not wired yet
    } finally {
      setSavingServer(false);
    }
  };

  const handleCopyEndpoint = async () => {
    try {
      await navigator.clipboard.writeText(endpointBase);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // ignore clipboard errors
    }
  };

  return (
    <div className="space-y-6">
      {/* Local OpenAI /v1 Server Card */}
      <div className="p-5 rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-primary-500/10 text-primary-600 dark:text-primary-400 shrink-0">
              <Server className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">
                  Local OpenAI /v1 Server
                </h3>
                <Badge variant={serverEnabled ? "success" : "default"} dot>
                  {serverEnabled ? "Enabled" : "Disabled"}
                </Badge>
              </div>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                Expose an OpenAI-compatible local endpoint for Cursor, Continue.dev, Aider, and external tools.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {(loadingConfig || savingServer) && (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-neutral-400" />
            )}
            <Switch
              checked={serverEnabled}
              onChange={handleToggleServer}
              disabled={savingServer}
              label="Toggle Local OpenAI /v1 Server"
            />
          </div>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-xl bg-neutral-50 dark:bg-neutral-800/60 border border-neutral-200/80 dark:border-neutral-700/70">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-[11px] font-medium uppercase tracking-wider text-neutral-400 shrink-0">
              Endpoint
            </span>
            <code className="text-xs font-mono text-neutral-800 dark:text-neutral-200 truncate">
              {endpointBase}
            </code>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={handleCopyEndpoint}
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-500" />
                  Copied
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  Copy URL
                </>
              )}
            </Button>
            <Button
              type="button"
              variant="tonal"
              size="sm"
              onClick={() => navigate("/server")}
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Open Full Server Inspector
            </Button>
          </div>
        </div>
      </div>

      {/* Advanced Mode Card */}
      <div className="p-5 rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300 shrink-0">
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">
                Advanced Mode
              </h3>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                Show Agents, Crews &amp; Automations in the sidebar — off by default for a clean Vesper experience
              </p>
            </div>
          </div>

          <Switch
            checked={advancedMode}
            onChange={setAdvancedMode}
            label="Toggle Advanced Mode"
          />
        </div>
      </div>
    </div>
  );
}

export default DeveloperTab;
