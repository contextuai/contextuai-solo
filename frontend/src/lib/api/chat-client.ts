import { api, streamRequest } from "@/lib/transport";
import type {
  ChatSession,
  ChatMessage,
  StreamChunk,
  SessionListResponse,
  MessagesListResponse,
} from "@/types/chat";

export type { StreamChunk };

const USER_ID = "local-user";

// ── Session helpers ──────────────────────────────────────────────

export function generateSessionId(): string {
  const ts = Date.now();
  const rand = Math.random().toString(36).substring(2, 11);
  return `session_${ts}_${rand}`;
}

export async function createSession(opts?: {
  title?: string;
  personaId?: string;
  modelId?: string;
}): Promise<ChatSession> {
  const { data } = await api.post<ChatSession>(
    `/chat-sessions/?user_id=${encodeURIComponent(USER_ID)}`,
    {
      userId: USER_ID,
      title: opts?.title,
      personaId: opts?.personaId,
      modelId: opts?.modelId,
    }
  );
  return data;
}

export async function listUserSessions(options?: {
  limit?: number;
  status?: "active" | "archived" | "deleted";
  search?: string;
  sortBy?: "created_at" | "updated_at" | "last_message_at";
  sortOrder?: "asc" | "desc";
}): Promise<SessionListResponse> {
  const params = new URLSearchParams();
  if (options?.limit) params.append("limit", options.limit.toString());
  if (options?.status) params.append("status", options.status);
  if (options?.search) params.append("search", options.search);
  if (options?.sortBy) params.append("sort_by", options.sortBy);
  if (options?.sortOrder) params.append("sort_order", options.sortOrder);

  const qs = params.toString();
  const { data } = await api.get<SessionListResponse>(
    `/chat-sessions/user/${USER_ID}${qs ? `?${qs}` : ""}`
  );
  return data;
}

export async function updateSession(
  sessionId: string,
  update: { title?: string; personaId?: string; modelId?: string }
): Promise<ChatSession> {
  const { data } = await api.put<ChatSession>(
    `/chat-sessions/${sessionId}`,
    update
  );
  return data;
}

export async function deleteSession(sessionId: string): Promise<void> {
  await api.delete(`/chat-sessions/${sessionId}`);
}

export async function archiveSession(sessionId: string): Promise<void> {
  await api.post(`/chat-sessions/${sessionId}/archive`);
}

// ── Message helpers ──────────────────────────────────────────────

/** Normalize a message from the API (camelCase) to our internal format (snake_case). */
function normalizeMessage(raw: Record<string, unknown>): ChatMessage {
  return {
    message_id:
      (raw.message_id as string) ||
      (raw.messageId as string) ||
      String(raw.id || Date.now()),
    session_id:
      (raw.session_id as string) || (raw.sessionId as string) || "",
    content: (raw.content as string) || "",
    message_type:
      ((raw.message_type as string) ||
        (raw.messageType as string) ||
        (raw.role as string) ||
        "user") as ChatMessage["message_type"],
    timestamp:
      (raw.timestamp as string) ||
      (raw.createdAt as string) ||
      new Date().toISOString(),
    metadata: raw.metadata as Record<string, unknown> | undefined,
  };
}

export async function listMessages(
  sessionId: string,
  options?: {
    limit?: number;
    sortOrder?: "asc" | "desc";
  }
): Promise<MessagesListResponse> {
  const params = new URLSearchParams();
  if (options?.limit) params.append("limit", options.limit.toString());
  if (options?.sortOrder) params.append("sort_order", options.sortOrder);

  const qs = params.toString();
  const { data } = await api.get<MessagesListResponse>(
    `/chat-messages/${sessionId}/messages${qs ? `?${qs}` : ""}`
  );
  // Normalize messages from API camelCase to our snake_case format
  if (data.messages) {
    data.messages = data.messages.map((m) =>
      normalizeMessage(m as unknown as Record<string, unknown>)
    );
  }
  return data;
}

// ── Streaming chat ───────────────────────────────────────────────

export async function* sendMessageStream(
  prompt: string,
  sessionId: string,
  modelId?: string,
  personaId?: string
): AsyncGenerator<StreamChunk, void, unknown> {
  const body = {
    model_name: modelId || "default",
    prompt,
    session: sessionId,
    method: "POST",
    stream: true,
    persona_id: personaId,
    userId: USER_ID,
  };

  for await (const raw of streamRequest("/ai-chat/", body)) {
    // streamRequest already parses SSE into { type, data }
    if (raw.type === "error") {
      yield { type: "error", data: raw.data };
    } else if (raw.type === "thinking") {
      yield { type: "thinking", data: raw.data };
    } else if (raw.type === "metadata") {
      try {
        const meta = JSON.parse(raw.data);
        yield { type: "metadata", data: "", metadata: meta };
      } catch {
        yield { type: "metadata", data: raw.data };
      }
    } else {
      // "chunk" (most common)
      yield { type: "chunk", data: raw.data };
    }
  }
}
