import { api } from "@/lib/transport";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ProjectAgent {
  agent_id: string;
  agent_name: string;
  role: string;
}

export interface WorkspaceProject {
  id?: string;
  project_id: string;
  title: string;
  description: string;
  project_type: string;
  status: "draft" | "queued" | "running" | "paused" | "completed" | "failed" | "cancelled";
  selected_agents: ProjectAgent[];
  user_id?: string;
  estimated_cost_usd?: number;
  created_at: string;
  updated_at: string;
  completed_at?: string;
}

export interface AgentContribution {
  agent_id: string;
  agent_name: string;
  content: string;
  round_number: number;
  timestamp?: string;
}

export interface ProjectExecution {
  execution_id: string;
  project_id: string;
  status: "running" | "completed" | "failed" | "cancelled";
  contributions?: AgentContribution[];
  compiled_output?: string;
  output_format?: string;
  total_tokens?: number;
  total_cost?: number;
  started_at: string;
  completed_at?: string;
}

export interface ProjectStep {
  agent_id: string;
  agent_name: string;
  status: "pending" | "running" | "completed" | "failed";
  output?: string;
  tokens_used?: number;
  started_at?: string;
  completed_at?: string;
}

export interface ProjectType {
  id: string;
  name: string;
  description: string;
  category?: string;
  default_agents?: string[];
  default_rounds?: number;
  output_format?: string;
  enabled?: boolean;
}

export interface CreateProjectPayload {
  title: string;
  description: string;
  project_type: string;
  selected_agents: string[];
}

// ---------------------------------------------------------------------------
// API client (uses desktop transport)
// ---------------------------------------------------------------------------

export const workspaceProjectsApi = {
  list: async (status?: string): Promise<WorkspaceProject[]> => {
    const params = new URLSearchParams();
    if (status) params.append("status", status);
    params.append("limit", "50");
    const query = params.toString();
    const { data } = await api.get<{
      projects?: WorkspaceProject[];
      success?: boolean;
      total_count?: number;
    }>(`/workspace/projects${query ? `?${query}` : ""}`);
    const raw = data as Record<string, unknown>;
    return (raw.projects ?? []) as WorkspaceProject[];
  },

  get: async (id: string): Promise<WorkspaceProject> => {
    const { data } = await api.get<{
      project?: WorkspaceProject;
      success?: boolean;
    }>(`/workspace/projects/${id}`);
    const raw = data as Record<string, unknown>;
    return (raw.project ?? raw) as WorkspaceProject;
  },

  create: async (payload: CreateProjectPayload): Promise<WorkspaceProject> => {
    const { data } = await api.post<{
      project?: WorkspaceProject;
      success?: boolean;
    }>("/workspace/projects", payload);
    const raw = data as Record<string, unknown>;
    return (raw.project ?? raw) as WorkspaceProject;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/workspace/projects/${id}`);
  },

  execute: async (projectId: string): Promise<ProjectExecution> => {
    const { data } = await api.post<{
      execution?: ProjectExecution;
      success?: boolean;
    }>(`/workspace/projects/${projectId}/execute`);
    const raw = data as Record<string, unknown>;
    return (raw.execution ?? raw) as ProjectExecution;
  },

  getExecution: async (projectId: string): Promise<ProjectExecution> => {
    const { data } = await api.get<{
      execution?: ProjectExecution;
      success?: boolean;
    }>(`/workspace/projects/${projectId}/execution/latest`);
    const raw = data as Record<string, unknown>;
    return (raw.execution ?? raw) as ProjectExecution;
  },

  listProjectTypes: async (): Promise<ProjectType[]> => {
    try {
      const { data } = await api.get<{
        project_types?: ProjectType[];
        success?: boolean;
      }>("/workspace-project-types?enabled=true");
      const raw = data as Record<string, unknown>;
      return (raw.project_types ?? []) as ProjectType[];
    } catch {
      return [];
    }
  },
};
