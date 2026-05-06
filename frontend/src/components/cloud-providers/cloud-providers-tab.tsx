import { useState, useEffect, useCallback, useMemo } from "react";
import { Loader2, Cloud, AlertCircle } from "lucide-react";
import {
  listCloudProviders,
  saveCloudProvider,
  deleteCloudProvider,
  testCloudProvider,
  testSavedCloudProvider,
  type CloudProvider,
  type CloudProviderType,
  type TestResult,
} from "@/lib/api/cloud-providers-client";
import { CloudProviderCard, type CatalogProvider } from "./cloud-provider-card";

// ---------------------------------------------------------------------------
// Catalog
// ---------------------------------------------------------------------------

const CATALOG: readonly CatalogProvider[] = [
  {
    type: "anthropic",
    name: "Anthropic",
    tagline: "Claude (Sonnet, Opus, Haiku)",
    portalUrl: "https://console.anthropic.com/settings/keys",
    portalLabel: "console.anthropic.com",
    brand: "#cd7f32",
    fields: [
      { key: "api_key", label: "API key", placeholder: "sk-ant-...", secret: true },
    ],
  },
  {
    type: "openai",
    name: "OpenAI",
    tagline: "GPT-4o, GPT-4 Turbo, GPT-3.5",
    portalUrl: "https://platform.openai.com/api-keys",
    portalLabel: "platform.openai.com",
    brand: "#10a37f",
    fields: [
      { key: "api_key", label: "API key", placeholder: "sk-...", secret: true },
    ],
  },
  {
    type: "google",
    name: "Google AI",
    tagline: "Gemini 2.0, Gemini 1.5 Pro / Flash",
    portalUrl: "https://aistudio.google.com/app/apikey",
    portalLabel: "aistudio.google.com",
    brand: "#4285f4",
    fields: [
      { key: "api_key", label: "API key", placeholder: "AIza...", secret: true },
    ],
  },
  {
    type: "bedrock",
    name: "AWS Bedrock",
    tagline: "Anthropic, Meta, Mistral, Amazon Titan",
    portalUrl: "https://us-east-1.console.aws.amazon.com/iam/home",
    portalLabel: "AWS Console",
    brand: "#ff9900",
    fields: [
      { key: "aws_access_key_id", label: "Access key ID", placeholder: "AKIA...", secret: false },
      { key: "aws_secret_access_key", label: "Secret access key", secret: true },
      { key: "aws_region", label: "Region", placeholder: "us-east-1", secret: false },
    ],
  },
] as const;

// ---------------------------------------------------------------------------
// Tab
// ---------------------------------------------------------------------------

export function CloudProvidersTab() {
  const [providers, setProviders] = useState<CloudProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await listCloudProviders();
      setProviders(list);
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to load providers");
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    (async () => {
      setLoading(true);
      try {
        const list = await listCloudProviders();
        if (mounted) {
          setProviders(list);
          setLoadError(null);
        }
      } catch (err) {
        if (mounted) {
          setLoadError(err instanceof Error ? err.message : "Failed to load providers");
        }
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  // Map saved rows by provider_type for quick lookup
  const savedByType = useMemo(() => {
    const map: Partial<Record<CloudProviderType, CloudProvider>> = {};
    for (const p of providers) {
      map[p.provider_type] = p;
    }
    return map;
  }, [providers]);

  const handleConnect = useCallback(
    async (input: {
      provider_type: CloudProviderType;
      display_name?: string;
      config: Record<string, string>;
    }) => {
      await saveCloudProvider(input);
      await refresh();
    },
    [refresh],
  );

  const handleDisconnect = useCallback(
    async (providerId: string) => {
      await deleteCloudProvider(providerId);
      await refresh();
    },
    [refresh],
  );

  const handleTestUnsaved = useCallback(
    async (
      type: CloudProviderType,
      config: Record<string, string>,
    ): Promise<TestResult> => {
      return testCloudProvider({ provider_type: type, config });
    },
    [],
  );

  const handleTestSaved = useCallback(
    async (providerId: string): Promise<TestResult> => {
      const result = await testSavedCloudProvider(providerId);
      // refresh so last_test_status / last_tested_at are picked up
      await refresh();
      return result;
    },
    [refresh],
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 animate-spin text-primary-500" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header / intro */}
      <div className="flex items-start gap-3 p-4 rounded-xl bg-neutral-100 dark:bg-neutral-800/60 border border-neutral-200 dark:border-neutral-800">
        <Cloud className="w-5 h-5 text-primary-500 flex-shrink-0 mt-0.5" />
        <div>
          <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">
            Cloud LLM providers
          </h3>
          <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
            Bring your own API keys for Anthropic, OpenAI, Google, and AWS Bedrock. Keys are stored locally and never leave your machine.
          </p>
        </div>
      </div>

      {loadError && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-800/50 text-xs text-red-600 dark:text-red-400">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {loadError}
        </div>
      )}

      {/* 2-column grid of provider cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {CATALOG.map((provider) => {
          const saved = savedByType[provider.type];
          return (
            <CloudProviderCard
              key={provider.type}
              provider={provider}
              saved={saved}
              onConnect={handleConnect}
              onDisconnect={async () => {
                if (saved) await handleDisconnect(saved.provider_id);
              }}
              onTest={async (config) => {
                // No config => use the saved-provider test endpoint.
                // Config provided => test those values without saving.
                if (config === undefined && saved) {
                  return handleTestSaved(saved.provider_id);
                }
                return handleTestUnsaved(provider.type, config ?? {});
              }}
            />
          );
        })}
      </div>
    </div>
  );
}
