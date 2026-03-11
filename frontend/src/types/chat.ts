export interface ChatSession {
  id: string;
  sessionId?: string;
  session_id?: string;
  userId: string;
  title?: string;
  personaId?: string;
  modelId?: string;
  messageCount: number;
  lastMessageAt?: string;
  createdAt: string;
  updatedAt: string;
  status: "active" | "archived" | "deleted";
}

export interface ChatMessage {
  message_id: string;
  session_id: string;
  content: string;
  message_type: "user" | "assistant" | "system";
  timestamp: string;
  metadata?: Record<string, unknown>;
}

export interface StreamChunk {
  type: "chunk" | "tool" | "metadata" | "error";
  data: string;
  metadata?: {
    model_used?: string;
    tokens_used?: number;
    processing_time?: number;
  };
}

export interface SessionListResponse {
  success: boolean;
  sessions: ChatSession[];
  totalCount: number;
  hasMore: boolean;
  lastEvaluatedKey?: string;
  lastUpdated: string;
  error?: string;
}

export interface MessagesListResponse {
  success: boolean;
  messages: ChatMessage[];
  total_count: number;
  has_more: boolean;
  last_evaluated_key?: string;
  last_updated: string;
  error?: string;
}
