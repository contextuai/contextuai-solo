import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  FolderOpen,
  Loader2,
  Play,
  Send,
  ShieldAlert,
  ShieldCheck,
  Square,
  Terminal,
  Trash2,
  User,
  Wrench,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { openFolder } from "@/lib/tauri-fs";
import {
  type CoderProject,
  deleteCoderProject,
  getCoderProject,
  startCoderProject,
  stopCoderProject,
  streamCoderOutput,
  updateCoderProject,
} from "@/lib/api/coder-client";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

const DEFAULT_PREVIEW_PORT = 5173;

export default function CoderProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<CoderProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [output, setOutput] = useState<string[]>([]);
  const streamCtrlRef = useRef<AbortController | null>(null);
  const outputBoxRef = useRef<HTMLDivElement | null>(null);

  const reload = useCallback(async () => {
    if (!id) return;
    try {
      const next = await getCoderProject(id);
      setProject(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load project");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    reload();
  }, [reload]);

  // Auto-scroll the output panel as new lines arrive.
  useEffect(() => {
    const el = outputBoxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [output]);

  // Tear down any active SSE on unmount.
  useEffect(() => {
    return () => {
      streamCtrlRef.current?.abort();
    };
  }, []);

  function startStreaming() {
    if (!id) return;
    streamCtrlRef.current?.abort();
    const ctrl = new AbortController();
    streamCtrlRef.current = ctrl;
    setOutput([]);
    (async () => {
      try {
        for await (const line of streamCoderOutput(id, ctrl.signal)) {
          setOutput((prev) => [...prev, line]);
        }
      } catch {
        // Stream closed — fine.
      }
    })();
  }

  async function handleRun() {
    if (!project || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await startCoderProject(project.project_id);
      if (result.status === "failed") {
        setError(result.error || "Failed to start project");
      } else {
        startStreaming();
      }
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Run failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleStop() {
    if (!project || busy) return;
    setBusy(true);
    setError(null);
    try {
      await stopCoderProject(project.project_id);
      streamCtrlRef.current?.abort();
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Stop failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleTrust() {
    if (!project) return;
    try {
      const updated = await updateCoderProject(project.project_id, {
        trusted: !project.trusted,
      });
      setProject(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Trust toggle failed");
    }
  }

  async function handleOpenFolder() {
    if (!project) return;
    const ok = await openFolder(project.folder_path);
    if (!ok) {
      // Non-Tauri / failed — fall back to copy-to-clipboard for visibility.
      try {
        await navigator.clipboard.writeText(project.folder_path);
      } catch {
        // ignore
      }
    }
  }

  async function handleDelete() {
    if (!project) return;
    if (
      !confirm(
        `Delete "${project.name}"? This removes the project record but keeps the folder on disk.`,
      )
    )
      return;
    try {
      await deleteCoderProject(project.project_id);
      navigate("/coder/projects");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 px-8 py-8 text-sm text-neutral-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading project…
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-8">
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          {error || "Project not found."}
        </p>
        <Button
          size="sm"
          variant="ghost"
          className="mt-4"
          onClick={() => navigate("/coder/projects")}
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to projects
        </Button>
      </div>
    );
  }

  const running = project.status === "running" || project.process_pid != null;
  const previewPort = project.preview_port ?? DEFAULT_PREVIEW_PORT;
  const previewUrl = `http://localhost:${previewPort}`;

  return (
    <div className="flex flex-col h-full overflow-hidden bg-neutral-50 dark:bg-neutral-950">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 px-6 py-4 border-b border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900">
        <div className="flex items-start gap-3 min-w-0">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => navigate("/coder/projects")}
          >
            <ArrowLeft className="w-3.5 h-3.5" />
          </Button>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-semibold text-neutral-900 dark:text-white truncate">
                {project.name}
              </h1>
              {running && <Badge variant="success" dot>Running</Badge>}
              <Badge variant="info">{project.runtime}</Badge>
              {project.trusted ? (
                <Badge variant="success">
                  <ShieldCheck className="w-3 h-3" /> Trusted
                </Badge>
              ) : (
                <Badge variant="warning">
                  <ShieldAlert className="w-3 h-3" /> Untrusted
                </Badge>
              )}
            </div>
            <div
              className="text-[11px] font-mono text-neutral-500 dark:text-neutral-400 mt-1 truncate"
              title={project.folder_path}
            >
              {project.folder_path}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={handleOpenFolder}>
            <FolderOpen className="w-3.5 h-3.5" /> Open folder
          </Button>
          <Button size="sm" variant="ghost" onClick={handleToggleTrust}>
            {project.trusted ? (
              <>
                <ShieldAlert className="w-3.5 h-3.5" /> Untrust
              </>
            ) : (
              <>
                <ShieldCheck className="w-3.5 h-3.5" /> Trust
              </>
            )}
          </Button>
          <Button size="sm" variant="danger" onClick={handleDelete}>
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {error && (
        <div className="mx-6 mt-3 rounded-xl border border-red-200 dark:border-red-700/40 bg-red-50 dark:bg-red-500/5 px-4 py-2 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {/* Two-column body */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-3 p-3 min-h-0">
        <ChatPanel projectId={project.project_id} />
        <RunPanel
          project={project}
          running={running}
          busy={busy}
          previewUrl={previewUrl}
          output={output}
          outputBoxRef={outputBoxRef}
          onRun={handleRun}
          onStop={handleStop}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chat panel — stub for PR 6
// ---------------------------------------------------------------------------

function ChatPanel({ projectId: _projectId }: { projectId: string }) {
  // TODO(PR7): wire to /api/v1/ai-chat with streaming + persistent thread per
  // project. For PR 6 this is a local-only stub that echoes a stubbed reply
  // so the surface is in place.
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");

  function handleSend() {
    const text = draft.trim();
    if (!text) return;
    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content: text,
    };
    const assistantMsg: ChatMessage = {
      id: `a-${Date.now()}`,
      role: "assistant",
      content:
        "Chat wiring lands in PR 7 — your message was captured but not sent to the model yet.",
    };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setDraft("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex flex-col rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 min-h-0">
      <div className="flex items-center gap-2 px-4 h-11 border-b border-neutral-200 dark:border-neutral-800">
        <Wrench className="w-3.5 h-3.5 text-primary-500" />
        <span className="text-xs font-semibold text-neutral-900 dark:text-white">
          Chat
        </span>
        <span className="text-[11px] text-neutral-400">PR 6 stub</span>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 min-h-0">
        {messages.length === 0 ? (
          <div className="text-xs text-neutral-500 dark:text-neutral-400 text-center py-12">
            Tell Solo Coder what you want to build.
            <br />
            <span className="text-[11px]">
              (Chat is wired in PR 7 — for now, the surface is here so you can
              see the layout.)
            </span>
          </div>
        ) : (
          messages.map((m) => (
            <ChatBubble key={m.id} message={m} />
          ))
        )}
      </div>

      <div className="flex items-end gap-2 p-3 border-t border-neutral-200 dark:border-neutral-800">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
          placeholder="Describe what to build, or ask a question…"
          className={cn(
            "flex-1 resize-none px-3 py-2 rounded-xl text-sm",
            "bg-neutral-50 dark:bg-neutral-800",
            "border border-neutral-200 dark:border-neutral-700",
            "text-neutral-900 dark:text-white",
            "placeholder:text-neutral-400 dark:placeholder:text-neutral-500",
            "focus:outline-none focus:ring-2 focus:ring-primary-500/40 focus:border-primary-500",
          )}
        />
        <Button size="sm" variant="primary" onClick={handleSend}>
          <Send className="w-3.5 h-3.5" /> Send
        </Button>
      </div>
    </div>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div
      className={cn(
        "flex gap-2",
        isUser ? "justify-end" : "justify-start",
      )}
    >
      {!isUser && (
        <div className="flex-shrink-0 w-7 h-7 rounded-lg bg-primary-50 dark:bg-primary-500/10 text-primary-500 flex items-center justify-center">
          <Wrench className="w-3.5 h-3.5" />
        </div>
      )}
      <div
        className={cn(
          "max-w-[80%] px-3 py-2 rounded-2xl text-sm whitespace-pre-wrap break-words",
          isUser
            ? "bg-primary-500 text-white"
            : "bg-neutral-100 dark:bg-neutral-800 text-neutral-900 dark:text-white",
        )}
      >
        {message.content}
      </div>
      {isUser && (
        <div className="flex-shrink-0 w-7 h-7 rounded-lg bg-neutral-100 dark:bg-neutral-800 text-neutral-500 flex items-center justify-center">
          <User className="w-3.5 h-3.5" />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Run + preview panel
// ---------------------------------------------------------------------------

function RunPanel({
  project,
  running,
  busy,
  previewUrl,
  output,
  outputBoxRef,
  onRun,
  onStop,
}: {
  project: CoderProject;
  running: boolean;
  busy: boolean;
  previewUrl: string;
  output: string[];
  outputBoxRef: React.RefObject<HTMLDivElement | null>;
  onRun: () => void;
  onStop: () => void;
}) {
  const runDisabled = !project.trusted || busy || running;
  const runTooltip = !project.trusted
    ? "Trust this project first to allow Solo Coder to run commands"
    : undefined;

  return (
    <div className="flex flex-col rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 min-h-0">
      <div className="flex items-center justify-between gap-2 px-4 h-11 border-b border-neutral-200 dark:border-neutral-800">
        <div className="flex items-center gap-2">
          <Play className="w-3.5 h-3.5 text-primary-500" />
          <span className="text-xs font-semibold text-neutral-900 dark:text-white">
            Preview & Run
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {running ? (
            <Button
              size="sm"
              variant="danger"
              onClick={onStop}
              disabled={busy}
            >
              {busy ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Square className="w-3.5 h-3.5" />
              )}
              Stop
            </Button>
          ) : (
            <span title={runTooltip}>
              <Button
                size="sm"
                variant="primary"
                onClick={onRun}
                disabled={runDisabled}
              >
                {busy ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Play className="w-3.5 h-3.5" />
                )}
                Run
              </Button>
            </span>
          )}
        </div>
      </div>

      {/* Preview */}
      <div className="flex-1 min-h-0 grid grid-rows-[1fr_auto]">
        <div className="bg-neutral-50 dark:bg-neutral-950 border-b border-neutral-200 dark:border-neutral-800 min-h-0 relative">
          {running ? (
            <iframe
              src={previewUrl}
              title={`Preview ${project.name}`}
              className="w-full h-full border-0"
              sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
            />
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-6">
              <div className="w-14 h-14 rounded-2xl bg-primary-50 dark:bg-primary-500/10 text-primary-500 flex items-center justify-center mb-3">
                <Play className="w-6 h-6" />
              </div>
              <p className="text-sm text-neutral-700 dark:text-neutral-300 font-medium">
                Run to start preview
              </p>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                Once running, the iframe will load{" "}
                <span className="font-mono">{previewUrl}</span>.
              </p>
              {!project.trusted && (
                <p className="text-[11px] text-amber-600 dark:text-amber-400 mt-3">
                  Trust the project first to enable Run.
                </p>
              )}
            </div>
          )}
        </div>

        {/* Output terminal */}
        <div className="flex flex-col h-48 bg-neutral-950 text-neutral-100">
          <div className="flex items-center gap-2 px-3 h-8 border-b border-neutral-800">
            <Terminal className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-[11px] font-mono text-neutral-300">
              output
            </span>
            {project.process_pid != null && (
              <span className="text-[11px] font-mono text-neutral-500">
                pid {project.process_pid}
              </span>
            )}
          </div>
          <div
            ref={outputBoxRef}
            className="flex-1 overflow-y-auto px-3 py-2 font-mono text-[11px] leading-relaxed"
          >
            {output.length === 0 ? (
              <div className="text-neutral-500">
                {running
                  ? "Waiting for output…"
                  : "No output yet. Hit Run to start the project."}
              </div>
            ) : (
              output.map((line, i) => (
                <div key={i} className="whitespace-pre-wrap break-all">
                  {line}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
