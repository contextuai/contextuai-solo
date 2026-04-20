import { useState, useEffect, useCallback, useMemo } from "react";
import { cn } from "@/lib/utils";
import {
  Clock,
  Plus,
  Play,
  Edit3,
  Trash2,
  Loader2,
  RefreshCw,
  ChevronDown,
  Send,
  Users,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";
import { Dialog, Button, Input, Textarea } from "@/components/ui";
import {
  listScheduledJobs,
  createScheduledJob,
  updateScheduledJob,
  deleteScheduledJob,
  runScheduledJobNow,
  toggleScheduledJob,
  validateCron,
  prettifyCron,
  type ScheduledJob,
  type ScheduledJobType,
} from "@/lib/api/scheduled-jobs-client";
import { listChannels, type DistributionChannel } from "@/lib/api/distribution-client";
import { crewsApi, type Crew } from "@/lib/api/crews-client";

// ─── Cron presets ────────────────────────────────────────────────

const CRON_PRESETS: { label: string; expr: string }[] = [
  { label: "Every day at 9am", expr: "0 9 * * *" },
  { label: "Every weekday at 9am", expr: "0 9 * * 1-5" },
  { label: "Every hour", expr: "0 * * * *" },
  { label: "Every Monday at 9am", expr: "0 9 * * 1" },
  { label: "Every day at 8am", expr: "0 8 * * *" },
  { label: "Every 15 minutes", expr: "*/15 * * * *" },
];

function guessLocalTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function formatDateTime(iso?: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

// ─── Job card ────────────────────────────────────────────────────

function JobCard({
  job,
  onRun,
  onToggle,
  onEdit,
  onDelete,
  busy,
}: {
  job: ScheduledJob;
  onRun: (j: ScheduledJob) => void;
  onToggle: (j: ScheduledJob) => void;
  onEdit: (j: ScheduledJob) => void;
  onDelete: (j: ScheduledJob) => void;
  busy: boolean;
}) {
  const typeBadge =
    job.job_type === "post"
      ? "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400"
      : "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400";

  const TypeIcon = job.job_type === "post" ? Send : Users;

  const statusChip = job.last_run_status === "success"
    ? { icon: CheckCircle2, cls: "text-green-600 dark:text-green-400", label: "Last run: success" }
    : job.last_run_status === "failed"
    ? { icon: AlertCircle, cls: "text-red-600 dark:text-red-400", label: "Last run: failed" }
    : null;

  return (
    <div className="rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800/50 p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-neutral-900 dark:text-white truncate">
              {job.name}
            </span>
            <span
              className={cn(
                "inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full font-medium",
                typeBadge
              )}
            >
              <TypeIcon className="w-3 h-3" />
              {job.job_type}
            </span>
            {!job.enabled && (
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-neutral-200 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-300">
                paused
              </span>
            )}
          </div>

          <div className="mt-1.5 text-xs text-neutral-500 dark:text-neutral-400 flex items-center gap-3 flex-wrap">
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {prettifyCron(job.cron)}
            </span>
            <span className="text-neutral-400">·</span>
            <span>{job.timezone}</span>
            <span className="text-neutral-400">·</span>
            <span>Next: {formatDateTime(job.next_run_at)}</span>
            <span className="text-neutral-400">·</span>
            <span>Runs: {job.run_count}</span>
          </div>

          {statusChip && (
            <div className={cn("mt-1.5 text-xs flex items-center gap-1", statusChip.cls)}>
              <statusChip.icon className="w-3 h-3" />
              {statusChip.label}
              {job.last_run_error && (
                <span className="text-neutral-500 dark:text-neutral-400 truncate max-w-[320px]">
                  — {job.last_run_error}
                </span>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={() => onRun(job)}
            disabled={busy}
            title="Run now"
            className="p-2 rounded-lg text-neutral-500 hover:text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-900/20 disabled:opacity-40"
          >
            <Play className="w-4 h-4" />
          </button>
          <button
            onClick={() => onToggle(job)}
            disabled={busy}
            title={job.enabled ? "Pause" : "Resume"}
            className={cn(
              "px-2 py-1 rounded-lg text-xs font-medium transition-colors",
              job.enabled
                ? "text-neutral-600 hover:bg-neutral-100 dark:hover:bg-neutral-700 dark:text-neutral-300"
                : "text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20 dark:text-green-400"
            )}
          >
            {job.enabled ? "Pause" : "Resume"}
          </button>
          <button
            onClick={() => onEdit(job)}
            title="Edit"
            className="p-2 rounded-lg text-neutral-500 hover:text-neutral-800 hover:bg-neutral-100 dark:hover:bg-neutral-700 dark:hover:text-white"
          >
            <Edit3 className="w-4 h-4" />
          </button>
          <button
            onClick={() => onDelete(job)}
            title="Delete"
            className="p-2 rounded-lg text-neutral-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Dialog ──────────────────────────────────────────────────────

interface JobFormState {
  name: string;
  job_type: ScheduledJobType;
  cron: string;
  timezone: string;
  channel_id: string;
  content: string;
  title: string;
  metadata_json: string;
  crew_id: string;
  crew_input_json: string;
  enabled: boolean;
}

function emptyForm(): JobFormState {
  return {
    name: "",
    job_type: "post",
    cron: "0 9 * * *",
    timezone: guessLocalTimezone(),
    channel_id: "",
    content: "",
    title: "",
    metadata_json: "",
    crew_id: "",
    crew_input_json: "",
    enabled: true,
  };
}

function jobToForm(j: ScheduledJob): JobFormState {
  return {
    name: j.name,
    job_type: j.job_type,
    cron: j.cron,
    timezone: j.timezone,
    channel_id: j.channel_id ?? "",
    content: j.content ?? "",
    title: j.title ?? "",
    metadata_json: j.metadata ? JSON.stringify(j.metadata, null, 2) : "",
    crew_id: j.crew_id ?? "",
    crew_input_json: j.crew_input ? JSON.stringify(j.crew_input, null, 2) : "",
    enabled: j.enabled,
  };
}

function JobDialog({
  open,
  editing,
  channels,
  crews,
  onClose,
  onSaved,
}: {
  open: boolean;
  editing: ScheduledJob | null;
  channels: DistributionChannel[];
  crews: Crew[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<JobFormState>(emptyForm());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showMetadata, setShowMetadata] = useState(false);
  const [previewRuns, setPreviewRuns] = useState<string[]>([]);
  const [previewError, setPreviewError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setForm(editing ? jobToForm(editing) : emptyForm());
    setError(null);
    setShowMetadata(false);
    setPreviewRuns([]);
    setPreviewError(null);
  }, [open, editing]);

  // Cron preview — debounced
  useEffect(() => {
    if (!open) return;
    const handle = setTimeout(async () => {
      try {
        const result = await validateCron(form.cron, form.timezone, 5);
        setPreviewRuns(result.next_runs);
        setPreviewError(null);
      } catch (err) {
        setPreviewRuns([]);
        setPreviewError((err as Error).message ?? "Invalid cron");
      }
    }, 400);
    return () => clearTimeout(handle);
  }, [form.cron, form.timezone, open]);

  const update = <K extends keyof JobFormState>(key: K, value: JobFormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const handleSave = async () => {
    setError(null);

    if (!form.name.trim()) {
      setError("Name is required");
      return;
    }
    if (form.job_type === "post") {
      if (!form.channel_id) return setError("Select a channel");
      if (!form.content.trim()) return setError("Content is required");
    } else {
      if (!form.crew_id) return setError("Select a crew");
    }

    let metadata: Record<string, unknown> | undefined;
    if (form.metadata_json.trim()) {
      try {
        metadata = JSON.parse(form.metadata_json);
      } catch {
        return setError("Metadata is not valid JSON");
      }
    }

    let crewInput: Record<string, unknown> | undefined;
    if (form.crew_input_json.trim()) {
      try {
        crewInput = JSON.parse(form.crew_input_json);
      } catch {
        return setError("Crew input is not valid JSON");
      }
    }

    const payload = {
      name: form.name.trim(),
      job_type: form.job_type,
      cron: form.cron.trim(),
      timezone: form.timezone || "UTC",
      enabled: form.enabled,
      ...(form.job_type === "post"
        ? {
            channel_id: form.channel_id,
            content: form.content,
            title: form.title || undefined,
            metadata,
          }
        : {
            crew_id: form.crew_id,
            crew_input: crewInput,
          }),
    };

    setSaving(true);
    try {
      if (editing) {
        await updateScheduledJob(editing.id, payload);
      } else {
        await createScheduledJob(payload);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError((err as Error).message ?? "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const actions = (
    <>
      <Button variant="secondary" onClick={onClose} disabled={saving}>
        Cancel
      </Button>
      <Button onClick={handleSave} disabled={saving}>
        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : editing ? "Save changes" : "Create"}
      </Button>
    </>
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={editing ? "Edit scheduled job" : "New scheduled job"}
      actions={actions}
      className="max-w-2xl"
    >
      <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
        {error && (
          <div className="rounded-lg border border-red-200 dark:border-red-800/40 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-700 dark:text-red-300">
            {error}
          </div>
        )}

        {/* Name */}
        <div>
          <label className="text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-1 block">
            Name
          </label>
          <Input
            value={form.name}
            onChange={(e) => update("name", e.target.value)}
            placeholder="Daily LinkedIn post"
          />
        </div>

        {/* Type selector */}
        <div>
          <label className="text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-1 block">
            Type
          </label>
          <div className="grid grid-cols-2 gap-2">
            {(["post", "crew"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => update("job_type", t)}
                className={cn(
                  "flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium transition-colors",
                  form.job_type === t
                    ? "border-primary-500 bg-primary-50 dark:bg-primary-500/10 text-primary-700 dark:text-primary-400"
                    : "border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800"
                )}
              >
                {t === "post" ? <Send className="w-4 h-4" /> : <Users className="w-4 h-4" />}
                {t === "post" ? "Publish post" : "Run crew"}
              </button>
            ))}
          </div>
        </div>

        {/* Post fields */}
        {form.job_type === "post" && (
          <>
            <div>
              <label className="text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-1 block">
                Channel
              </label>
              <select
                value={form.channel_id}
                onChange={(e) => update("channel_id", e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl text-sm bg-neutral-50 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 text-neutral-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500/40 focus:border-primary-500"
              >
                <option value="">Select a channel…</option>
                {channels.map((c) => (
                  <option key={c.channel_id} value={c.channel_id}>
                    {c.name} ({c.channel_type})
                  </option>
                ))}
              </select>
              {channels.length === 0 && (
                <p className="text-xs text-neutral-500 mt-1">
                  No distribution channels yet — add one in Connections.
                </p>
              )}
            </div>

            <div>
              <label className="text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-1 block">
                Title (optional)
              </label>
              <Input
                value={form.title}
                onChange={(e) => update("title", e.target.value)}
                placeholder="Optional post title"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-1 block">
                Content
              </label>
              <Textarea
                value={form.content}
                onChange={(e) => update("content", e.target.value)}
                rows={5}
                placeholder="The post body that will be published each time the job fires."
              />
            </div>

            <div>
              <button
                type="button"
                onClick={() => setShowMetadata((v) => !v)}
                className="text-xs text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300 flex items-center gap-1"
              >
                <ChevronDown
                  className={cn(
                    "w-3 h-3 transition-transform",
                    showMetadata && "rotate-180"
                  )}
                />
                Advanced: metadata JSON
              </button>
              {showMetadata && (
                <Textarea
                  value={form.metadata_json}
                  onChange={(e) => update("metadata_json", e.target.value)}
                  rows={3}
                  placeholder='{"image_url": "https://..."}'
                  className="mt-2 font-mono text-xs"
                />
              )}
            </div>
          </>
        )}

        {/* Crew fields */}
        {form.job_type === "crew" && (
          <>
            <div>
              <label className="text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-1 block">
                Crew
              </label>
              <select
                value={form.crew_id}
                onChange={(e) => update("crew_id", e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl text-sm bg-neutral-50 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 text-neutral-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500/40 focus:border-primary-500"
              >
                <option value="">Select a crew…</option>
                {crews.map((c) => (
                  <option key={c.crew_id} value={c.crew_id}>
                    {c.name}
                  </option>
                ))}
              </select>
              {crews.length === 0 && (
                <p className="text-xs text-neutral-500 mt-1">
                  No crews yet — create one in Crews.
                </p>
              )}
            </div>

            <div>
              <label className="text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-1 block">
                Crew input JSON (optional)
              </label>
              <Textarea
                value={form.crew_input_json}
                onChange={(e) => update("crew_input_json", e.target.value)}
                rows={4}
                placeholder='{"topic": "weekly news digest"}'
                className="font-mono text-xs"
              />
            </div>
          </>
        )}

        {/* Cron presets */}
        <div>
          <label className="text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-1 block">
            Schedule
          </label>
          <div className="flex flex-wrap gap-1.5 mb-2">
            {CRON_PRESETS.map((p) => (
              <button
                key={p.expr}
                type="button"
                onClick={() => update("cron", p.expr)}
                className={cn(
                  "px-2.5 py-1 rounded-md text-xs border transition-colors",
                  form.cron === p.expr
                    ? "border-primary-500 bg-primary-50 dark:bg-primary-500/10 text-primary-700 dark:text-primary-400"
                    : "border-neutral-200 dark:border-neutral-700 text-neutral-600 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-800"
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
          <Input
            value={form.cron}
            onChange={(e) => update("cron", e.target.value)}
            placeholder="0 9 * * *"
            className="font-mono text-sm"
          />
          <p className="text-[11px] text-neutral-500 mt-1">
            Standard 5-field cron: minute hour day-of-month month day-of-week
          </p>
        </div>

        {/* Timezone */}
        <div>
          <label className="text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-1 block">
            Timezone
          </label>
          <Input
            value={form.timezone}
            onChange={(e) => update("timezone", e.target.value)}
            placeholder="UTC"
          />
        </div>

        {/* Preview */}
        <div className="rounded-lg border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900/50 px-3 py-2">
          <p className="text-xs font-medium text-neutral-600 dark:text-neutral-400 mb-1">
            Next 5 runs
          </p>
          {previewError ? (
            <p className="text-xs text-red-600 dark:text-red-400">{previewError}</p>
          ) : previewRuns.length === 0 ? (
            <p className="text-xs text-neutral-400">—</p>
          ) : (
            <ul className="text-xs text-neutral-700 dark:text-neutral-300 space-y-0.5">
              {previewRuns.map((r) => (
                <li key={r} className="font-mono">
                  {formatDateTime(r)}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Dialog>
  );
}

// ─── Page ────────────────────────────────────────────────────────

export default function SchedulePage() {
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [channels, setChannels] = useState<DistributionChannel[]>([]);
  const [crews, setCrews] = useState<Crew[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<ScheduledJob | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const loadJobs = useCallback(async () => {
    try {
      const result = await listScheduledJobs(0, 200);
      setJobs(result.jobs);
    } catch (err) {
      console.warn("Failed to load scheduled jobs:", err);
    }
  }, []);

  const loadChannelsAndCrews = useCallback(async () => {
    try {
      const [ch, cr] = await Promise.all([listChannels(), crewsApi.list()]);
      setChannels(ch);
      setCrews(cr);
    } catch (err) {
      console.warn("Failed to load channels/crews:", err);
    }
  }, []);

  useEffect(() => {
    (async () => {
      setLoading(true);
      await Promise.all([loadJobs(), loadChannelsAndCrews()]);
      setLoading(false);
    })();
  }, [loadJobs, loadChannelsAndCrews]);

  const openCreate = () => {
    setEditing(null);
    setDialogOpen(true);
  };

  const openEdit = (j: ScheduledJob) => {
    setEditing(j);
    setDialogOpen(true);
  };

  const handleRun = async (j: ScheduledJob) => {
    setBusyId(j.id);
    try {
      await runScheduledJobNow(j.id);
      await loadJobs();
    } catch (err) {
      console.warn("Run-now failed:", err);
    } finally {
      setBusyId(null);
    }
  };

  const handleToggle = async (j: ScheduledJob) => {
    setBusyId(j.id);
    try {
      await toggleScheduledJob(j.id);
      await loadJobs();
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (j: ScheduledJob) => {
    if (!window.confirm(`Delete scheduled job "${j.name}"?`)) return;
    setBusyId(j.id);
    try {
      await deleteScheduledJob(j.id);
      await loadJobs();
    } finally {
      setBusyId(null);
    }
  };

  const sortedJobs = useMemo(
    () =>
      [...jobs].sort((a, b) =>
        (a.next_run_at ?? "").localeCompare(b.next_run_at ?? "")
      ),
    [jobs]
  );

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-primary-100 dark:bg-primary-500/20">
              <Clock className="w-5 h-5 text-primary-600 dark:text-primary-400" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-neutral-900 dark:text-white">
                Scheduled Jobs
              </h1>
              <p className="text-sm text-neutral-500">
                Cron-based posts and crew runs
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={loadJobs}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
            >
              <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
              Refresh
            </button>
            <Button onClick={openCreate}>
              <Plus className="w-4 h-4 mr-1" />
              New scheduled job
            </Button>
          </div>
        </div>

        {/* List */}
        {loading && jobs.length === 0 ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 text-neutral-400 animate-spin" />
          </div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-16">
            <Clock className="w-12 h-12 text-neutral-300 dark:text-neutral-600 mx-auto mb-3" />
            <p className="text-neutral-500 dark:text-neutral-400">
              No scheduled jobs yet
            </p>
            <p className="text-sm text-neutral-400 dark:text-neutral-500 mt-1">
              Schedule a daily post or a recurring crew run to get started
            </p>
            <Button onClick={openCreate} className="mt-4">
              <Plus className="w-4 h-4 mr-1" />
              Create your first scheduled job
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {sortedJobs.map((j) => (
              <JobCard
                key={j.id}
                job={j}
                busy={busyId === j.id}
                onRun={handleRun}
                onToggle={handleToggle}
                onEdit={openEdit}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>

      <JobDialog
        open={dialogOpen}
        editing={editing}
        channels={channels}
        crews={crews}
        onClose={() => setDialogOpen(false)}
        onSaved={loadJobs}
      />
    </div>
  );
}
