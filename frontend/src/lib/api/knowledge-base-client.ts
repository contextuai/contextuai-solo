import { api, getApiBaseUrl } from "@/lib/transport";

export interface KnowledgeBase {
  id: string;
  name: string;
  description?: string | null;
  embedding_model: string;
  embedding_dim: number;
  doc_count: number;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface KbDocument {
  id: string;
  kb_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  page_count: number;
  chunk_count: number;
  status: "pending" | "indexing" | "ready" | "error";
  error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface KbCitation {
  doc_id: string;
  filename: string;
  page: number | null;
  chunk_index: number;
  score: number;
  excerpt: string;
}

export interface KbUploadResult {
  id?: string;
  filename: string;
  status: "ready" | "error";
  chunks?: number;
  pages?: number;
  error?: string;
}

function normalizeKb(raw: Record<string, unknown>): KnowledgeBase {
  return {
    id: (raw.id as string) || (raw._id as string),
    name: raw.name as string,
    description: (raw.description as string | null) ?? null,
    embedding_model: (raw.embedding_model as string) || "all-MiniLM-L6-v2",
    embedding_dim: (raw.embedding_dim as number) || 384,
    doc_count: (raw.doc_count as number) || 0,
    chunk_count: (raw.chunk_count as number) || 0,
    created_at: raw.created_at as string,
    updated_at: raw.updated_at as string,
  };
}

function normalizeDoc(raw: Record<string, unknown>): KbDocument {
  return {
    id: (raw.id as string) || (raw._id as string),
    kb_id: raw.kb_id as string,
    filename: raw.filename as string,
    mime_type: (raw.mime_type as string) || "application/octet-stream",
    size_bytes: (raw.size_bytes as number) || 0,
    page_count: (raw.page_count as number) || 0,
    chunk_count: (raw.chunk_count as number) || 0,
    status: (raw.status as KbDocument["status"]) || "pending",
    error: (raw.error as string | null) ?? null,
    created_at: raw.created_at as string,
    updated_at: raw.updated_at as string,
  };
}

export async function listKnowledgeBases(): Promise<KnowledgeBase[]> {
  const { data } = await api.get<{ items: Record<string, unknown>[] }>(
    "/knowledge-bases",
  );
  return (data.items || []).map(normalizeKb);
}

export async function createKnowledgeBase(payload: {
  name: string;
  description?: string;
}): Promise<KnowledgeBase> {
  const { data } = await api.post<{ item: Record<string, unknown> }>(
    "/knowledge-bases",
    payload,
  );
  return normalizeKb(data.item);
}

export async function getKnowledgeBase(id: string): Promise<KnowledgeBase> {
  const { data } = await api.get<{ item: Record<string, unknown> }>(
    `/knowledge-bases/${id}`,
  );
  return normalizeKb(data.item);
}

export async function updateKnowledgeBase(
  id: string,
  payload: { name?: string; description?: string },
): Promise<KnowledgeBase> {
  const { data } = await api.put<{ item: Record<string, unknown> }>(
    `/knowledge-bases/${id}`,
    payload,
  );
  return normalizeKb(data.item);
}

export async function deleteKnowledgeBase(id: string): Promise<boolean> {
  const { ok } = await api.delete<{ deleted: boolean }>(
    `/knowledge-bases/${id}`,
  );
  return ok;
}

export async function listDocuments(kbId: string): Promise<KbDocument[]> {
  const { data } = await api.get<{ items: Record<string, unknown>[] }>(
    `/knowledge-bases/${kbId}/documents`,
  );
  return (data.items || []).map(normalizeDoc);
}

export async function deleteDocument(
  kbId: string,
  docId: string,
): Promise<boolean> {
  const { ok } = await api.delete<{ deleted: boolean }>(
    `/knowledge-bases/${kbId}/documents/${docId}`,
  );
  return ok;
}

export async function queryKnowledgeBase(
  kbId: string,
  query: string,
  topK = 5,
): Promise<KbCitation[]> {
  const { data } = await api.post<{ citations: KbCitation[] }>(
    `/knowledge-bases/${kbId}/query`,
    { query, top_k: topK },
  );
  return data.citations || [];
}

/**
 * Multipart file upload. apiRequest is JSON-only, so this uses the bare
 * fetch API against the resolved sidecar/dev backend URL.
 */
export async function uploadDocuments(
  kbId: string,
  files: File[],
): Promise<KbUploadResult[]> {
  const formData = new FormData();
  for (const file of files) formData.append("files", file);

  const baseUrl = await getApiBaseUrl();
  const response = await fetch(
    `${baseUrl}/knowledge-bases/${kbId}/documents`,
    { method: "POST", body: formData },
  );
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(`Upload failed (${response.status}): ${text}`);
  }
  const data = (await response.json()) as { items: KbUploadResult[] };
  return data.items || [];
}
