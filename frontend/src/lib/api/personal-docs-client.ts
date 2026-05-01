/**
 * Typed client for Personal Docs / folder-mapped RAG.
 * Endpoints under /api/v1/personal-docs.
 */
import { api, getApiBaseUrl } from "@/lib/transport";

export type Schedule = "manual" | "1h" | "6h" | "24h";
export type SourceStatus = "active" | "paused" | "error";
export type JobStatus =
  | "queued"
  | "walking"
  | "awaiting_confirmation"
  | "running"
  | "done"
  | "error"
  | "cancelled";
export type JobKind = "full_sync" | "incremental" | "delete_source";

export interface FolderSource {
  id: string;
  kb_id: string;
  path: string;
  label: string;
  include_globs: string[];
  exclude_globs: string[];
  schedule: Schedule;
  max_file_bytes: number;
  max_files: number;
  max_depth: number;
  status: SourceStatus;
  last_sync_at: string | null;
  last_sync_job_id: string | null;
  file_count: number;
  byte_count: number;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface IndexJob {
  id: string;
  kb_id: string;
  source_id: string;
  kind: JobKind;
  status: JobStatus;
  files_total: number;
  files_done: number;
  files_added: number;
  files_updated: number;
  files_removed: number;
  files_skipped: number;
  bytes_total: number;
  bytes_done: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

function normalizeSource(raw: Record<string, unknown>): FolderSource {
  const id = (raw.id as string) || (raw._id as string);
  return { ...(raw as unknown as FolderSource), id };
}

function normalizeJob(raw: Record<string, unknown>): IndexJob {
  const id = (raw.id as string) || (raw._id as string);
  return { ...(raw as unknown as IndexJob), id };
}

// ---------------------------------------------------------------------------
// Folder mapping CRUD
// ---------------------------------------------------------------------------

export async function listFolders(kbId: string): Promise<FolderSource[]> {
  const { data } = await api.get<{ items: Record<string, unknown>[] }>(
    `/personal-docs/kbs/${kbId}/folders`,
  );
  return (data.items || []).map(normalizeSource);
}

export async function createFolder(
  kbId: string,
  payload: {
    path: string;
    label?: string;
    schedule?: Schedule;
    include_globs?: string[];
    exclude_globs?: string[];
    max_file_bytes?: number;
    max_files?: number;
    max_depth?: number;
  },
): Promise<{ source: FolderSource; jobId: string }> {
  const { data } = await api.post<{
    source: Record<string, unknown>;
    job_id: string;
  }>(`/personal-docs/kbs/${kbId}/folders`, payload);
  return { source: normalizeSource(data.source), jobId: data.job_id };
}

export async function getFolder(sourceId: string): Promise<FolderSource> {
  const { data } = await api.get<{ item: Record<string, unknown> }>(
    `/personal-docs/folders/${sourceId}`,
  );
  return normalizeSource(data.item);
}

export async function updateFolder(
  sourceId: string,
  payload: Partial<
    Pick<
      FolderSource,
      | "label"
      | "schedule"
      | "status"
      | "include_globs"
      | "exclude_globs"
      | "max_file_bytes"
      | "max_files"
      | "max_depth"
    >
  >,
): Promise<FolderSource> {
  const { data } = await api.put<{ item: Record<string, unknown> }>(
    `/personal-docs/folders/${sourceId}`,
    payload,
  );
  return normalizeSource(data.item);
}

export async function deleteFolder(sourceId: string): Promise<boolean> {
  const { ok } = await api.delete<{ deleted: boolean }>(
    `/personal-docs/folders/${sourceId}`,
  );
  return ok;
}

export async function syncFolder(sourceId: string): Promise<{ jobId: string }> {
  const { data } = await api.post<{ job_id: string }>(
    `/personal-docs/folders/${sourceId}/sync`,
    {},
  );
  return { jobId: data.job_id };
}

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------

export async function getJob(jobId: string): Promise<IndexJob> {
  const { data } = await api.get<{ item: Record<string, unknown> }>(
    `/personal-docs/jobs/${jobId}`,
  );
  return normalizeJob(data.item);
}

export async function listJobsForFolder(sourceId: string): Promise<IndexJob[]> {
  const { data } = await api.get<{ items: Record<string, unknown>[] }>(
    `/personal-docs/folders/${sourceId}/jobs`,
  );
  return (data.items || []).map(normalizeJob);
}

export async function confirmJob(jobId: string): Promise<void> {
  await api.post(`/personal-docs/jobs/${jobId}/confirm`, {});
}

export async function cancelJob(jobId: string): Promise<void> {
  await api.post(`/personal-docs/jobs/${jobId}/cancel`, {});
}

/**
 * Subscribe to live job progress via Server-Sent Events.
 * Returns a cleanup function the caller must invoke on unmount.
 */
export async function subscribeJob(
  jobId: string,
  onUpdate: (j: IndexJob) => void,
): Promise<() => void> {
  const baseUrl = await getApiBaseUrl();
  const es = new EventSource(`${baseUrl}/personal-docs/jobs/${jobId}/stream`);
  es.onmessage = (e) => {
    try {
      onUpdate(JSON.parse(e.data) as IndexJob);
    } catch {
      // ignore malformed event
    }
  };
  return () => es.close();
}
