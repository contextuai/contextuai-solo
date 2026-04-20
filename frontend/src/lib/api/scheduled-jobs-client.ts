import { api } from "@/lib/transport";

export type ScheduledJobType = "post" | "crew";

export interface ScheduledJob {
  id: string;
  name: string;
  job_type: ScheduledJobType;
  cron: string;
  timezone: string;
  enabled: boolean;

  channel_id?: string | null;
  content?: string | null;
  title?: string | null;
  metadata?: Record<string, unknown> | null;

  crew_id?: string | null;
  crew_input?: Record<string, unknown> | null;

  last_run_at?: string | null;
  last_run_status?: "success" | "failed" | null;
  last_run_error?: string | null;
  next_run_at?: string | null;
  run_count: number;

  created_at: string;
  updated_at: string;
}

export interface CreateScheduledJobBody {
  name: string;
  job_type: ScheduledJobType;
  cron: string;
  timezone?: string;
  enabled?: boolean;

  channel_id?: string;
  content?: string;
  title?: string;
  metadata?: Record<string, unknown>;

  crew_id?: string;
  crew_input?: Record<string, unknown>;
}

export interface UpdateScheduledJobBody {
  name?: string;
  cron?: string;
  timezone?: string;
  enabled?: boolean;

  channel_id?: string;
  content?: string;
  title?: string;
  metadata?: Record<string, unknown>;

  crew_id?: string;
  crew_input?: Record<string, unknown>;
}

export interface ValidateCronResult {
  valid: boolean;
  cron: string;
  timezone: string;
  next_runs: string[];
}

export interface ScheduledJobRunResult {
  job_id: string;
  job_type: ScheduledJobType;
  status: "success" | "failed" | "skipped";
  ran_at: string;
  error?: string | null;
  details?: Record<string, unknown> | null;
}

interface Envelope<T> {
  status: string;
  data: T;
  message?: string;
}

const BASE = "/scheduled-jobs";

export async function listScheduledJobs(
  skip: number = 0,
  limit: number = 100
): Promise<{ jobs: ScheduledJob[]; total: number }> {
  const { data } = await api.get<Envelope<{ jobs: ScheduledJob[]; total: number; skip: number; limit: number }>>(
    `${BASE}/?skip=${skip}&limit=${limit}`
  );
  return { jobs: data.data?.jobs ?? [], total: data.data?.total ?? 0 };
}

export async function getScheduledJob(id: string): Promise<ScheduledJob> {
  const { data } = await api.get<Envelope<ScheduledJob>>(`${BASE}/${encodeURIComponent(id)}`);
  return data.data;
}

export async function createScheduledJob(body: CreateScheduledJobBody): Promise<ScheduledJob> {
  const { data } = await api.post<Envelope<ScheduledJob>>(`${BASE}/`, body);
  return data.data;
}

export async function updateScheduledJob(
  id: string,
  body: UpdateScheduledJobBody
): Promise<ScheduledJob> {
  const { data } = await api.patch<Envelope<ScheduledJob>>(
    `${BASE}/${encodeURIComponent(id)}`,
    body
  );
  return data.data;
}

export async function deleteScheduledJob(id: string): Promise<void> {
  await api.delete(`${BASE}/${encodeURIComponent(id)}`);
}

export async function runScheduledJobNow(id: string): Promise<ScheduledJobRunResult> {
  const { data } = await api.post<Envelope<ScheduledJobRunResult>>(
    `${BASE}/${encodeURIComponent(id)}/run-now`
  );
  return data.data;
}

export async function toggleScheduledJob(id: string): Promise<ScheduledJob> {
  const { data } = await api.post<Envelope<ScheduledJob>>(
    `${BASE}/${encodeURIComponent(id)}/toggle`
  );
  return data.data;
}

export async function validateCron(
  expr: string,
  timezone: string = "UTC",
  count: number = 5
): Promise<ValidateCronResult> {
  const qs = new URLSearchParams({
    expr,
    timezone,
    count: String(count),
  });
  const { data } = await api.get<ValidateCronResult>(`${BASE}/validate-cron?${qs.toString()}`);
  return data;
}

// ─── Helpers ───────────────────────────────────────────────────────

const CRON_PRESETS: Record<string, string> = {
  "0 9 * * *": "Every day at 9:00 AM",
  "0 9 * * 1-5": "Every weekday at 9:00 AM",
  "0 * * * *": "Every hour",
  "0 9 * * 1": "Every Monday at 9:00 AM",
  "0 0 * * *": "Every day at midnight",
  "*/15 * * * *": "Every 15 minutes",
  "0 8 * * *": "Every day at 8:00 AM",
};

/** Prettify common cron expressions; falls back to the raw string. */
export function prettifyCron(expr: string): string {
  if (CRON_PRESETS[expr]) return CRON_PRESETS[expr];
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return expr;
  const [minute, hour, dom, month, dow] = parts;

  const hourNum = parseInt(hour, 10);
  const minNum = parseInt(minute, 10);
  const everyDay = dom === "*" && month === "*" && dow === "*";

  if (everyDay && !Number.isNaN(hourNum) && !Number.isNaN(minNum)) {
    const h12 = hourNum % 12 || 12;
    const ampm = hourNum < 12 ? "AM" : "PM";
    return `Every day at ${h12}:${String(minNum).padStart(2, "0")} ${ampm}`;
  }
  return expr;
}
