import { api, getApiBaseUrl } from "@/lib/transport";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type RoleKind =
  | "coder"
  | "reviewer"
  | "security"
  | "ui_ux"
  | "docs"
  | "tester"
  | "planner"
  | "custom";

export type WorkflowMode = "solo" | "sequential" | "parallel" | "custom";

export interface CoderAgentRole {
  role_id: string;
  project_id: string;
  role_kind: RoleKind;
  display_name: string;
  system_prompt: string;
  model_id: string;
  temperature: number;
  max_tokens: number;
  enabled: boolean;
  order: number;
}

export type CoderAgentRoleCreate = Omit<CoderAgentRole, "role_id" | "project_id">;
export type CoderAgentRoleUpdate = Partial<CoderAgentRoleCreate>;

export interface RolePresetSummary {
  preset_id: string;
  name: string;
  description: string;
  workflow_mode: WorkflowMode;
  role_count: number;
}

export interface RolePresetDetail extends RolePresetSummary {
  roles: Omit<CoderAgentRole, "role_id" | "project_id">[];
}

// Chat message used in run/preview calls
export interface WorkflowChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface WorkflowPlanRole {
  role_id: string;
  role_kind: RoleKind;
  display_name: string;
  model_id: string;
}

export interface WorkflowPlan {
  workflow_mode: WorkflowMode;
  roles: WorkflowPlanRole[];
}

// ---------------------------------------------------------------------------
// Discriminated-union workflow events
// ---------------------------------------------------------------------------

export interface WorkflowStartEvent {
  type: "workflow_start";
  workflow_mode: WorkflowMode;
  roles: WorkflowPlanRole[];
}

export interface RoleStartEvent {
  type: "role_start";
  role_id: string;
  role_kind: RoleKind;
  display_name: string;
  model_id: string;
}

export interface RoleTokenEvent {
  type: "role_token";
  role_id: string;
  content: string;
}

export interface RoleDoneEvent {
  type: "role_done";
  role_id: string;
  output: string;
  usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
}

export interface WorkflowDoneEvent {
  type: "workflow_done";
  total_usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
}

export interface WorkflowErrorEvent {
  type: "error";
  error: string;
  role_id?: string;
}

export type WorkflowEvent =
  | WorkflowStartEvent
  | RoleStartEvent
  | RoleTokenEvent
  | RoleDoneEvent
  | WorkflowDoneEvent
  | WorkflowErrorEvent;

// ---------------------------------------------------------------------------
// Roles CRUD
// ---------------------------------------------------------------------------

export async function listRoles(projectId: string): Promise<CoderAgentRole[]> {
  const { data } = await api.get<CoderAgentRole[]>(`/coder/projects/${projectId}/roles`);
  return data ?? [];
}

export async function createRole(
  projectId: string,
  body: CoderAgentRoleCreate,
): Promise<CoderAgentRole> {
  const { data } = await api.post<CoderAgentRole>(
    `/coder/projects/${projectId}/roles`,
    body,
  );
  return data;
}

export async function updateRole(
  projectId: string,
  roleId: string,
  body: CoderAgentRoleUpdate,
): Promise<CoderAgentRole> {
  const { data } = await api.put<CoderAgentRole>(
    `/coder/projects/${projectId}/roles/${roleId}`,
    body,
  );
  return data;
}

export async function deleteRole(projectId: string, roleId: string): Promise<void> {
  await api.delete(`/coder/projects/${projectId}/roles/${roleId}`);
}

export async function applyPreset(
  projectId: string,
  presetId: string,
): Promise<CoderAgentRole[]> {
  const { data } = await api.post<CoderAgentRole[]>(
    `/coder/projects/${projectId}/roles/apply-preset`,
    { preset_id: presetId },
  );
  return data ?? [];
}

export async function reorderRoles(projectId: string, roleIds: string[]): Promise<void> {
  await api.put(`/coder/projects/${projectId}/roles/reorder`, { role_ids: roleIds });
}

// ---------------------------------------------------------------------------
// Workflow mode
// ---------------------------------------------------------------------------

export async function getWorkflowMode(projectId: string): Promise<WorkflowMode> {
  const { data } = await api.get<{ workflow_mode: WorkflowMode }>(
    `/coder/projects/${projectId}/workflow`,
  );
  return data.workflow_mode;
}

export async function setWorkflowMode(projectId: string, mode: WorkflowMode): Promise<void> {
  await api.put(`/coder/projects/${projectId}/workflow`, { workflow_mode: mode });
}

// ---------------------------------------------------------------------------
// Presets
// ---------------------------------------------------------------------------

export async function listPresets(): Promise<RolePresetSummary[]> {
  const { data } = await api.get<RolePresetSummary[]>("/coder/role-presets");
  return data ?? [];
}

export async function getPreset(presetId: string): Promise<RolePresetDetail> {
  const { data } = await api.get<RolePresetDetail>(`/coder/role-presets/${presetId}`);
  return data;
}

// ---------------------------------------------------------------------------
// Execution
// ---------------------------------------------------------------------------

export async function previewWorkflow(
  projectId: string,
  message: string,
  history?: WorkflowChatMessage[],
): Promise<WorkflowPlan> {
  const { data } = await api.post<WorkflowPlan>(
    `/coder/projects/${projectId}/run/preview`,
    { message, history: history ?? [] },
  );
  return data;
}

export async function* streamWorkflow(
  projectId: string,
  message: string,
  history?: WorkflowChatMessage[],
  signal?: AbortSignal,
): AsyncGenerator<WorkflowEvent, void, unknown> {
  const baseUrl = await getApiBaseUrl();
  const url = `${baseUrl}/coder/projects/${projectId}/run`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history: history ?? [] }),
      signal,
    });
  } catch (err) {
    if (signal?.aborted) return;
    yield { type: "error", error: `Connection failed: ${err}` };
    return;
  }

  if (!response.ok) {
    yield { type: "error", error: `HTTP ${response.status}: ${response.statusText}` };
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    yield { type: "error", error: "No response body" };
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data: ")) continue;
      const content = trimmed.slice(6);
      if (content === "[DONE]") continue;
      try {
        const parsed = JSON.parse(content) as Record<string, unknown>;
        // Attach the `type` field and pass through verbatim
        if (typeof parsed.type === "string") {
          yield parsed as unknown as WorkflowEvent;
        }
      } catch {
        // skip malformed lines
      }
    }
  }
}
