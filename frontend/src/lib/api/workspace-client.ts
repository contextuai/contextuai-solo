import { api } from "@/lib/transport";

export type AgentKind = "prompt" | "database" | "web" | "mcp" | "api" | "file";

export const AGENT_KINDS: AgentKind[] = ["prompt", "database", "web", "mcp", "api", "file"];

export interface WorkspaceAgent {
  id: string;
  agent_id?: string;
  name: string;
  role: string;
  description: string;
  system_prompt: string;
  tools: string[];
  capabilities?: string[];
  model_id?: string;
  icon?: string;
  category?: string;
  category_label?: string;
  kind?: AgentKind;
  is_public: boolean;
  is_system?: boolean;
  source?: string;
  created_at: string;
  updated_at: string;
}

export type CreateAgentPayload = Omit<WorkspaceAgent, "id" | "created_at" | "updated_at">;
export type UpdateAgentPayload = Partial<CreateAgentPayload>;

// Category enum → display label
const CATEGORY_LABEL_MAP: Record<string, string> = {
  c_suite: "C-Suite",
  data_analytics: "Data & Analytics",
  design: "Design & UX",
  finance_operations: "Finance & Operations",
  hr_people: "HR & People",
  it_security: "IT & Security",
  legal_compliance: "Legal & Compliance",
  marketing_sales: "Marketing & Sales",
  product_management: "Product Management",
  specialized: "Specialized",
  startup_venture: "Startup & Venture",
};

// Category → display role mapping for the UI filter pills
const CATEGORY_ROLE_MAP: Record<string, string> = {
  c_suite: "Executive",
  data_analytics: "Analyst",
  design: "Designer",
  finance_operations: "Analyst",
  hr_people: "Planner",
  it_security: "Reviewer",
  legal_compliance: "Reviewer",
  marketing_sales: "Writer",
  product_management: "Planner",
  specialized: "Custom",
  startup_venture: "Researcher",
};

function normalizeAgent(raw: Record<string, unknown>): WorkspaceAgent {
  const rawKind = raw.kind as string | undefined;
  const kind: AgentKind | undefined =
    rawKind && (AGENT_KINDS as string[]).includes(rawKind)
      ? (rawKind as AgentKind)
      : rawKind === undefined
        ? "prompt"
        : undefined;
  return {
    id: (raw.id ?? raw.agent_id ?? "") as string,
    agent_id: (raw.agent_id ?? raw.id ?? "") as string,
    name: (raw.name ?? "") as string,
    role: (raw.role ?? CATEGORY_ROLE_MAP[raw.category as string] ?? "Custom") as string,
    description: (raw.description ?? "") as string,
    system_prompt: (raw.system_prompt ?? "") as string,
    tools: (raw.tools ?? raw.capabilities ?? []) as string[],
    capabilities: (raw.capabilities ?? []) as string[],
    model_id: raw.model_id as string | undefined,
    icon: raw.icon as string | undefined,
    category: (raw.category_label ?? CATEGORY_LABEL_MAP[raw.category as string] ?? raw.category ?? "") as string,
    category_label: raw.category_label as string | undefined,
    kind,
    is_public: (raw.is_public ?? true) as boolean,
    is_system: raw.is_system as boolean | undefined,
    source: raw.source as string | undefined,
    created_at: (raw.created_at ?? new Date().toISOString()) as string,
    updated_at: (raw.updated_at ?? "") as string,
  };
}

export interface ListAgentsOptions {
  kind?: AgentKind;
  page?: number;
  pageSize?: number;
}

export const workspaceApi = {
  async listAgents(options?: ListAgentsOptions): Promise<WorkspaceAgent[]> {
    const params = new URLSearchParams();
    params.set("page_size", String(options?.pageSize ?? 100));
    if (options?.page) params.set("page", String(options.page));
    if (options?.kind) params.set("kind", options.kind);
    const { data } = await api.get<{ agents: Record<string, unknown>[] } | Record<string, unknown>[]>(
      `/workspace/agents?${params.toString()}`
    );
    const raw = Array.isArray(data)
      ? data
      : (data as { agents: Record<string, unknown>[] }).agents ?? [];
    return raw.map(normalizeAgent);
  },

  async getAgentKindCounts(): Promise<Record<string, number>> {
    const { data } = await api.get<{ counts: Record<string, number> }>(
      "/workspace/agents/kinds/counts"
    );
    return data?.counts ?? {};
  },

  async getAgent(id: string): Promise<WorkspaceAgent> {
    const { data } = await api.get<WorkspaceAgent>(`/workspace/agents/${id}`);
    return data;
  },

  async createAgent(payload: CreateAgentPayload): Promise<WorkspaceAgent> {
    const { data } = await api.post<WorkspaceAgent>("/workspace/agents/", payload);
    return data;
  },

  async updateAgent(id: string, payload: UpdateAgentPayload): Promise<WorkspaceAgent> {
    const { data } = await api.put<WorkspaceAgent>(`/workspace/agents/${id}`, payload);
    return data;
  },

  async deleteAgent(id: string): Promise<void> {
    await api.delete(`/workspace/agents/${id}`);
  },
};
