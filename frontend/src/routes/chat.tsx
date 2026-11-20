import { useState, useEffect, useCallback, useRef } from "react";
import type { ChatSession, ChatMessage, ChatMessageMetadata } from "@/types/chat";
import type { ModelConfig } from "@/lib/api/models-client";
import type { Persona } from "@/lib/api/personas-client";
import type { KnowledgeBase } from "@/lib/api/knowledge-base-client";
import { getModels } from "@/lib/api/models-client";
import { useAiMode } from "@/contexts/ai-mode-context";
import { getPersonas } from "@/lib/api/personas-client";
import { listKnowledgeBases } from "@/lib/api/knowledge-base-client";
import {
  generateSessionId,
  createSession,
  listUserSessions,
  listMessages,
  sendMessageStream,
  deleteSession,
  archiveSession,
  updateSession,
  uploadChatFile,
} from "@/lib/api/chat-client";
import ChatSidebar from "@/components/chat/chat-sidebar";
import ChatHeader from "@/components/chat/chat-header";
import ChatInput, { type AttachedChatFile } from "@/components/chat/chat-input";
import MessageList from "@/components/chat/message-list";
import { MemoryDrawer } from "@/components/chat/memory-drawer";
import { ToolApprovalModal } from "@/components/chat/tool-approval-modal";
import { Dialog } from "@/components/ui/dialog";
import { AlertTriangle } from "lucide-react";

export default function ChatPage() {
  const { aiMode } = useAiMode();
  const aiModeRef = useRef(aiMode);
  aiModeRef.current = aiMode;
  const modelsFetchSeqRef = useRef(0);

  // ── Data state ─────────────────────────────────────────────────
  const [models, setModels] = useState<ModelConfig[]>([]);
  // True once the first models fetch has resolved — avoids flashing the
  // no-model nudge during initial load before the model list arrives.
  const [modelsLoaded, setModelsLoaded] = useState(false);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);

  // ── Active session state ───────────────────────────────────────
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionTitle, setSessionTitle] = useState("New Chat");
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [selectedPersonaId, setSelectedPersonaId] = useState<string | null>(null);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  // ── UI state ───────────────────────────────────────────────────
  const [input, setInput] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<AttachedChatFile[]>([]);
  const [uploadingFiles, setUploadingFiles] = useState(false);
  const [memoryDrawerOpen, setMemoryDrawerOpen] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingThinking, setStreamingThinking] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
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
      loadKnowledgeBases();
      loadSessions();
    }

    waitForBackend();
    return () => { cancelled = true; };
  }, []);

  // Re-fetch models when AI mode changes
  useEffect(() => {
    loadModels(aiMode);
  }, [aiMode]);

  // Keyboard shortcut: Ctrl/Cmd+N or M3 sidebar FAB for new chat
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "n") {
        e.preventDefault();
        handleNewChat();
      }
    };
    const handleNewChatEvent = () => handleNewChat();
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("contextuai:new-chat", handleNewChatEvent);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("contextuai:new-chat", handleNewChatEvent);
    };
  }, []);

  // Cross-mode handoff: pre-fill the chat input from `?prefill=...`, `?kb=...`, or `?model=...`
  // and then strip the params so a refresh doesn't repopulate them.
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const prefill = params.get("prefill");
      const kbParam = params.get("kb");
      const modelParam = params.get("model");
      let changed = false;
      if (prefill) {
        setInput(prefill);
        params.delete("prefill");
        changed = true;
      }
      if (kbParam) {
        setSelectedKnowledgeBaseId(kbParam);
        params.delete("kb");
        changed = true;
      }
      if (modelParam) {
        setSelectedModelId(modelParam.startsWith("local:") ? modelParam : `local:${modelParam}`);
        params.delete("model");
        changed = true;
      }
      if (changed) {
        const newSearch = params.toString();
        const newUrl =
          window.location.pathname +
          (newSearch ? `?${newSearch}` : "") +
          window.location.hash;
        window.history.replaceState({}, "", newUrl);
      }
    } catch {
      // ignore — best-effort prefill
    }
  }, []);

  async function loadModels(modeOverride?: typeof aiMode) {
    const seq = ++modelsFetchSeqRef.current;
    const targetMode = modeOverride ?? aiModeRef.current;
    try {
      const data = await getModels(targetMode);
      if (seq !== modelsFetchSeqRef.current) return;
      setModels(data);

      // Auto-select: if current selection is not in the new list, pick first
      setSelectedModelId((prevSelected) => {
        const currentValid = data.some((m) => m.id === prevSelected && m.enabled);
        if (currentValid) return prevSelected;
        const first = data.find((m) => m.enabled);
        return first ? first.id : null;
      });
    } catch (err) {
      console.warn("Failed to load models:", err);
    } finally {
      if (seq === modelsFetchSeqRef.current) {
        setModelsLoaded(true);
      }
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

  async function loadKnowledgeBases() {
    try {
      setKnowledgeBases(await listKnowledgeBases());
    } catch (err) {
      console.warn("Failed to load knowledge bases:", err);
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
    setAttachedFiles([]);

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
    setAttachedFiles([]);
  }, []);

  // ── File attachments ───────────────────────────────────────────

  const handleAttachFiles = useCallback(async (files: FileList | File[]) => {
    const fileArray = Array.from(files);
    if (fileArray.length === 0) return;
    setUploadingFiles(true);
    try {
      const uploaded = await Promise.all(
        fileArray.map(async (file) => {
          const res = await uploadChatFile(file);
          return {
            file_id: res.file_id,
            filename: res.original_filename || file.name,
            size: res.size ?? file.size,
          };
        })
      );
      setAttachedFiles((prev) => {
        const existing = new Set(prev.map((f) => f.file_id));
        return [...prev, ...uploaded.filter((u) => !existing.has(u.file_id))];
      });
    } catch (err) {
      setErrorModal(
        err instanceof Error ? err.message : "Failed to upload attached file"
      );
    } finally {
      setUploadingFiles(false);
    }
  }, []);

  const handleRemoveFile = useCallback((fileId: string) => {
    setAttachedFiles((prev) => prev.filter((f) => f.file_id !== fileId));
  }, []);

  // ── Sending messages ───────────────────────────────────────────

  const handleSend = useCallback(async () => {
    const prompt = input.trim();
    if (!prompt || isStreaming || uploadingFiles) return;

    const fileIds = attachedFiles.map((f) => f.file_id);
    setInput("");
    setAttachedFiles([]);
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
    let lastMetadata: ChatMessageMetadata | undefined = undefined;

    try {
      for await (const chunk of sendMessageStream(
        prompt,
        sessionId,
        selectedModelId || undefined,
        selectedPersonaId || undefined,
        controller.signal,
        selectedKnowledgeBaseId || undefined,
        fileIds.length > 0 ? fileIds : undefined
      )) {
        if (abortRef.current) break;

        if (chunk.type === "thinking") {
          fullThinking += chunk.data;
          setStreamingThinking(fullThinking);
        } else if (chunk.type === "chunk") {
          fullResponse += chunk.data;
          setStreamingContent(fullResponse);
        } else if (chunk.type === "metadata" && chunk.metadata) {
          lastMetadata = { ...(lastMetadata ?? {}), ...chunk.metadata };
        } else if (chunk.type === "error") {
          setErrorModal(chunk.data);
        }
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
        metadata: lastMetadata,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    }

    setIsStreaming(false);
    setStreamingContent("");
    setStreamingThinking("");

    // Refresh session list to update message counts
    loadSessions();
  }, [input, isStreaming, uploadingFiles, attachedFiles, activeSessionId, selectedModelId, selectedPersonaId, selectedKnowledgeBaseId]);

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
    <div className="relative flex h-full overflow-hidden">
      {/* M3 Floating Chat History Drawer (collapsed by default for full-width chat) */}
      {!sidebarCollapsed && (
        <>
          <div
            className="fixed inset-0 z-20 bg-black/20 backdrop-blur-[1px]"
            onClick={() => setSidebarCollapsed(true)}
          />
          <div className="absolute inset-y-0 left-0 z-30 h-full">
            <ChatSidebar
              sessions={sessions}
              activeSessionId={activeSessionId}
              onSelectSession={(id) => {
                handleSelectSession(id);
                setSidebarCollapsed(true);
              }}
              onNewChat={() => {
                handleNewChat();
                setSidebarCollapsed(true);
              }}
              onDeleteSession={handleDeleteSession}
              onArchiveSession={handleArchiveSession}
              collapsed={false}
              onToggleCollapse={() => setSidebarCollapsed(true)}
            />
          </div>
        </>
      )}

      <div className="flex-1 flex flex-col min-w-0">
        <ChatHeader
          sessionTitle={sessionTitle}
          onRenameSession={handleRenameSession}
          messages={messages}
          draftInput={input}
          selectedModel={models.find((m) => m.id === selectedModelId) ?? null}
          sessionsCount={sessions.length}
          historyOpen={!sidebarCollapsed}
          onToggleHistory={() => setSidebarCollapsed((c) => !c)}
          memoryOpen={memoryDrawerOpen}
          onToggleMemory={() => setMemoryDrawerOpen((o) => !o)}
        />

        <MessageList
          messages={messages}
          streamingContent={streamingContent}
          streamingThinking={streamingThinking}
          isStreaming={isStreaming}
          noModel={modelsLoaded && !models.some((m) => m.enabled)}
          onSelectStarterPrompt={(prompt) => setInput(prompt)}
        />

        <ToolApprovalModal className="mx-4 sm:mx-auto sm:w-full max-w-3xl mb-2" />

        <ChatInput
          value={input}
          onChange={setInput}
          onSend={handleSend}
          onStop={handleStop}
          isStreaming={isStreaming}
          models={models}
          personas={personas}
          knowledgeBases={knowledgeBases}
          selectedModelId={selectedModelId}
          selectedPersonaId={selectedPersonaId}
          selectedKnowledgeBaseId={selectedKnowledgeBaseId}
          onSelectModel={setSelectedModelId}
          onSelectPersona={setSelectedPersonaId}
          onSelectKnowledgeBase={setSelectedKnowledgeBaseId}
          attachedFiles={attachedFiles}
          onAttachFiles={handleAttachFiles}
          onRemoveFile={handleRemoveFile}
          uploadingFiles={uploadingFiles}
        />
      </div>

      <MemoryDrawer
        open={memoryDrawerOpen}
        onClose={() => setMemoryDrawerOpen(false)}
      />

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
