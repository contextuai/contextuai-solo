import { useState, useEffect, useCallback, useMemo } from "react";
import { cn } from "@/lib/utils";
import {
  Send,
  Linkedin,
  AtSign,
  Camera,
  Globe,
  Mail,
  MessageCircle,
  FileText,
  Plus,
  Edit3,
  Trash2,
  RefreshCw,
  Loader2,
  Check,
  Upload,
  Clock,
} from "lucide-react";
import { Button, Input, Textarea, Select, Badge, Dialog, Tabs } from "@/components/ui";
import {
  listChannels,
  createChannel,
  updateChannel,
  deleteChannel,
  toggleChannel,
  publish as publishOne,
  publishMulti,
  listDeliveries,
  type DistributionChannel,
  type DistributionChannelType,
  type Delivery,
  type PublishMetadata,
  type MultiPublishResult,
} from "@/lib/api/distribution-client";

// ─── Channel type meta ──────────────────────────────────────────

type ChannelTypeMeta = {
  label: string;
  icon: React.ElementType;
  color: string;
  bg: string;
};

const CHANNEL_META: Record<DistributionChannelType, ChannelTypeMeta> = {
  linkedin: {
    label: "LinkedIn",
    icon: Linkedin,
    color: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-500/15",
  },
  twitter: {
    label: "Twitter / X",
    icon: AtSign,
    color: "text-neutral-800 dark:text-neutral-200",
    bg: "bg-neutral-100 dark:bg-neutral-500/15",
  },
  instagram: {
    label: "Instagram",
    icon: Camera,
    color: "text-pink-600 dark:text-pink-400",
    bg: "bg-pink-100 dark:bg-pink-500/15",
  },
  facebook: {
    label: "Facebook",
    icon: Globe,
    color: "text-blue-700 dark:text-blue-400",
    bg: "bg-blue-100 dark:bg-blue-500/15",
  },
  blog: {
    label: "Blog",
    icon: FileText,
    color: "text-amber-700 dark:text-amber-400",
    bg: "bg-amber-100 dark:bg-amber-500/15",
  },
  email: {
    label: "Email",
    icon: Mail,
    color: "text-emerald-700 dark:text-emerald-400",
    bg: "bg-emerald-100 dark:bg-emerald-500/15",
  },
  slack: {
    label: "Slack",
    icon: MessageCircle,
    color: "text-violet-700 dark:text-violet-400",
    bg: "bg-violet-100 dark:bg-violet-500/15",
  },
};

type FieldDef = {
  key: string;
  label: string;
  placeholder?: string;
  secret?: boolean;
  type?: "text" | "textarea" | "select";
  options?: { value: string; label: string }[];
  helperText?: string;
};

const CHANNEL_FIELDS: Record<DistributionChannelType, FieldDef[]> = {
  linkedin: [
    { key: "access_token", label: "Access Token", placeholder: "LinkedIn OAuth access token", secret: true },
    {
      key: "author_urn",
      label: "Author URN",
      placeholder: "urn:li:person:xxxx or urn:li:organization:xxxx",
      helperText: "Person or organization URN this channel posts as.",
    },
  ],
  twitter: [
    { key: "api_key", label: "API Key", placeholder: "Consumer key", secret: true },
    { key: "api_secret", label: "API Secret", placeholder: "Consumer secret", secret: true },
    { key: "access_token", label: "Access Token", placeholder: "User access token", secret: true },
    { key: "access_token_secret", label: "Access Token Secret", placeholder: "User access token secret", secret: true },
    {
      key: "bearer_token",
      label: "Bearer Token (alternative to OAuth 1.0a)",
      placeholder: "App-only bearer token",
      secret: true,
      helperText: "Provide either the 4 OAuth 1.0a keys above OR a bearer token.",
    },
  ],
  instagram: [
    { key: "access_token", label: "Access Token", placeholder: "Graph API access token", secret: true },
    { key: "instagram_user_id", label: "Instagram User ID", placeholder: "e.g. 178414xxxxxxxx" },
  ],
  facebook: [
    { key: "page_id", label: "Page ID", placeholder: "e.g. 102xxxxxxx" },
    { key: "page_access_token", label: "Page Access Token", placeholder: "Long-lived page token", secret: true },
  ],
  blog: [
    { key: "api_url", label: "API URL", placeholder: "https://your-blog.com/api/posts" },
    { key: "api_key", label: "API Key", placeholder: "Bearer token / API key", secret: true },
    {
      key: "cms_type",
      label: "CMS Type",
      type: "select",
      options: [
        { value: "custom", label: "Custom" },
        { value: "ghost", label: "Ghost" },
        { value: "wordpress", label: "WordPress" },
      ],
    },
  ],
  email: [
    {
      key: "provider",
      label: "Provider",
      type: "select",
      options: [
        { value: "sendgrid", label: "SendGrid" },
        { value: "ses", label: "AWS SES" },
      ],
    },
    { key: "api_key", label: "API Key", placeholder: "Provider API key", secret: true },
    { key: "from_email", label: "From Email", placeholder: "noreply@example.com" },
  ],
  slack: [
    { key: "webhook_url", label: "Incoming Webhook URL", placeholder: "https://hooks.slack.com/services/...", secret: true },
  ],
};

const CHANNEL_TYPE_OPTIONS: { value: DistributionChannelType; label: string }[] = (
  Object.keys(CHANNEL_META) as DistributionChannelType[]
).map((k) => ({ value: k, label: CHANNEL_META[k].label }));

// ─── Helpers ────────────────────────────────────────────────────

function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function isMasked(value: unknown): boolean {
  return typeof value === "string" && value.includes("****");
}

// ─── Channel Form Dialog ────────────────────────────────────────

interface ChannelFormDialogProps {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
  existing: DistributionChannel | null;
}

function ChannelFormDialog({ open, onClose, onSaved, existing }: ChannelFormDialogProps) {
  const [channelType, setChannelType] = useState<DistributionChannelType>("linkedin");
  const [name, setName] = useState("");
  const [config, setConfig] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (existing) {
      setChannelType(existing.channel_type);
      setName(existing.name);
      const cfg: Record<string, string> = {};
      for (const [k, v] of Object.entries(existing.config ?? {})) {
        cfg[k] = v == null ? "" : String(v);
      }
      setConfig(cfg);
    } else {
      setChannelType("linkedin");
      setName("");
      setConfig({});
    }
    setError(null);
  }, [open, existing]);

  const fields = CHANNEL_FIELDS[channelType];
  const isEdit = !!existing;

  const handleTypeChange = (t: DistributionChannelType) => {
    setChannelType(t);
    setConfig({});
  };

  const handleSave = async () => {
    if (!name.trim()) {
      setError("Channel name is required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      // Only include non-empty config values, and skip masked placeholders
      // when editing (so we don't overwrite stored secrets with "****").
      const cleanedConfig: Record<string, string> = {};
      for (const field of fields) {
        const val = (config[field.key] ?? "").trim();
        if (!val) continue;
        if (isEdit && isMasked(val)) continue;
        cleanedConfig[field.key] = val;
      }

      if (isEdit && existing) {
        // Merge: if a field was left masked/empty, preserve it server-side by
        // only sending the fields the user actually changed.
        const updates: Record<string, unknown> = { name: name.trim() };
        if (Object.keys(cleanedConfig).length > 0) {
          // Merge user-provided values with the existing (masked) config.
          const merged: Record<string, unknown> = { ...existing.config };
          for (const [k, v] of Object.entries(cleanedConfig)) merged[k] = v;
          // Strip any masked leftovers so server doesn't re-store "****".
          for (const k of Object.keys(merged)) {
            if (isMasked(merged[k])) delete merged[k];
          }
          updates.config = merged;
        }
        await updateChannel(existing.channel_id, updates);
      } else {
        await createChannel({
          channel_type: channelType,
          name: name.trim(),
          config: cleanedConfig,
        });
      }
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save channel");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={isEdit ? "Edit Channel" : "Add Distribution Channel"}
      className="max-w-lg"
      actions={
        <>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> Saving
              </>
            ) : (
              <>
                <Check className="w-3.5 h-3.5" /> {isEdit ? "Save Changes" : "Create Channel"}
              </>
            )}
          </Button>
        </>
      }
    >
      <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-1">
        {!isEdit && (
          <Select
            label="Channel Type"
            value={channelType}
            onChange={(e) => handleTypeChange(e.target.value as DistributionChannelType)}
            options={CHANNEL_TYPE_OPTIONS}
          />
        )}

        <Input
          label="Channel Name"
          placeholder="e.g. Company LinkedIn, Marketing Slack"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />

        <div className="space-y-3 pt-1 border-t border-neutral-100 dark:border-neutral-800">
          <p className="text-xs font-medium text-neutral-500 dark:text-neutral-400 pt-3">
            {CHANNEL_META[channelType].label} Credentials
          </p>
          {fields.map((field) => {
            const val = config[field.key] ?? "";
            if (field.type === "select" && field.options) {
              return (
                <Select
                  key={field.key}
                  label={field.label}
                  value={val}
                  onChange={(e) => setConfig({ ...config, [field.key]: e.target.value })}
                  options={field.options}
                  placeholder="Select..."
                  helperText={field.helperText}
                />
              );
            }
            return (
              <Input
                key={field.key}
                label={field.label}
                type={field.secret ? "password" : "text"}
                placeholder={
                  isEdit && isMasked(val)
                    ? "Leave masked to keep existing value"
                    : field.placeholder
                }
                value={val}
                onChange={(e) => setConfig({ ...config, [field.key]: e.target.value })}
                helperText={field.helperText}
              />
            );
          })}
        </div>

        {error && (
          <div className="px-3 py-2 rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-xs text-red-700 dark:text-red-400">
            {error}
          </div>
        )}
      </div>
    </Dialog>
  );
}

// ─── Publish Dialog ─────────────────────────────────────────────

interface PublishDialogProps {
  open: boolean;
  onClose: () => void;
  channels: DistributionChannel[];
  onPublished: () => void;
}

function PublishDialog({ open, onClose, channels, onPublished }: PublishDialogProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [content, setContent] = useState("");
  const [title, setTitle] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [toEmails, setToEmails] = useState("");
  const [publishing, setPublishing] = useState(false);
  const [result, setResult] = useState<MultiPublishResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setSelected(new Set());
      setContent("");
      setTitle("");
      setImageUrl("");
      setToEmails("");
      setResult(null);
      setError(null);
    }
  }, [open]);

  const enabledChannels = channels.filter((c) => c.enabled);
  const selectedChannels = enabledChannels.filter((c) => selected.has(c.channel_id));
  const needsImage = selectedChannels.some((c) => c.channel_type === "instagram");
  const needsEmails = selectedChannels.some((c) => c.channel_type === "email");

  const toggleChannelSelection = (channelId: string) => {
    const next = new Set(selected);
    if (next.has(channelId)) next.delete(channelId);
    else next.add(channelId);
    setSelected(next);
  };

  const handlePublish = async () => {
    if (selected.size === 0 || !content.trim()) return;
    setPublishing(true);
    setError(null);
    setResult(null);

    const metadata: PublishMetadata = {};
    if (imageUrl.trim()) metadata.image_url = imageUrl.trim();
    if (toEmails.trim()) {
      metadata.to_emails = toEmails
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    }

    try {
      const ids = Array.from(selected);
      if (ids.length === 1) {
        const delivery = await publishOne({
          channel_id: ids[0],
          content: content.trim(),
          title: title.trim() || undefined,
          metadata: Object.keys(metadata).length ? metadata : undefined,
        });
        setResult({
          total_channels: 1,
          published: delivery.status === "published" ? 1 : 0,
          failed: delivery.status === "published" ? 0 : 1,
          deliveries: [delivery],
        });
      } else {
        const multi = await publishMulti({
          channel_ids: ids,
          content: content.trim(),
          title: title.trim() || undefined,
          metadata: Object.keys(metadata).length ? metadata : undefined,
        });
        setResult(multi);
      }
      onPublished();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Publish failed");
    } finally {
      setPublishing(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Publish Content"
      className="max-w-xl"
      actions={
        <>
          <Button variant="ghost" onClick={onClose} disabled={publishing}>
            {result ? "Close" : "Cancel"}
          </Button>
          {!result && (
            <Button
              onClick={handlePublish}
              disabled={publishing || selected.size === 0 || !content.trim()}
            >
              {publishing ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> Publishing
                </>
              ) : (
                <>
                  <Send className="w-3.5 h-3.5" /> Publish to {selected.size || 0}
                </>
              )}
            </Button>
          )}
        </>
      }
    >
      <div className="space-y-4 max-h-[65vh] overflow-y-auto pr-1">
        {result ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Badge variant="success">{result.published} published</Badge>
              {result.failed > 0 && (
                <Badge variant="error">{result.failed} failed</Badge>
              )}
            </div>
            <div className="space-y-2">
              {result.deliveries.map((d) => {
                const meta = CHANNEL_META[d.channel_type];
                const Icon = meta?.icon ?? Send;
                return (
                  <div
                    key={d.delivery_id}
                    className="flex items-start gap-3 p-3 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-800/50"
                  >
                    <div className={cn("p-1.5 rounded-lg", meta?.bg)}>
                      <Icon className={cn("w-4 h-4", meta?.color)} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-neutral-900 dark:text-white">
                          {d.channel_name || meta?.label}
                        </span>
                        {d.status === "published" ? (
                          <Badge variant="success" dot>
                            published
                          </Badge>
                        ) : (
                          <Badge variant="error" dot>
                            {d.status}
                          </Badge>
                        )}
                      </div>
                      {d.status !== "published" && d.result?.error && (
                        <p className="text-xs text-red-600 dark:text-red-400 mt-1 break-words">
                          {String(d.result.error).slice(0, 300)}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <>
            {/* Channel picker */}
            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                Channels
              </label>
              {enabledChannels.length === 0 ? (
                <div className="text-xs text-neutral-500 dark:text-neutral-400 px-3 py-3 rounded-lg bg-neutral-50 dark:bg-neutral-800">
                  No enabled channels. Add one to get started.
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {enabledChannels.map((c) => {
                    const meta = CHANNEL_META[c.channel_type];
                    const Icon = meta.icon;
                    const active = selected.has(c.channel_id);
                    return (
                      <button
                        key={c.channel_id}
                        type="button"
                        onClick={() => toggleChannelSelection(c.channel_id)}
                        className={cn(
                          "flex items-center gap-2 px-3 py-2.5 rounded-xl border text-left text-sm transition-all",
                          active
                            ? "border-primary-500 bg-primary-50 dark:bg-primary-500/10"
                            : "border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800/60 hover:border-neutral-300 dark:hover:border-neutral-600"
                        )}
                      >
                        <div className={cn("p-1.5 rounded-lg", meta.bg)}>
                          <Icon className={cn("w-4 h-4", meta.color)} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-medium text-neutral-900 dark:text-white truncate">
                            {c.name}
                          </div>
                          <div className="text-[10px] text-neutral-500 dark:text-neutral-400">
                            {meta.label}
                          </div>
                        </div>
                        <div
                          className={cn(
                            "w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0",
                            active
                              ? "border-primary-500 bg-primary-500"
                              : "border-neutral-300 dark:border-neutral-600"
                          )}
                        >
                          {active && <Check className="w-2.5 h-2.5 text-white" />}
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            <Input
              label="Title (optional)"
              placeholder="Subject line, blog post title, etc."
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />

            <Textarea
              label="Content"
              placeholder="What do you want to publish?"
              rows={6}
              value={content}
              onChange={(e) => setContent(e.target.value)}
            />

            {needsImage && (
              <Input
                label="Image URL"
                placeholder="https://example.com/image.jpg"
                value={imageUrl}
                onChange={(e) => setImageUrl(e.target.value)}
                helperText="Instagram requires an image_url."
              />
            )}

            {needsEmails && (
              <Input
                label="To Emails (comma-separated)"
                placeholder="alice@example.com, bob@example.com"
                value={toEmails}
                onChange={(e) => setToEmails(e.target.value)}
              />
            )}

            {error && (
              <div className="px-3 py-2 rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-xs text-red-700 dark:text-red-400">
                {error}
              </div>
            )}
          </>
        )}
      </div>
    </Dialog>
  );
}

// ─── Main Page ──────────────────────────────────────────────────

type TabId = "channels" | "deliveries";

export default function DistributionPage() {
  const [activeTab, setActiveTab] = useState<TabId>("channels");
  const [channels, setChannels] = useState<DistributionChannel[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<DistributionChannel | null>(null);
  const [publishOpen, setPublishOpen] = useState(false);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadChannels = useCallback(async () => {
    try {
      const data = await listChannels();
      setChannels(data);
    } catch (e) {
      console.warn("Failed to load channels:", e);
    }
  }, []);

  const loadDeliveries = useCallback(async () => {
    try {
      const data = await listDeliveries(undefined, 100);
      setDeliveries(data);
    } catch (e) {
      console.warn("Failed to load deliveries:", e);
    }
  }, []);

  const refreshAll = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([loadChannels(), loadDeliveries()]);
    } finally {
      setLoading(false);
    }
  }, [loadChannels, loadDeliveries]);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  const handleToggle = async (ch: DistributionChannel) => {
    setTogglingId(ch.channel_id);
    try {
      await toggleChannel(ch.channel_id, !ch.enabled);
      await loadChannels();
    } catch (e) {
      console.warn("Toggle failed:", e);
    } finally {
      setTogglingId(null);
    }
  };

  const handleDelete = async (ch: DistributionChannel) => {
    if (!confirm(`Delete channel "${ch.name}"? This cannot be undone.`)) return;
    setDeletingId(ch.channel_id);
    try {
      await deleteChannel(ch.channel_id);
      await loadChannels();
    } catch (e) {
      console.warn("Delete failed:", e);
    } finally {
      setDeletingId(null);
    }
  };

  const handleEdit = (ch: DistributionChannel) => {
    setEditing(ch);
    setFormOpen(true);
  };

  const handleAdd = () => {
    setEditing(null);
    setFormOpen(true);
  };

  const enabledCount = useMemo(() => channels.filter((c) => c.enabled).length, [channels]);

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-5xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-primary-100 dark:bg-primary-500/15">
              <Send className="w-5 h-5 text-primary-600 dark:text-primary-400" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-neutral-900 dark:text-white">
                Distribution
              </h1>
              <p className="text-sm text-neutral-500">
                Publish content to LinkedIn, Twitter, Slack, email, blogs, and more.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={refreshAll}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
            >
              <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
              Refresh
            </button>
            <Button
              onClick={() => setPublishOpen(true)}
              disabled={enabledCount === 0}
              size="sm"
            >
              <Upload className="w-3.5 h-3.5" />
              Publish
            </Button>
            <Button onClick={handleAdd} variant="secondary" size="sm">
              <Plus className="w-3.5 h-3.5" />
              Add channel
            </Button>
          </div>
        </div>

        {/* Tabs */}
        <div className="mb-6">
          <Tabs
            tabs={[
              { id: "channels", label: `Channels (${channels.length})` },
              { id: "deliveries", label: `Delivery History (${deliveries.length})` },
            ]}
            activeTab={activeTab}
            onChange={(id) => setActiveTab(id as TabId)}
            className="w-fit"
          />
        </div>

        {/* Channels tab */}
        {activeTab === "channels" && (
          <>
            {loading && channels.length === 0 ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-6 h-6 text-neutral-400 animate-spin" />
              </div>
            ) : channels.length === 0 ? (
              <div className="text-center py-16 rounded-2xl border border-dashed border-neutral-200 dark:border-neutral-800 bg-neutral-50/50 dark:bg-neutral-800/20">
                <Send className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
                <p className="text-neutral-600 dark:text-neutral-400 font-medium">
                  No distribution channels yet
                </p>
                <p className="text-sm text-neutral-500 mt-1">
                  Add a channel to start publishing AI-generated content.
                </p>
                <div className="mt-4">
                  <Button onClick={handleAdd} size="sm">
                    <Plus className="w-3.5 h-3.5" />
                    Add your first channel
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                {channels.map((ch) => {
                  const meta = CHANNEL_META[ch.channel_type];
                  const Icon = meta.icon;
                  return (
                    <div
                      key={ch.channel_id}
                      className={cn(
                        "rounded-2xl border p-5 bg-white dark:bg-neutral-900 transition-colors",
                        ch.enabled
                          ? "border-neutral-200 dark:border-neutral-800"
                          : "border-neutral-200 dark:border-neutral-800 opacity-70"
                      )}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-start gap-4 min-w-0 flex-1">
                          <div className={cn("p-2.5 rounded-xl flex-shrink-0", meta.bg)}>
                            <Icon className={cn("w-5 h-5", meta.color)} />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <h3 className="text-sm font-semibold text-neutral-900 dark:text-white truncate">
                                {ch.name}
                              </h3>
                              <Badge variant="info">{meta.label}</Badge>
                              {ch.enabled ? (
                                <Badge variant="success" dot>
                                  enabled
                                </Badge>
                              ) : (
                                <Badge variant="default" dot>
                                  disabled
                                </Badge>
                              )}
                            </div>
                            <div className="flex items-center gap-4 mt-1.5 text-xs text-neutral-500 dark:text-neutral-400">
                              <span>
                                <span className="font-medium text-neutral-700 dark:text-neutral-300">
                                  {ch.publish_count}
                                </span>{" "}
                                {ch.publish_count === 1 ? "post" : "posts"}
                              </span>
                              <span className="flex items-center gap-1">
                                <Clock className="w-3 h-3" />
                                Last published {timeAgo(ch.last_published_at)}
                              </span>
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center gap-1 flex-shrink-0">
                          <button
                            onClick={() => handleToggle(ch)}
                            disabled={togglingId === ch.channel_id}
                            className={cn(
                              "relative inline-flex h-5 w-9 items-center rounded-full transition-colors mx-2",
                              ch.enabled
                                ? "bg-green-500"
                                : "bg-neutral-300 dark:bg-neutral-600"
                            )}
                            title={ch.enabled ? "Disable" : "Enable"}
                          >
                            <span
                              className={cn(
                                "inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform",
                                ch.enabled ? "translate-x-[18px]" : "translate-x-[3px]"
                              )}
                            />
                          </button>
                          <button
                            onClick={() => handleEdit(ch)}
                            className="p-2 rounded-lg text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
                            title="Edit"
                          >
                            <Edit3 className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleDelete(ch)}
                            disabled={deletingId === ch.channel_id}
                            className="p-2 rounded-lg text-neutral-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                            title="Delete"
                          >
                            {deletingId === ch.channel_id ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <Trash2 className="w-4 h-4" />
                            )}
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}

        {/* Deliveries tab */}
        {activeTab === "deliveries" && (
          <>
            {loading && deliveries.length === 0 ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-6 h-6 text-neutral-400 animate-spin" />
              </div>
            ) : deliveries.length === 0 ? (
              <div className="text-center py-16 rounded-2xl border border-dashed border-neutral-200 dark:border-neutral-800 bg-neutral-50/50 dark:bg-neutral-800/20">
                <Clock className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
                <p className="text-neutral-600 dark:text-neutral-400 font-medium">
                  No deliveries yet
                </p>
                <p className="text-sm text-neutral-500 mt-1">
                  Publishing activity will show up here.
                </p>
              </div>
            ) : (
              <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-neutral-50 dark:bg-neutral-800/50 text-xs text-neutral-500 dark:text-neutral-400">
                    <tr>
                      <th className="text-left font-medium px-4 py-2.5">When</th>
                      <th className="text-left font-medium px-4 py-2.5">Channel</th>
                      <th className="text-left font-medium px-4 py-2.5">Title</th>
                      <th className="text-left font-medium px-4 py-2.5">Length</th>
                      <th className="text-left font-medium px-4 py-2.5">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deliveries.map((d) => {
                      const meta = CHANNEL_META[d.channel_type];
                      const Icon = meta?.icon ?? Send;
                      const truncTitle = d.title
                        ? d.title.length > 60
                          ? d.title.slice(0, 60) + "…"
                          : d.title
                        : "—";
                      return (
                        <tr
                          key={d.delivery_id}
                          className="border-t border-neutral-100 dark:border-neutral-800"
                        >
                          <td className="px-4 py-3 text-xs text-neutral-500 whitespace-nowrap">
                            {timeAgo(d.timestamp)}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <div className={cn("p-1 rounded-md", meta?.bg)}>
                                <Icon className={cn("w-3.5 h-3.5", meta?.color)} />
                              </div>
                              <span className="text-xs font-medium text-neutral-800 dark:text-neutral-200 truncate max-w-[180px]">
                                {d.channel_name || meta?.label || d.channel_type}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-xs text-neutral-600 dark:text-neutral-400">
                            {truncTitle}
                          </td>
                          <td className="px-4 py-3 text-xs text-neutral-500">
                            {d.content_length}
                          </td>
                          <td className="px-4 py-3">
                            {d.status === "published" ? (
                              <Badge variant="success" dot>
                                published
                              </Badge>
                            ) : d.status === "failed" ? (
                              <Badge variant="error" dot>
                                failed
                              </Badge>
                            ) : (
                              <Badge variant="warning" dot>
                                {d.status}
                              </Badge>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {/* Info banner */}
        <div className="flex items-start gap-3 p-4 mt-6 bg-primary-50 dark:bg-primary-500/5 border border-primary-200 dark:border-primary-800/50 rounded-xl">
          <Send className="w-4 h-4 text-primary-500 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-neutral-600 dark:text-neutral-400 leading-relaxed">
            Channels store credentials locally and publish directly to each platform&apos;s API.
            Credentials are masked in the UI once saved — leave fields blank while editing to preserve
            existing values. Use the <span className="font-medium">Connections</span> page for inbound
            conversations; this page is for outbound publishing.
          </p>
        </div>

        {/* Dialogs */}
        <ChannelFormDialog
          open={formOpen}
          onClose={() => setFormOpen(false)}
          onSaved={loadChannels}
          existing={editing}
        />
        <PublishDialog
          open={publishOpen}
          onClose={() => setPublishOpen(false)}
          channels={channels}
          onPublished={refreshAll}
        />
      </div>
    </div>
  );
}
