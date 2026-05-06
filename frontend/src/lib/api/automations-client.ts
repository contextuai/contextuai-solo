import { api, getApiBaseUrl } from "@/lib/transport";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AutomationStatus = "active" | "inactive" | "draft";
export type TriggerType = "manual" | "scheduled" | "event";
export type ExecutionMode = "sequential" | "parallel" | "smart";
export type ExecutionStatus = "running" | "success" | "failed" | "partial";

export type OutputActionType =
  | "generate_pdf"
  | "generate_pptx"
  | "send_email"
  | "webhook"
  | "save_file"
  | "distribute"
  | "run_coder_project";

export interface OutputAction {
  type: OutputActionType;
  config: Record<string, unknown>;
}

export interface Automation {
  automation_id: string;
  name: string;
  description: string;
  prompt_template: string;
  trigger_type: TriggerType;
  trigger_config?: Record<string, unknown> | null;
  status: AutomationStatus;
  created_at: string;
  updated_at: string;
  last_run?: string | null;
  run_count: number;
  personas_detected: string[];
  execution_mode: ExecutionMode;
  output_actions?: OutputAction[];
  model_id?: string | null;
}

export interface AutomationListResponse {
  success: boolean;
  automations: Automation[];
  total_count: number;
  page: number;
  page_size: number;
  last_updated: string;
}

export interface ExecutionStep {
  step_number: number;
  persona: string;
  instruction: string;
  full_prompt: string;
  result: string;
  status: "pending" | "success" | "failed" | "skipped";
  error?: string | null;
  duration_ms: number;
}

export interface AutomationExecution {
  execution_id: string;
  automation_id: string;
  status: ExecutionStatus;
  started_at: string;
  completed_at?: string | null;
  duration_ms?: number | null;
  steps: ExecutionStep[];
  final_result: string;
  error_message?: string | null;
  total_steps: number;
  successful_steps: number;
  failed_steps: number;
  output_results?: Array<Record<string, unknown>> | null;
}

export interface AutomationValidation {
  is_valid: boolean;
  personas_detected: string[];
  execution_mode: ExecutionMode;
  warnings: string[];
  errors: string[];
  suggestions: string[];
  estimated_duration_seconds?: number | null;
}

export interface CreateAutomationPayload {
  name: string;
  description?: string;
  prompt_template: string;
  trigger_type?: TriggerType;
  trigger_config?: Record<string, unknown>;
  status?: AutomationStatus;
  output_actions?: OutputAction[];
  model_id?: string;
}

export type UpdateAutomationPayload = Partial<CreateAutomationPayload>;

// ---------------------------------------------------------------------------
// CRUD
// ---------------------------------------------------------------------------

export async function listAutomations(params?: {
  status?: AutomationStatus;
  page?: number;
  page_size?: number;
}): Promise<AutomationListResponse> {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.page) query.set("page", String(params.page));
  if (params?.page_size) query.set("page_size", String(params.page_size));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const { data } = await api.get<AutomationListResponse>(
    `/automations${suffix}`,
  );
  return data;
}

export async function createAutomation(
  payload: CreateAutomationPayload,
): Promise<Automation> {
  const { data } = await api.post<Automation>("/automations", payload);
  return data;
}

export async function getAutomation(id: string): Promise<Automation> {
  const { data } = await api.get<Automation>(`/automations/${id}`);
  return data;
}

export async function updateAutomation(
  id: string,
  payload: UpdateAutomationPayload,
): Promise<Automation> {
  const { data } = await api.put<Automation>(`/automations/${id}`, payload);
  return data;
}

export async function deleteAutomation(id: string): Promise<boolean> {
  const { ok } = await api.delete(`/automations/${id}`);
  return ok;
}

// ---------------------------------------------------------------------------
// Validation + execution
// ---------------------------------------------------------------------------

export async function validatePrompt(
  prompt: string,
): Promise<AutomationValidation> {
  const { data } = await api.post<AutomationValidation>(
    "/automations/validate",
    { prompt_template: prompt },
  );
  return data;
}

export async function runAutomation(
  id: string,
  parameters?: Record<string, unknown>,
): Promise<AutomationExecution> {
  const { data } = await api.post<AutomationExecution>(
    `/automations/${id}/run`,
    { parameters: parameters || {} },
  );
  return data;
}

export async function listExecutions(
  automationId: string,
  page = 1,
  pageSize = 20,
): Promise<{ executions: AutomationExecution[]; total_count: number }> {
  const { data } = await api.get<{
    executions: AutomationExecution[];
    total_count: number;
  }>(`/automations/${automationId}/executions?page=${page}&page_size=${pageSize}`);
  return data;
}

export async function listRecentExecutions(
  page = 1,
  pageSize = 20,
): Promise<{ executions: AutomationExecution[]; total_count: number }> {
  const { data } = await api.get<{
    executions: AutomationExecution[];
    total_count: number;
  }>(`/automations/executions/recent?page=${page}&page_size=${pageSize}`);
  return data;
}

export async function getExecution(
  executionId: string,
): Promise<AutomationExecution> {
  const { data } = await api.get<AutomationExecution>(
    `/automations/executions/${executionId}`,
  );
  return data;
}

/**
 * Subscribe to an execution's SSE progress stream. Returns an `EventSource`-like
 * AsyncIterable so the caller can render step-by-step progress as the engine
 * writes new step rows.
 */
export async function* streamExecution(
  executionId: string,
  signal?: AbortSignal,
): AsyncGenerator<AutomationExecution, void, unknown> {
  const baseUrl = await getApiBaseUrl();
  const response = await fetch(
    `${baseUrl}/automations/executions/${executionId}/stream`,
    { method: "GET", signal },
  );
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
      const dataLine = event
        .split("\n")
        .find((l) => l.startsWith("data: "));
      if (!dataLine) continue;
      try {
        const parsed = JSON.parse(dataLine.slice(6)) as AutomationExecution;
        yield parsed;
      } catch {
        // ignore malformed
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Promote to crew
// ---------------------------------------------------------------------------

export async function promoteToCrew(
  automationId: string,
  name?: string,
): Promise<{ promoted: boolean; crew_id: string }> {
  const { data } = await api.post<{ promoted: boolean; crew_id: string }>(
    `/automations/${automationId}/promote-to-crew`,
    { name },
  );
  return data;
}

// ---------------------------------------------------------------------------
// Connections (for the output-action picker)
// ---------------------------------------------------------------------------

export interface ConnectionSummary {
  id: string;
  platform: string;
  display_name?: string | null;
  connected: boolean;
  inbound_enabled: boolean;
  outbound_enabled: boolean;
  inbound_supported: boolean;
  outbound_supported: boolean;
}

export async function listOutboundConnections(): Promise<ConnectionSummary[]> {
  const { data } = await api.get<{
    connections: ConnectionSummary[];
    total_count: number;
  }>("/connections");
  return (data.connections || []).filter(
    (c) => c.outbound_supported && c.outbound_enabled,
  );
}
