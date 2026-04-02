import { useState, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import {
  Send,
  MessageCircle,
  Linkedin,
  AtSign,
  Camera,
  Globe,
  Check,
  Eye,
  EyeOff,
  ExternalLink,
  Loader2,
  Plus,
  Trash2,
  Info,
  ArrowDownToLine,
  ArrowUpFromLine,
  LogIn,
  User,
} from "lucide-react";
import {
  configureOAuthClient,
  getOAuthAuthorizeUrl,
  getOAuthStatus,
  disconnectOAuth,
  type OAuthStatus,
} from "@/lib/api/oauth-client";
import {
  listTriggers,
  createTrigger,
  updateTrigger,
  deleteTrigger,
  type Trigger,
} from "@/lib/api/triggers-client";

// ─── Types ──────────────────────────────────────────────────────

type ConnectionId = "telegram" | "discord" | "linkedin" | "twitter" | "instagram" | "facebook";

interface ConnectionConfig {
  id: ConnectionId;
  name: string;
  description: string;
  icon: React.ElementType;
  iconBg: string;
  iconColor: string;
  docsUrl: string;
  /** Token-paste fields (Telegram/Discord). Empty for OAuth providers. */
  fields: { key: string; label: string; placeholder: string; secret?: boolean }[];
  /** OAuth provider key (matches backend). Null = token-paste flow. */
  oauthProvider: string | null;
  /** Fields required before starting OAuth (client_id, client_secret). */
  oauthSetupFields?: { key: string; label: string; placeholder: string; secret?: boolean }[];
  /** OAuth setup instructions (provider-specific). */
  oauthHelp?: { title: string; devUrl: string; devLabel: string; callbackPath: string; steps?: string[] };
  supportsInbound: boolean;
  supportsOutbound: boolean;
  defaultInbound: boolean;
  defaultOutbound: boolean;
}

interface SavedConnection {
  id: ConnectionId;
  config: Record<string, string>;
  inbound: boolean;
  outbound: boolean;
  status: "connected" | "disconnected" | "error";
  connectedAt?: string;
  profileName?: string;
}

// ─── Connection definitions ─────────────────────────────────────

const CONNECTIONS: ConnectionConfig[] = [
  {
    id: "telegram",
    name: "Telegram Bot",
    description: "Send and receive messages via your Telegram bot.",
    icon: Send,
    iconBg: "bg-sky-100 dark:bg-sky-500/20",
    iconColor: "text-sky-600 dark:text-sky-400",
    docsUrl: "https://core.telegram.org/bots#how-do-i-create-a-bot",
    oauthProvider: null,
    supportsInbound: true,
    supportsOutbound: true,
    defaultInbound: true,
    defaultOutbound: true,
    fields: [
      {
        key: "bot_token",
        label: "Bot Token",
        placeholder: "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        secret: true,
      },
    ],
  },
  {
    id: "discord",
    name: "Discord Bot",
    description: "Send and receive messages in your Discord server.",
    icon: MessageCircle,
    iconBg: "bg-indigo-100 dark:bg-indigo-500/20",
    iconColor: "text-indigo-600 dark:text-indigo-400",
    docsUrl: "https://discord.com/developers/docs/getting-started",
    oauthProvider: null,
    supportsInbound: true,
    supportsOutbound: true,
    defaultInbound: true,
    defaultOutbound: true,
    fields: [
      {
        key: "bot_token",
        label: "Bot Token",
        placeholder: "Your Discord bot token",
        secret: true,
      },
      {
        key: "public_key",
        label: "Public Key",
        placeholder: "Your app's public key (for webhook verification)",
      },
      {
        key: "application_id",
        label: "Application ID",
        placeholder: "Your Discord application ID",
      },
    ],
  },
  {
    id: "linkedin",
    name: "LinkedIn",
    description: "Publish AI-generated content to your LinkedIn profile.",
    icon: Linkedin,
    iconBg: "bg-blue-100 dark:bg-blue-500/20",
    iconColor: "text-blue-600 dark:text-blue-400",
    docsUrl: "https://learn.microsoft.com/en-us/linkedin/marketing/getting-started",
    oauthProvider: "linkedin",
    oauthSetupFields: [
      {
        key: "client_id",
        label: "Client ID",
        placeholder: "Your LinkedIn App Client ID",
      },
      {
        key: "client_secret",
        label: "Client Secret",
        placeholder: "Your LinkedIn App Client Secret",
        secret: true,
      },
    ],
    oauthHelp: {
      title: "How to connect LinkedIn:",
      devUrl: "https://www.linkedin.com/developers/apps",
      devLabel: "LinkedIn Developers",
      callbackPath: "/api/v1/oauth/linkedin/callback",
    },
    fields: [], // No manual token fields — OAuth handles it
    supportsInbound: false,
    supportsOutbound: true,
    defaultInbound: false,
    defaultOutbound: true,
  },
  {
    id: "twitter",
    name: "Twitter / X",
    description: "Post daily content, updates, and engage with your audience on X.",
    icon: AtSign,
    iconBg: "bg-neutral-100 dark:bg-neutral-500/20",
    iconColor: "text-neutral-900 dark:text-neutral-200",
    docsUrl: "https://developer.x.com/en/portal/dashboard",
    oauthProvider: null,
    supportsInbound: false,
    supportsOutbound: true,
    defaultInbound: false,
    defaultOutbound: true,
    fields: [
      { key: "api_key", label: "API Key", placeholder: "Your Twitter API Key", secret: true },
      { key: "api_secret", label: "API Secret", placeholder: "Your Twitter API Secret", secret: true },
      { key: "access_token", label: "Access Token", placeholder: "Your Access Token", secret: true },
      { key: "access_token_secret", label: "Access Token Secret", placeholder: "Your Access Token Secret", secret: true },
    ],
  },
  {
    id: "instagram",
    name: "Instagram",
    description: "Post photos, stories, and reels to your Instagram business account.",
    icon: Camera,
    iconBg: "bg-pink-100 dark:bg-pink-500/20",
    iconColor: "text-pink-600 dark:text-pink-400",
    docsUrl: "https://developers.facebook.com/docs/instagram-api/",
    oauthProvider: "instagram",
    oauthSetupFields: [
      { key: "client_id", label: "App ID", placeholder: "Your Facebook/Instagram App ID" },
      { key: "client_secret", label: "App Secret", placeholder: "Your Facebook/Instagram App Secret", secret: true },
    ],
    oauthHelp: {
      title: "How to connect Instagram:",
      devUrl: "https://developers.facebook.com/apps/",
      devLabel: "Meta for Developers",
      callbackPath: "/api/v1/oauth/instagram/callback",
      steps: [
        "Create a Facebook App with Instagram Basic Display product",
        "Add the redirect URL below to your app's Valid OAuth Redirect URIs",
        "Copy your App ID and App Secret below",
      ],
    },
    fields: [],
    supportsInbound: false,
    supportsOutbound: true,
    defaultInbound: false,
    defaultOutbound: true,
  },
  {
    id: "facebook",
    name: "Facebook",
    description: "Publish posts and manage your Facebook business page.",
    icon: Globe,
    iconBg: "bg-blue-100 dark:bg-blue-500/20",
    iconColor: "text-blue-700 dark:text-blue-400",
    docsUrl: "https://developers.facebook.com/docs/pages-api/",
    oauthProvider: "facebook",
    oauthSetupFields: [
      { key: "client_id", label: "App ID", placeholder: "Your Facebook App ID" },
      { key: "client_secret", label: "App Secret", placeholder: "Your Facebook App Secret", secret: true },
    ],
    oauthHelp: {
      title: "How to connect Facebook:",
      devUrl: "https://developers.facebook.com/apps/",
      devLabel: "Meta for Developers",
      callbackPath: "/api/v1/oauth/facebook/callback",
      steps: [
        "Create a Facebook App with Facebook Login product",
        "Add the redirect URL below to your app's Valid OAuth Redirect URIs",
        "Copy your App ID and App Secret below",
      ],
    },
    fields: [],
    supportsInbound: false,
    supportsOutbound: true,
    defaultInbound: false,
    defaultOutbound: true,
  },
];

// ─── Helpers ────────────────────────────────────────────────────

function loadConnections(): SavedConnection[] {
  try {
    return JSON.parse(localStorage.getItem("contextuai-solo-connections") || "[]");
  } catch {
    return [];
  }
}

function saveConnections(connections: SavedConnection[]) {
  localStorage.setItem("contextuai-solo-connections", JSON.stringify(connections));
}

// ─── Main page ──────────────────────────────────────────────────

export default function ConnectionsPage() {
  const [connections, setConnections] = useState<SavedConnection[]>(loadConnections);
  const [editing, setEditing] = useState<ConnectionId | null>(null);
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [formInbound, setFormInbound] = useState(true);
  const [formOutbound, setFormOutbound] = useState(true);
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});
  const [testing, setTesting] = useState<ConnectionId | null>(null);
  const [oauthStatuses, setOauthStatuses] = useState<Record<string, OAuthStatus>>({});
  const [oauthLoading, setOauthLoading] = useState<ConnectionId | null>(null);
  const [triggers, setTriggers] = useState<Trigger[]>([]);

  const getConnection = (id: ConnectionId) => connections.find((c) => c.id === id);

  // Poll OAuth status for LinkedIn on mount + after OAuth redirect
  const refreshOAuthStatuses = useCallback(async () => {
    for (const conn of CONNECTIONS) {
      if (!conn.oauthProvider) continue;
      try {
        const status = await getOAuthStatus(conn.oauthProvider);
        setOauthStatuses((prev) => ({ ...prev, [conn.id]: status }));

        // Sync to local connections state if connected via OAuth
        if (status.connected) {
          setConnections((prev) => {
            const existing = prev.find((c) => c.id === conn.id);
            if (existing?.status === "connected") return prev;
            const updated = prev.filter((c) => c.id !== conn.id);
            updated.push({
              id: conn.id,
              config: {},
              inbound: conn.defaultInbound,
              outbound: conn.defaultOutbound,
              status: "connected",
              connectedAt: status.connected_at,
              profileName: status.profile_name,
            });
            saveConnections(updated);
            return updated;
          });
        }
      } catch {
        // Backend might not be running yet
      }
    }
  }, []);

  useEffect(() => {
    refreshOAuthStatuses();
    listTriggers().then(setTriggers).catch(() => {});

    // Poll every 3s while an OAuth flow might be in progress
    const interval = setInterval(refreshOAuthStatuses, 3000);
    return () => clearInterval(interval);
  }, [refreshOAuthStatuses]);

  const getTriggerForChannel = (channelType: string) =>
    triggers.find((t) => t.channel_type === channelType);

  const handleToggleAutoReply = async (channelType: string, currentTrigger?: Trigger) => {
    if (currentTrigger) {
      await updateTrigger(currentTrigger.trigger_id, { enabled: !currentTrigger.enabled });
    } else {
      await createTrigger({ channel_type: channelType, enabled: true });
    }
    const updated = await listTriggers();
    setTriggers(updated);
  };

  const handleToggleApproval = async (trigger: Trigger) => {
    await updateTrigger(trigger.trigger_id, { approval_required: !trigger.approval_required });
    const updated = await listTriggers();
    setTriggers(updated);
  };

  // handleDeleteTrigger available if needed
  void deleteTrigger;

  const handleEdit = (conn: ConnectionConfig) => {
    const saved = getConnection(conn.id);
    setFormData(saved?.config ?? {});
    setFormInbound(saved?.inbound ?? conn.defaultInbound);
    setFormOutbound(saved?.outbound ?? conn.defaultOutbound);
    setEditing(conn.id);
    setShowSecrets({});
  };

  const handleCancel = () => {
    setEditing(null);
    setFormData({});
    setShowSecrets({});
  };

  // Token-paste save (Telegram/Discord)
  const handleSave = async (connId: ConnectionId) => {
    setTesting(connId);
    await new Promise((r) => setTimeout(r, 1500));

    const hasValues = Object.values(formData).some((v) => v.trim());
    const status = hasValues ? "connected" : "disconnected";

    const updated = connections.filter((c) => c.id !== connId);
    if (hasValues) {
      updated.push({
        id: connId,
        config: { ...formData },
        inbound: formInbound,
        outbound: formOutbound,
        status,
        connectedAt: new Date().toISOString(),
      });
    }

    setConnections(updated);
    saveConnections(updated);
    setTesting(null);
    setEditing(null);
    setFormData({});
  };

  // OAuth flow: configure client creds, then open browser
  const handleOAuthConnect = async (conn: ConnectionConfig) => {
    if (!conn.oauthProvider) return;

    const clientId = formData.client_id?.trim();
    const clientSecret = formData.client_secret?.trim();

    if (!clientId || !clientSecret) return;

    setOauthLoading(conn.id);
    try {
      // Step 1: Save client credentials to backend
      await configureOAuthClient(conn.oauthProvider, clientId, clientSecret);

      // Step 2: Get authorization URL
      const { auth_url } = await getOAuthAuthorizeUrl(conn.oauthProvider);

      // Step 3: Open browser for user to authorize
      if ("__TAURI__" in window) {
        const { open } = await import("@tauri-apps/plugin-shell");
        await open(auth_url);
      } else {
        window.open(auth_url, "_blank");
      }

      // The callback is handled by the backend.
      // We poll for status changes via the useEffect interval above.
      setEditing(null);
      setFormData({});
    } catch (err) {
      console.error("OAuth initiation failed:", err);
    } finally {
      setOauthLoading(null);
    }
  };

  const handleDisconnect = async (conn: ConnectionConfig) => {
    // If OAuth provider, also disconnect on backend
    if (conn.oauthProvider) {
      try {
        await disconnectOAuth(conn.oauthProvider);
        setOauthStatuses((prev) => ({
          ...prev,
          [conn.id]: { ...prev[conn.id], connected: false, provider: conn.oauthProvider! },
        }));
      } catch {
        // proceed with local cleanup anyway
      }
    }

    const updated = connections.filter((c) => c.id !== conn.id);
    setConnections(updated);
    saveConnections(updated);
  };

  const inputCls = cn(
    "w-full px-4 py-2.5 rounded-xl text-sm",
    "bg-neutral-50 dark:bg-neutral-800",
    "border border-neutral-200 dark:border-neutral-700",
    "text-neutral-900 dark:text-white",
    "placeholder:text-neutral-400 dark:placeholder:text-neutral-500",
    "focus:outline-none focus:ring-2 focus:ring-primary-500/40 focus:border-primary-500",
    "transition-all"
  );

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-3xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white mb-1">
            Connections
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            Connect your favorite platforms to send and receive messages through AI.
          </p>
        </div>

        {/* Connection Cards */}
        <div className="space-y-4">
          {CONNECTIONS.map((conn) => {
            const Icon = conn.icon;
            const saved = getConnection(conn.id);
            const isEditing = editing === conn.id;
            const isTesting = testing === conn.id;
            const isOAuth = !!conn.oauthProvider;
            const oauthStatus = oauthStatuses[conn.id];
            const isConnected = saved?.status === "connected" || oauthStatus?.connected;
            const isOAuthLoading = oauthLoading === conn.id;

            return (
              <div
                key={conn.id}
                className={cn(
                  "rounded-2xl border transition-all",
                  isConnected
                    ? "border-green-200 dark:border-green-800/50 bg-green-50/30 dark:bg-green-500/5"
                    : "border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900"
                )}
              >
                {/* Card Header */}
                <div className="flex items-center justify-between p-5">
                  <div className="flex items-center gap-4">
                    <div className={cn("p-2.5 rounded-xl", conn.iconBg)}>
                      <Icon className={cn("w-5 h-5", conn.iconColor)} />
                    </div>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">
                          {conn.name}
                        </h3>
                        {isConnected && (
                          <>
                            <span className="flex items-center gap-1 text-[10px] font-medium text-green-600 dark:text-green-400 bg-green-100 dark:bg-green-500/20 px-2 py-0.5 rounded-full">
                              <Check className="w-3 h-3" /> Connected
                            </span>
                            {/* Show profile name for OAuth connections */}
                            {oauthStatus?.profile_name && (
                              <span className="flex items-center gap-1 text-[10px] font-medium text-blue-600 dark:text-blue-400 bg-blue-100 dark:bg-blue-500/15 px-2 py-0.5 rounded-full">
                                <User className="w-2.5 h-2.5" /> {oauthStatus.profile_name}
                              </span>
                            )}
                            {(saved?.inbound || conn.defaultInbound) && conn.supportsInbound && (
                              <span className="flex items-center gap-1 text-[10px] font-medium text-sky-600 dark:text-sky-400 bg-sky-100 dark:bg-sky-500/15 px-2 py-0.5 rounded-full">
                                <ArrowDownToLine className="w-2.5 h-2.5" /> Inbound
                              </span>
                            )}
                            {(saved?.outbound || conn.defaultOutbound) && conn.supportsOutbound && (
                              <span className="flex items-center gap-1 text-[10px] font-medium text-violet-600 dark:text-violet-400 bg-violet-100 dark:bg-violet-500/15 px-2 py-0.5 rounded-full">
                                <ArrowUpFromLine className="w-2.5 h-2.5" /> Outbound
                              </span>
                            )}
                          </>
                        )}
                      </div>
                      <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                        {conn.description}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <a
                      href={conn.docsUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-2 rounded-lg text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
                      title="Setup guide"
                    >
                      <ExternalLink className="w-4 h-4" />
                    </a>
                    {isConnected && !isEditing && (
                      <button
                        onClick={() => handleDisconnect(conn)}
                        className="p-2 rounded-lg text-neutral-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                        title="Disconnect"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                    {!isEditing && (
                      <button
                        onClick={() => handleEdit(conn)}
                        className={cn(
                          "px-4 py-2 rounded-xl text-xs font-medium transition-all",
                          isConnected
                            ? "bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-700"
                            : "bg-primary-500 text-white hover:bg-primary-600"
                        )}
                      >
                        {isConnected ? "Edit" : (
                          <span className="flex items-center gap-1">
                            <Plus className="w-3.5 h-3.5" /> Connect
                          </span>
                        )}
                      </button>
                    )}
                  </div>
                </div>

                {/* Expanded Edit Form */}
                {isEditing && (
                  <div className="px-5 pb-5 pt-0 border-t border-neutral-100 dark:border-neutral-800 mt-0">
                    <div className="pt-4 space-y-3">

                      {/* OAuth flow */}
                      {isOAuth && (
                        <>
                          {/* Provider-specific setup instructions */}
                          {conn.oauthHelp && (
                          <div className="flex items-start gap-3 p-3 bg-blue-50 dark:bg-blue-500/5 border border-blue-200 dark:border-blue-800/50 rounded-xl mb-1">
                            <Info className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
                            <div className="text-xs text-neutral-600 dark:text-neutral-400 leading-relaxed">
                              <p className="font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                                {conn.oauthHelp.title}
                              </p>
                              <ol className="list-decimal list-inside space-y-0.5">
                                {conn.oauthHelp.steps ? (
                                  conn.oauthHelp.steps.map((step, i) => <li key={i}>{step}</li>)
                                ) : (
                                  <li>
                                    Create an app at{" "}
                                    <a
                                      href={conn.oauthHelp.devUrl}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="text-blue-500 underline"
                                    >
                                      {conn.oauthHelp.devLabel}
                                    </a>
                                  </li>
                                )}
                                <li>
                                  Add <code className="bg-neutral-200 dark:bg-neutral-700 px-1 rounded text-[11px]">
                                    http://localhost:18741{conn.oauthHelp.callbackPath}
                                  </code> as an authorized redirect URL
                                </li>
                                <li>Copy your credentials below</li>
                                <li>Click &quot;Sign in with {conn.name}&quot; to authorize</li>
                              </ol>
                            </div>
                          </div>
                          )}

                          {conn.oauthSetupFields?.map((field) => (
                            <div key={field.key}>
                              <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-1.5">
                                {field.label}
                              </label>
                              <div className="relative">
                                <input
                                  type={field.secret && !showSecrets[field.key] ? "password" : "text"}
                                  value={formData[field.key] || ""}
                                  onChange={(e) =>
                                    setFormData({ ...formData, [field.key]: e.target.value })
                                  }
                                  placeholder={field.placeholder}
                                  className={inputCls}
                                />
                                {field.secret && (
                                  <button
                                    type="button"
                                    onClick={() =>
                                      setShowSecrets({
                                        ...showSecrets,
                                        [field.key]: !showSecrets[field.key],
                                      })
                                    }
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
                                  >
                                    {showSecrets[field.key] ? (
                                      <EyeOff className="w-4 h-4" />
                                    ) : (
                                      <Eye className="w-4 h-4" />
                                    )}
                                  </button>
                                )}
                              </div>
                            </div>
                          ))}
                        </>
                      )}

                      {/* Token-paste fields (Telegram/Discord) */}
                      {!isOAuth && conn.fields.map((field) => (
                        <div key={field.key}>
                          <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-1.5">
                            {field.label}
                          </label>
                          <div className="relative">
                            <input
                              type={field.secret && !showSecrets[field.key] ? "password" : "text"}
                              value={formData[field.key] || ""}
                              onChange={(e) =>
                                setFormData({ ...formData, [field.key]: e.target.value })
                              }
                              placeholder={field.placeholder}
                              className={inputCls}
                            />
                            {field.secret && (
                              <button
                                type="button"
                                onClick={() =>
                                  setShowSecrets({
                                    ...showSecrets,
                                    [field.key]: !showSecrets[field.key],
                                  })
                                }
                                className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
                              >
                                {showSecrets[field.key] ? (
                                  <EyeOff className="w-4 h-4" />
                                ) : (
                                  <Eye className="w-4 h-4" />
                                )}
                              </button>
                            )}
                          </div>
                        </div>
                      ))}

                      {/* Direction Controls (non-OAuth only — OAuth is outbound-only for LinkedIn) */}
                      {!isOAuth && (
                        <div className="pt-2">
                          <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-2">
                            Message Direction
                          </label>
                          <div className="flex gap-3">
                            {conn.supportsInbound && (
                              <button
                                type="button"
                                onClick={() => setFormInbound(!formInbound)}
                                className={cn(
                                  "flex items-center gap-2 px-4 py-2.5 rounded-xl border text-xs font-medium transition-all flex-1",
                                  formInbound
                                    ? "border-sky-300 dark:border-sky-700 bg-sky-50 dark:bg-sky-500/10 text-sky-700 dark:text-sky-300"
                                    : "border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-neutral-400"
                                )}
                              >
                                <ArrowDownToLine className="w-3.5 h-3.5" />
                                <div className="text-left">
                                  <div className="font-semibold">Inbound</div>
                                  <div className={cn(
                                    "text-[10px] mt-0.5",
                                    formInbound ? "text-sky-600/70 dark:text-sky-400/70" : "text-neutral-400"
                                  )}>
                                    Receive messages
                                  </div>
                                </div>
                                <div className={cn(
                                  "ml-auto w-4 h-4 rounded-full border-2 flex items-center justify-center transition-all",
                                  formInbound
                                    ? "border-sky-500 bg-sky-500"
                                    : "border-neutral-300 dark:border-neutral-600"
                                )}>
                                  {formInbound && <Check className="w-2.5 h-2.5 text-white" />}
                                </div>
                              </button>
                            )}
                            {conn.supportsOutbound && (
                              <button
                                type="button"
                                onClick={() => setFormOutbound(!formOutbound)}
                                className={cn(
                                  "flex items-center gap-2 px-4 py-2.5 rounded-xl border text-xs font-medium transition-all flex-1",
                                  formOutbound
                                    ? "border-violet-300 dark:border-violet-700 bg-violet-50 dark:bg-violet-500/10 text-violet-700 dark:text-violet-300"
                                    : "border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-neutral-400"
                                )}
                              >
                                <ArrowUpFromLine className="w-3.5 h-3.5" />
                                <div className="text-left">
                                  <div className="font-semibold">Outbound</div>
                                  <div className={cn(
                                    "text-[10px] mt-0.5",
                                    formOutbound ? "text-violet-600/70 dark:text-violet-400/70" : "text-neutral-400"
                                  )}>
                                    Send messages
                                  </div>
                                </div>
                                <div className={cn(
                                  "ml-auto w-4 h-4 rounded-full border-2 flex items-center justify-center transition-all",
                                  formOutbound
                                    ? "border-violet-500 bg-violet-500"
                                    : "border-neutral-300 dark:border-neutral-600"
                                )}>
                                  {formOutbound && <Check className="w-2.5 h-2.5 text-white" />}
                                </div>
                              </button>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Action buttons */}
                      <div className="flex items-center justify-end gap-2 pt-2">
                        <button
                          onClick={handleCancel}
                          className="px-4 py-2 rounded-xl text-xs font-medium text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300 transition-colors"
                        >
                          Cancel
                        </button>

                        {isOAuth ? (
                          <button
                            onClick={() => handleOAuthConnect(conn)}
                            disabled={isOAuthLoading || !formData.client_id?.trim() || !formData.client_secret?.trim()}
                            className="flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-semibold bg-primary-500 hover:bg-primary-600 text-white transition-all disabled:opacity-40"
                          >
                            {isOAuthLoading ? (
                              <>
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                Opening browser...
                              </>
                            ) : (
                              <>
                                <LogIn className="w-3.5 h-3.5" />
                                Sign in with {conn.name}
                              </>
                            )}
                          </button>
                        ) : (
                          <button
                            onClick={() => handleSave(conn.id)}
                            disabled={isTesting}
                            className="flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-semibold bg-primary-500 hover:bg-primary-600 text-white transition-all disabled:opacity-60"
                          >
                            {isTesting ? (
                              <>
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                Testing...
                              </>
                            ) : (
                              <>
                                <Check className="w-3.5 h-3.5" />
                                Save & Test
                              </>
                            )}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {/* Auto-Reply Trigger Config (shown for connected inbound channels) */}
                {isConnected && conn.supportsInbound && !isEditing && (() => {
                  const trigger = getTriggerForChannel(conn.id);
                  return (
                    <div className="px-5 pb-4 pt-0 border-t border-neutral-100 dark:border-neutral-800">
                      <div className="pt-3 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-neutral-600 dark:text-neutral-400">
                            Auto-Reply
                          </span>
                          {trigger?.enabled && (
                            <span className="text-[10px] font-medium text-green-600 dark:text-green-400 bg-green-100 dark:bg-green-500/20 px-2 py-0.5 rounded-full">
                              ON
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3">
                          {trigger?.enabled && (
                            <label className="flex items-center gap-1.5 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={trigger.approval_required}
                                onChange={() => handleToggleApproval(trigger)}
                                className="rounded border-neutral-300 text-primary-500 focus:ring-primary-500 w-3.5 h-3.5"
                              />
                              <span className="text-[11px] text-neutral-500">Require approval</span>
                            </label>
                          )}
                          <button
                            onClick={() => handleToggleAutoReply(conn.id, trigger)}
                            className={cn(
                              "relative inline-flex h-5 w-9 items-center rounded-full transition-colors",
                              trigger?.enabled
                                ? "bg-green-500"
                                : "bg-neutral-300 dark:bg-neutral-600"
                            )}
                          >
                            <span
                              className={cn(
                                "inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform",
                                trigger?.enabled ? "translate-x-[18px]" : "translate-x-[3px]"
                              )}
                            />
                          </button>
                        </div>
                      </div>
                      {trigger?.enabled && (
                        <p className="text-[11px] text-neutral-400 mt-1">
                          Incoming messages will be answered by AI.
                          {trigger.approval_required
                            ? " Replies go to the Approval Queue first."
                            : " Replies are sent immediately."}
                        </p>
                      )}
                    </div>
                  );
                })()}
              </div>
            );
          })}
        </div>

        {/* Info banner */}
        <div className="flex items-start gap-3 p-4 mt-6 bg-primary-50 dark:bg-primary-500/5 border border-primary-200 dark:border-primary-800/50 rounded-xl">
          <Info className="w-4 h-4 text-primary-500 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-neutral-600 dark:text-neutral-400 leading-relaxed">
            Telegram and Discord use bot tokens stored locally. Twitter/X uses API keys stored locally.
            LinkedIn, Instagram, and Facebook connect via OAuth2 — your browser opens to authorize, and
            tokens are stored securely in the local database. You can disconnect any time.
          </p>
        </div>
      </div>
    </div>
  );
}
