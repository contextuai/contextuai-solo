import { api } from "@/lib/transport";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CrewAgent {
  agent_id: string;
  name: string;
  role: string;
  custom_role?: string;
  instructions?: string;
  model_id?: string;
  order: number;
  tools?: string[];
  library_agent_id?: string;
}

export interface CrewExecutionConfig {
  mode: "sequential" | "parallel" | "pipeline" | "autonomous";
  timeout_seconds?: number;
  max_iterations?: number;
  max_agent_invocations?: number;
  budget_limit_usd?: number;
}

export interface CrewSchedule {
  enabled: boolean;
  cron_expression?: string;
  timezone?: string;
}

export interface ChannelBinding {
  channel_type: string;
  enabled: boolean;
  approval_required: boolean;
}

export interface Crew {
  id?: string;
  crew_id: string;
  name: string;
  description?: string;
  execution_config?: CrewExecutionConfig;
  agents?: CrewAgent[];
  channel_bindings?: ChannelBinding[];
  phases?: unknown[];
  schedule?: CrewSchedule;
  status: "active" | "paused" | "archived" | "idle";
  tags?: string[];
  user_id?: string;
  created_at?: string;
  updated_at?: string;
}

export interface CrewRun {
  id?: string;
  run_id: string;
  crew_id: string;
  crew_name?: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled" | "scheduled";
  started_at?: string;
  completed_at?: string;
  created_at: string;
  duration_seconds?: number;
  total_tokens?: number;
  cost_usd?: number;
  phases_completed?: number;
  total_phases?: number;
  steps?: CrewRunStep[];
  input_data?: Record<string, unknown>;
  output_data?: Record<string, unknown>;
  error?: string;
}

export interface CrewRunStep {
  agent_id: string;
  agent_name: string;
  status: "pending" | "running" | "completed" | "failed";
  started_at?: string;
  completed_at?: string;
  output?: string;
  tokens_used?: number;
  duration_seconds?: number;
}

export interface LibraryAgent {
  agent_id: string;
  name: string;
  description: string;
  category: string;
  capabilities: string[];
  suggested_role: string;
  icon: string;
}

// ---------------------------------------------------------------------------
// API client (uses desktop transport)
// ---------------------------------------------------------------------------

export const crewsApi = {
  list: async (): Promise<Crew[]> => {
    const { data } = await api.get<{ crews?: Crew[]; data?: { crews?: Crew[] } }>("/crews/");
    const raw = data as Record<string, unknown>;
    const crews = (raw.crews ?? (raw.data as Record<string, unknown>)?.crews ?? []) as Crew[];
    return crews;
  },

  get: async (id: string): Promise<Crew> => {
    const { data } = await api.get<{ data: Crew }>(`/crews/${id}`);
    return (data as { data: Crew }).data;
  },

  create: async (payload: Record<string, unknown>): Promise<Crew> => {
    const { data } = await api.post<{ data: Crew }>("/crews/", payload);
    return (data as { data: Crew }).data;
  },

  update: async (id: string, payload: Record<string, unknown>): Promise<Crew> => {
    const { data } = await api.patch<{ data: Crew }>(`/crews/${id}`, payload);
    return (data as { data: Crew }).data;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/crews/${id}`);
  },

  // Runs
  listRuns: async (crewId?: string, limit = 50): Promise<CrewRun[]> => {
    const path = crewId
      ? `/crews/${crewId}/runs?page_size=${limit}`
      : `/crews/runs?limit=${limit}`;
    const { data } = await api.get<{ runs?: CrewRun[]; data?: { runs?: CrewRun[] } }>(path);
    const raw = data as Record<string, unknown>;
    return (raw.runs ?? (raw.data as Record<string, unknown>)?.runs ?? []) as CrewRun[];
  },

  startRun: async (crewId: string, inputData?: Record<string, unknown>): Promise<CrewRun> => {
    const { data } = await api.post<{ data: CrewRun }>(`/crews/${crewId}/run`, {
      input_data: inputData ?? {},
    });
    return (data as { data: CrewRun }).data;
  },

  getRun: async (_crewId: string, runId: string): Promise<CrewRun> => {
    // Backend route is /crews/runs/{run_id} (no crew_id in path)
    const { data } = await api.get<{ data: CrewRun }>(`/crews/runs/${runId}`);
    return (data as { data: CrewRun }).data;
  },

  cancelRun: async (_crewId: string, runId: string): Promise<void> => {
    // Backend route is /crews/runs/{run_id}/cancel (no crew_id in path)
    await api.post(`/crews/runs/${runId}/cancel`);
  },

  // Library agents
  listLibraryAgents: async (
    params: { page?: number; page_size?: number; category?: string; search?: string } = {}
  ): Promise<{
    agents: LibraryAgent[];
    total_count: number;
    page: number;
    page_size: number;
  }> => {
    const query = new URLSearchParams();
    if (params.page) query.set("page", String(params.page));
    if (params.page_size) query.set("page_size", String(params.page_size));
    if (params.category) query.set("category", params.category);
    if (params.search) query.set("search", params.search);
    const qs = query.toString();
    const path = `/crews/library-agents${qs ? `?${qs}` : ""}`;
    const { data } = await api.get<{
      data?: LibraryAgent[];
      total_count?: number;
      page?: number;
      page_size?: number;
    }>(path);
    const raw = data as Record<string, unknown>;
    return {
      agents: (raw.data ?? []) as LibraryAgent[],
      total_count: (raw.total_count ?? 0) as number,
      page: (raw.page ?? 1) as number,
      page_size: (raw.page_size ?? 20) as number,
    };
  },
};
