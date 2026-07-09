import { api } from "@/lib/transport";

export interface MemoryFact {
  id: string;
  scope: string;
  subject: string;
  predicate: string;
  value: string;
  text: string;
  confidence: number;
  status: "active" | "review";
  pinned: boolean;
  source_kind: string;
  source_id?: string | null;
  source_label?: string | null;
  origin: "extracted" | "user";
  created_at?: string | null;
  updated_at?: string | null;
  last_used_at?: string | null;
  /** Present only on search/query results (semantic similarity, 0..1). */
  score?: number;
}

export interface MemorySettings {
  enabled: boolean;
  chat_enabled: boolean;
  crews_enabled: boolean;
  channels_enabled: boolean;
  confidence_threshold: number;
}

export interface MemoryExport {
  exported_at: string;
  facts: (MemoryFact & { has_embedding?: boolean })[];
}

function normalizeFact(raw: Record<string, unknown>): MemoryFact {
  return {
    id: (raw.id as string) || (raw._id as string),
    scope: (raw.scope as string) || "global",
    subject: raw.subject as string,
    predicate: raw.predicate as string,
    value: raw.value as string,
    text: raw.text as string,
    confidence: typeof raw.confidence === "number" ? raw.confidence : 1.0,
    status: (raw.status as MemoryFact["status"]) || "active",
    pinned: Boolean(raw.pinned),
    source_kind: (raw.source_kind as string) || "user",
    source_id: (raw.source_id as string | null) ?? null,
    source_label: (raw.source_label as string | null) ?? null,
    origin: (raw.origin as MemoryFact["origin"]) || "user",
    created_at: (raw.created_at as string | null) ?? null,
    updated_at: (raw.updated_at as string | null) ?? null,
    last_used_at: (raw.last_used_at as string | null) ?? null,
    ...(typeof raw.score === "number" ? { score: raw.score as number } : {}),
  };
}

export async function listFacts(params?: {
  scope?: string;
  status?: string;
  q?: string;
}): Promise<MemoryFact[]> {
  const search = new URLSearchParams();
  if (params?.scope) search.set("scope", params.scope);
  if (params?.status) search.set("status", params.status);
  if (params?.q) search.set("q", params.q);
  const qs = search.toString();
  const { data } = await api.get<{ items: Record<string, unknown>[] }>(
    `/memory/facts${qs ? `?${qs}` : ""}`,
  );
  return (data.items || []).map(normalizeFact);
}

export async function getFact(id: string): Promise<MemoryFact> {
  const { data } = await api.get<{ item: Record<string, unknown> }>(
    `/memory/facts/${id}`,
  );
  return normalizeFact(data.item);
}

export async function createFact(payload: {
  subject: string;
  predicate: string;
  value: string;
  text?: string;
  scope?: string;
}): Promise<MemoryFact> {
  const { data } = await api.post<{ item: Record<string, unknown> }>(
    "/memory/facts",
    payload,
  );
  return normalizeFact(data.item);
}

export async function updateFact(
  id: string,
  payload: Partial<{
    subject: string;
    predicate: string;
    value: string;
    text: string;
    pinned: boolean;
    status: "active" | "review";
    scope: string;
  }>,
): Promise<MemoryFact> {
  const { data } = await api.put<{ item: Record<string, unknown> }>(
    `/memory/facts/${id}`,
    payload,
  );
  return normalizeFact(data.item);
}

export async function deleteFact(id: string): Promise<boolean> {
  const { data } = await api.delete<{ deleted: boolean }>(
    `/memory/facts/${id}`,
  );
  return data.deleted;
}

export async function pinFact(
  id: string,
  pinned: boolean,
): Promise<MemoryFact> {
  const { data } = await api.post<{ item: Record<string, unknown> }>(
    `/memory/facts/${id}/pin`,
    { pinned },
  );
  return normalizeFact(data.item);
}

export async function searchFacts(
  query: string,
  topK = 8,
  scopes?: string[],
): Promise<MemoryFact[]> {
  const { data } = await api.post<{ items: Record<string, unknown>[] }>(
    "/memory/search",
    { query, top_k: topK, scopes },
  );
  return (data.items || []).map(normalizeFact);
}

export async function exportMemory(): Promise<MemoryExport> {
  const { data } = await api.get<MemoryExport>("/memory/export");
  return data;
}

export async function getMemorySettings(): Promise<MemorySettings> {
  const { data } = await api.get<MemorySettings>("/memory/settings");
  return data;
}

export async function updateMemorySettings(
  payload: Partial<MemorySettings>,
): Promise<MemorySettings> {
  const { data } = await api.put<MemorySettings>("/memory/settings", payload);
  return data;
}
