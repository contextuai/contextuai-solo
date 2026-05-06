import { api, getApiBaseUrl } from "@/lib/transport";

// ---------------------------------------------------------------------------
// Types — mirror backend contract for /api/v1/coder
// ---------------------------------------------------------------------------

export type CoderProjectStatus = "created" | "trusted" | "running" | "stopped";
export type Runtime = "node" | "python" | "static" | "auto";
export type NetworkPolicy = "allow" | "block";

export interface CoderProject {
  project_id: string;
  name: string;
  folder_path: string;
  template_id?: string | null;
  runtime: Runtime;
  trusted: boolean;
  network_policy: NetworkPolicy;
  chat_thread_id?: string | null;
  last_run_at?: string | null;
  status: CoderProjectStatus;
  created_at: string;
  updated_at: string;
  process_pid?: number | null;
  preview_port?: number | null;
}

export interface CoderTemplateInfo {
  id: string;
  name: string;
  description: string;
  runtime: Runtime;
  init_commands: string[];
  starter_prompt: string;
}

export interface CoderProjectCreate {
  name: string;
  folder_path: string;
  template_id?: string | null;
  runtime?: Runtime;
}

export interface CoderProjectUpdate {
  name?: string;
  trusted?: boolean;
  network_policy?: NetworkPolicy;
}

export interface RunResult {
  status: "started" | "already_running" | "failed" | "stopped" | "not_running";
  error?: string | null;
}

export interface RunningProject {
  project_id: string;
  name: string;
  pid: number;
  started_at: string;
}

// ---------------------------------------------------------------------------
// Templates
// ---------------------------------------------------------------------------

export async function listCoderTemplates(): Promise<CoderTemplateInfo[]> {
  const { data } = await api.get<{ templates: CoderTemplateInfo[] }>(
    "/coder/templates",
  );
  return data.templates ?? [];
}

// ---------------------------------------------------------------------------
// Projects CRUD
// ---------------------------------------------------------------------------

export async function listCoderProjects(): Promise<CoderProject[]> {
  const { data } = await api.get<{
    success: boolean;
    projects: CoderProject[];
    total_count: number;
  }>("/coder/projects");
  return data.projects ?? [];
}

export async function createCoderProject(
  input: CoderProjectCreate,
): Promise<CoderProject> {
  const { data } = await api.post<CoderProject>("/coder/projects", input);
  return data;
}

export async function getCoderProject(id: string): Promise<CoderProject> {
  const { data } = await api.get<CoderProject>(`/coder/projects/${id}`);
  return data;
}

export async function updateCoderProject(
  id: string,
  patch: CoderProjectUpdate,
): Promise<CoderProject> {
  const { data } = await api.put<CoderProject>(`/coder/projects/${id}`, patch);
  return data;
}

export async function deleteCoderProject(id: string): Promise<void> {
  await api.delete(`/coder/projects/${id}`);
}

// ---------------------------------------------------------------------------
// Run / stop / running list
// ---------------------------------------------------------------------------

export async function startCoderProject(
  id: string,
  command?: string,
): Promise<RunResult> {
  const { data } = await api.post<RunResult>(
    `/coder/projects/${id}/start`,
    command ? { command } : {},
  );
  return data;
}

export async function stopCoderProject(id: string): Promise<RunResult> {
  const { data } = await api.post<RunResult>(`/coder/projects/${id}/stop`);
  return data;
}

export async function listRunningProjects(): Promise<RunningProject[]> {
  const { data } = await api.get<{ projects: RunningProject[] }>(
    "/coder/running",
  );
  return data.projects ?? [];
}

// ---------------------------------------------------------------------------
// Cross-mode handoff: index project folder as a Knowledge Base source
// ---------------------------------------------------------------------------

export type IndexAsKbSchedule = "manual" | "1h" | "6h" | "24h";

export interface IndexAsKbInput {
  kb_id: string;
  label?: string;
  schedule?: IndexAsKbSchedule;
}

export interface IndexAsKbResult {
  success: boolean;
  source_id: string;
  kb_id: string;
}

export async function indexCoderProjectAsKb(
  projectId: string,
  input: IndexAsKbInput,
): Promise<IndexAsKbResult> {
  const { data } = await api.post<IndexAsKbResult>(
    `/coder/projects/${projectId}/index-as-kb`,
    input,
  );
  return data;
}

// ---------------------------------------------------------------------------
// SSE: project run output stream
// ---------------------------------------------------------------------------

/**
 * Subscribe to a project's stdout/stderr SSE stream. Each yielded value is one
 * line emitted by the running process. Pattern follows
 * `automations-client.ts::streamExecution`.
 */
export async function* streamCoderOutput(
  id: string,
  signal?: AbortSignal,
): AsyncGenerator<string, void, unknown> {
  const baseUrl = await getApiBaseUrl();
  const response = await fetch(`${baseUrl}/coder/projects/${id}/output`, {
    method: "GET",
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`Stream failed: HTTP ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";
    for (const event of events) {
      // SSE event: lines may contain "data: <line>" — concatenate any data
      // lines (rare for stdout, but spec-compliant).
      const dataLines = event
        .split("\n")
        .filter((l) => l.startsWith("data: "))
        .map((l) => l.slice(6));
      if (dataLines.length === 0) continue;
      yield dataLines.join("\n");
    }
  }
}
