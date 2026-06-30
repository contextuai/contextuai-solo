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
  // Phase 4 PR 9: Coder project step.
  // When `coder_project_id` is set, the orchestrator runs the named Coder
  // project headlessly instead of invoking an LLM agent. A step is valid
  // if it has `instructions` OR `coder_project_id`.
  coder_project_id?: string | null;
  coder_run_timeout_seconds?: number;
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

// Phase 3 additions — safe to read as optional since PR 1 may not be merged yet.
export interface ConnectionBinding {
  connection_id: string;
  platform: string;
  direction: "inbound" | "outbound" | "both";
}

export type CrewTrigger =
  | {
      type: "reactive";
      connection_id: string;
      keywords?: string[];
      hashtags?: string[];
      mentions?: string[];
    }
  | {
      type: "scheduled";
      connection_ids?: string[];
      cron?: string;
      run_at?: string;
      content_brief?: string;
    };

export interface Crew {
  id?: string;
  crew_id: string;
  name: string;
  description?: string;
  execution_config?: CrewExecutionConfig;
  agents?: CrewAgent[];
  channel_bindings?: ChannelBinding[];
  connection_bindings?: ConnectionBinding[];
  triggers?: CrewTrigger[];
  approval_required?: boolean;
  phases?: unknown[];
  schedule?: CrewSchedule;
  status: "active" | "paused" | "archived" | "idle";
  tags?: string[];
  user_id?: string;
  created_at?: string;
  updated_at?: string;
  // Phase 4 PR 3: distinguishes recurring crews ("crew") from one-shot
  // promoted workspace projects ("project"). Optional because legacy rows
  // pre-migration may omit it.
  kind?: "crew" | "project";
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
  trigger_type?: "reactive" | "scheduled" | "manual";
  trigger_source?: string;
}

export interface CrewRunStep {
  agent_id: string;
  agent_name: string;
  status: "pending" | "running" | "completed" | "failed";
  started_at?: string;
  completed_at?: string;
  output?: string;
  tokens_used?: number;
  cost_usd?: number;
  duration_seconds?: number;
}

// The backend returns agents/total_cost_usd/duration_ms; the UI reads
// steps/cost_usd/duration_seconds/phases. Normalize the run shape so the
// progress panel and run list show tokens, cost, steps, and progress.
function normalizeRun(raw: Record<string, unknown>): CrewRun {
  const r = (raw ?? {}) as Record<string, any>;
  const rawSteps = (r.steps ?? r.agents ?? []) as Record<string, any>[];
  const steps: CrewRunStep[] = rawSteps.map((a) => ({
    agent_id: a.agent_id,
    agent_name: a.agent_name ?? a.name,
    status: a.status,
    started_at: a.started_at,
    completed_at: a.completed_at,
    output: a.output,
    tokens_used: a.tokens_used,
    cost_usd: a.cost_usd,
    duration_seconds: a.duration_seconds,
  }));
  const completed = steps.filter((s) => s.status === "completed").length;
  return {
    ...(r as CrewRun),
    steps,
    cost_usd: r.cost_usd ?? r.total_cost_usd,
    total_tokens: r.total_tokens,
    duration_seconds:
      r.duration_seconds ??
      (r.duration_ms != null ? Math.round(r.duration_ms / 1000) : undefined),
    phases_completed: r.phases_completed ?? completed,
    total_phases: r.total_phases ?? steps.length,
  };
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
  list: async (
    options: {
      kind?: "crew" | "project" | "all";
      status?: string;
      page?: number;
      page_size?: number;
    } = {}
  ): Promise<Crew[]> => {
    const query = new URLSearchParams();
    if (options.kind) query.set("kind", options.kind);
    if (options.status) query.set("status", options.status);
    if (options.page) query.set("page", String(options.page));
    if (options.page_size) query.set("page_size", String(options.page_size));
    const qs = query.toString();
    const path = `/crews/${qs ? `?${qs}` : ""}`;
    const { data } = await api.get<{ crews?: Crew[]; data?: { crews?: Crew[] } }>(path);
    const raw = data as Record<string, unknown>;
    const crews = (raw.crews ?? (raw.data as Record<string, unknown>)?.crews ?? []) as Crew[];
    return crews;
  },

  // Phase 4 PR 3: per-kind counts for tab badges on the unified Crews page.
  getCrewsKindCounts: async (): Promise<{ crew: number; project: number }> => {
    const { data } = await api.get<{ counts?: { crew?: number; project?: number } }>(
      "/crews/kinds/counts"
    );
    const raw = data as Record<string, unknown>;
    const counts = (raw.counts ?? {}) as { crew?: number; project?: number };
    return { crew: counts.crew ?? 0, project: counts.project ?? 0 };
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
    const runs = (raw.runs ?? (raw.data as Record<string, unknown>)?.runs ?? []) as Record<string, unknown>[];
    return runs.map(normalizeRun);
  },

  startRun: async (
    crewId: string,
    input?: string,
    inputData?: Record<string, unknown>,
  ): Promise<CrewRun> => {
    // `input` is the task/objective for this run. Without it the crew has
    // nothing concrete to do and agents fall back to describing themselves.
    const { data } = await api.post<{ data: CrewRun }>(`/crews/${crewId}/run`, {
      input: input && input.trim() ? input.trim() : undefined,
      input_data: inputData ?? {},
    });
    return (data as { data: CrewRun }).data;
  },

  getRun: async (_crewId: string, runId: string): Promise<CrewRun> => {
    // Backend route is /crews/runs/{run_id} (no crew_id in path)
    const { data } = await api.get<{ data: Record<string, unknown> }>(`/crews/runs/${runId}`);
    return normalizeRun((data as { data: Record<string, unknown> }).data);
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
