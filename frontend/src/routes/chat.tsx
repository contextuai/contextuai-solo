import { useState, useEffect, useCallback, useRef } from "react";
import type { ChatSession, ChatMessage } from "@/types/chat";
import type { ModelConfig } from "@/lib/api/models-client";
import type { Persona } from "@/lib/api/personas-client";
import { getModels } from "@/lib/api/models-client";
import { useAiMode } from "@/contexts/ai-mode-context";
import { getPersonas } from "@/lib/api/personas-client";
import {
  generateSessionId,
  createSession,
  listUserSessions,
  listMessages,
  sendMessageStream,
  deleteSession,
  archiveSession,
  updateSession,
} from "@/lib/api/chat-client";
import ChatSidebar from "@/components/chat/chat-sidebar";
import ChatHeader from "@/components/chat/chat-header";
import ChatInput from "@/components/chat/chat-input";
import MessageList from "@/components/chat/message-list";
import { Dialog } from "@/components/ui/dialog";
import { AlertTriangle } from "lucide-react";

export default function ChatPage() {
  const { aiMode } = useAiMode();

  // ── Data state ─────────────────────────────────────────────────
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);

  // ── Active session state ───────────────────────────────────────
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionTitle, setSessionTitle] = useState("New Chat");
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [selectedPersonaId, setSelectedPersonaId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  // ── UI state ───────────────────────────────────────────────────
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingThinking, setStreamingThinking] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [errorModal, setErrorModal] = useState<string | null>(null);

  // Abort controller for stopping stream
  const abortRef = useRef(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  // ── Load initial data (wait for backend to be ready) ──────────
  useEffect(() => {
    let cancelled = false;

    async function waitForBackend() {
      // Poll /health until the backend responds (handles cold-start delay)
      for (let i = 0; i < 60; i++) {
        if (cancelled) return;
        try {
          const resp = await fetch("http://127.0.0.1:18741/health");
          if (resp.ok) break;
        } catch {
          // backend not ready yet
        }
        await new Promise((r) => setTimeout(r, 1000));
      }
      if (cancelled) return;

      // Backend is ready — load all data
      import("@/lib/api/local-models-client")
        .then((m) => m.syncLocalModels())
        .catch(() => {})
        .finally(() => loadModels());
      loadPersonas();
      loadSessions();
    }

    waitForBackend();
    return () => { cancelled = true; };
  }, []);

  // Re-fetch models when AI mode changes
  useEffect(() => {
    loadModels();
  }, [aiMode]);

  // Keyboard shortcut: Ctrl/Cmd+N for new chat
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "n") {
        e.preventDefault();
        handleNewChat();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  async function loadModels() {
    try {
      const data = await getModels(aiMode);
      setModels(data);

      // Auto-select: if current selection is not in the new list, pick first
      const currentValid = data.some((m) => m.id === selectedModelId && m.enabled);
      if (!currentValid) {
        const first = data.find((m) => m.enabled);
        if (first) {
          setSelectedModelId(first.id);
        } else {
          setSelectedModelId(null);
        }
      }
    } catch (err) {
      console.warn("Failed to load models:", err);
    }
  }

  async function loadPersonas() {
    try {
      const data = await getPersonas();
      setPersonas(data);
    } catch (err) {
      console.warn("Failed to load personas:", err);
    }
  }

  async function loadSessions() {
    try {
      const response = await listUserSessions({
        limit: 50,
        status: "active",
        sortBy: "updated_at",
        sortOrder: "desc",
      });
      setSessions(response.sessions || []);
    } catch (err) {
      console.warn("Failed to load sessions:", err);
    }
  }

  // ── Session switching ──────────────────────────────────────────

  const handleSelectSession = useCallback(async (sessionId: string) => {
    setActiveSessionId(sessionId);
    setMessages([]);
    setStreamingContent("");
    setStreamingThinking("");
    setInput("");

    // Find session in list for title/model/persona
    const session = sessions.find(
      (s) => (s.id || s.sessionId || s.session_id) === sessionId
    );
    if (session) {
      setSessionTitle(session.title || "New Chat");
      if (session.modelId) setSelectedModelId(session.modelId);
      if (session.personaId) setSelectedPersonaId(session.personaId);
    }

    // Load messages
    try {
      const res = await listMessages(sessionId, {
        limit: 100,
        sortOrder: "asc",
      });
      setMessages(res.messages || []);
    } catch (err) {
      console.warn("Failed to load messages:", err);
    }
  }, [sessions]);

  const handleNewChat = useCallback(() => {
    setActiveSessionId(null);
    setMessages([]);
    setStreamingContent("");
    setStreamingThinking("");
    setSessionTitle("New Chat");
    setInput("");
  }, []);

  // ── Sending messages ───────────────────────────────────────────

  const handleSend = useCallback(async () => {
    const prompt = input.trim();
    if (!prompt || isStreaming) return;

    setInput("");
    abortRef.current = false;

    let sessionId = activeSessionId;

    // Create session on first message
    if (!sessionId) {
      const newId = generateSessionId();
      sessionId = newId;
      setActiveSessionId(newId);

      // Create backend session
      try {
        const created = await createSession({
          title: prompt.slice(0, 30),
          modelId: selectedModelId || undefined,
          personaId: selectedPersonaId || undefined,
        });
        const realId =
          created.id || created.sessionId || created.session_id || newId;
        sessionId = realId;
        setActiveSessionId(realId);
        setSessionTitle(prompt.slice(0, 30));

        // Refresh session list from backend (avoids duplicates from optimistic add + reload)
        loadSessions();
      } catch (err) {
        console.warn("Failed to create session, using local ID:", err);
      }
    }

    // Optimistic user message
    const userMsg: ChatMessage = {
      message_id: `msg_${Date.now()}_user`,
      session_id: sessionId,
      content: prompt,
      message_type: "user",
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    // Start streaming
    setIsStreaming(true);
    setStreamingContent("");
    setStreamingThinking("");

    const controller = new AbortController();
    abortControllerRef.current = controller;

    let fullResponse = "";
    let fullThinking = "";

    try {
      for await (const chunk of sendMessageStream(
        prompt,
        sessionId,
        selectedModelId || undefined,
        selectedPersonaId || undefined,
        controller.signal
      )) {
        if (abortRef.current) break;

        if (chunk.type === "thinking") {
          fullThinking += chunk.data;
          setStreamingThinking(fullThinking);
        } else if (chunk.type === "chunk") {
          fullResponse += chunk.data;
          setStreamingContent(fullResponse);
        } else if (chunk.type === "error") {
          setErrorModal(chunk.data);
        }
        // metadata chunks are silently consumed
      }
    } catch (err) {
      // Ignore abort errors — those are intentional stops
      const isAbort = abortRef.current || (err instanceof DOMException && err.name === "AbortError");
      if (!isAbort) {
        setErrorModal(err instanceof Error ? err.message : "An unexpected error occurred");
      }
    }
    abortControllerRef.current = null;

    // Finalize: add assistant message
    if (fullResponse || fullThinking) {
      const assistantMsg: ChatMessage = {
        message_id: `msg_${Date.now()}_assistant`,
        session_id: sessionId,
        content: fullResponse,
        reasoning: fullThinking || undefined,
        message_type: "assistant",
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    }

    setIsStreaming(false);
    setStreamingContent("");
    setStreamingThinking("");

    // Refresh session list to update message counts
    loadSessions();
  }, [input, isStreaming, activeSessionId, selectedModelId, selectedPersonaId]);

  const handleStop = useCallback(() => {
    abortRef.current = true;
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
  }, []);

  // ── Session management ─────────────────────────────────────────

  const handleDeleteSession = useCallback(
    async (sessionId: string) => {
      try {
        await deleteSession(sessionId);
        setSessions((prev) =>
          prev.filter(
            (s) => (s.id || s.sessionId || s.session_id) !== sessionId
          )
        );
        if (activeSessionId === sessionId) {
          handleNewChat();
        }
      } catch (err) {
        console.warn("Failed to delete session:", err);
      }
    },
    [activeSessionId, handleNewChat]
  );

  const handleArchiveSession = useCallback(
    async (sessionId: string) => {
      try {
        await archiveSession(sessionId);
        setSessions((prev) =>
          prev.filter(
            (s) => (s.id || s.sessionId || s.session_id) !== sessionId
          )
        );
        if (activeSessionId === sessionId) {
          handleNewChat();
        }
      } catch (err) {
        console.warn("Failed to archive session:", err);
      }
    },
    [activeSessionId, handleNewChat]
  );

  const handleRenameSession = useCallback(
    async (title: string) => {
      setSessionTitle(title);
      if (activeSessionId) {
        try {
          await updateSession(activeSessionId, { title });
          setSessions((prev) =>
            prev.map((s) => {
              const sid = s.id || s.sessionId || s.session_id;
              return sid === activeSessionId ? { ...s, title } : s;
            })
          );
        } catch (err) {
          console.warn("Failed to rename session:", err);
        }
      }
    },
    [activeSessionId]
  );

  // ── Render ─────────────────────────────────────────────────────

  return (
    <div className="flex h-screen overflow-hidden">
      <ChatSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        onDeleteSession={handleDeleteSession}
        onArchiveSession={handleArchiveSession}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
      />

      <div className="flex-1 flex flex-col min-w-0">
        <ChatHeader
          sessionTitle={sessionTitle}
          onRenameSession={handleRenameSession}
        />

        <MessageList
          messages={messages}
          streamingContent={streamingContent}
          streamingThinking={streamingThinking}
          isStreaming={isStreaming}
        />

        <ChatInput
          value={input}
          onChange={setInput}
          onSend={handleSend}
          onStop={handleStop}
          isStreaming={isStreaming}
          models={models}
          personas={personas}
          selectedModelId={selectedModelId}
          selectedPersonaId={selectedPersonaId}
          onSelectModel={setSelectedModelId}
          onSelectPersona={setSelectedPersonaId}
        />
      </div>

      {/* Error modal */}
      <Dialog
        open={!!errorModal}
        onClose={() => setErrorModal(null)}
        title="Model Error"
        actions={
          <button
            onClick={() => setErrorModal(null)}
            className="px-4 py-2 text-sm font-medium text-white bg-primary-500 hover:bg-primary-600 rounded-lg transition-colors"
          >
            OK
          </button>
        }
      >
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-500 mt-0.5 shrink-0" />
          <p className="text-sm text-neutral-700 dark:text-neutral-300 whitespace-pre-wrap">
            {errorModal}
          </p>
        </div>
      </Dialog>
    </div>
  );
}
