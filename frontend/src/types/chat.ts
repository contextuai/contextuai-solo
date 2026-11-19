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

export interface ChatCitation {
  index: number;
  doc_id?: string;
  filename: string;
  page?: number | null;
  chunk_index?: number;
  score?: number;
  vector_score?: number;
  bm25_score?: number;
  excerpt: string;
  mode?: "full_context" | "hybrid_rag";
}

export interface DlpRedactionSummary {
  total: number;
  categories: string[];
}

export interface ChatMessageMetadata {
  citations?: ChatCitation[];
  rag_mode?: "full_context" | "hybrid_rag";
  dlp_redaction?: DlpRedactionSummary;
  [key: string]: unknown;
}

export interface ChatMessage {
  message_id: string;
  session_id: string;
  content: string;
  reasoning?: string;
  message_type: "user" | "assistant" | "system";
  timestamp: string;
  metadata?: ChatMessageMetadata;
}

export interface StreamChunk {
  type: "chunk" | "thinking" | "tool" | "metadata" | "error";
  data: string;
  metadata?: {
    model_used?: string;
    tokens_used?: number;
    processing_time?: number;
    citations?: ChatCitation[];
    rag_mode?: "full_context" | "hybrid_rag";
    dlp_redaction?: DlpRedactionSummary;
    [key: string]: unknown;
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
