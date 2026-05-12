import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Bug,
  CheckCircle2,
  Database,
  FolderOpen,
  Loader2,
  MoreHorizontal,
  Play,
  Send,
  ShieldAlert,
  ShieldCheck,
  Square,
  Terminal,
  Trash2,
  Upload,
  User,
  Wrench,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { openFolder } from "@/lib/tauri-fs";
import { useMode } from "@/contexts/mode-context";
import {
  type CoderProject,
  type IndexAsKbSchedule,
  deleteCoderProject,
  getCoderProject,
  indexCoderProjectAsKb,
  startCoderProject,
  stopCoderProject,
  streamCoderOutput,
  updateCoderProject,
} from "@/lib/api/coder-client";
import {
  type KnowledgeBase,
  listKnowledgeBases,
} from "@/lib/api/knowledge-base-client";
import {
  type ConnectionSummary,
  listOutboundConnections,
} from "@/lib/api/automations-client";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

const DEFAULT_PREVIEW_PORT = 5173;

export default function CoderProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { setMode } = useMode();
  const [project, setProject] = useState<CoderProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [output, setOutput] = useState<string[]>([]);
  const streamCtrlRef = useRef<AbortController | null>(null);
  const outputBoxRef = useRef<HTMLDivElement | null>(null);

  // 3-dot menu + handoff dialogs (PR 7)
  const [menuOpen, setMenuOpen] = useState(false);
  const [indexDialogOpen, setIndexDialogOpen] = useState(false);
  const [distributeDialogOpen, setDistributeDialogOpen] = useState(false);
  const [handoffBanner, setHandoffBanner] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  // Best-effort last-error extraction from the output stream — picks up the
  // last few lines that smell like errors (or just the tail if nothing matched).
  const lastErrorLines = useMemo(() => {
    if (output.length === 0) return "";
    const errorRegex = /(error|exception|traceback|failed|fatal|panic)/i;
    const matched: string[] = [];
    for (let i = output.length - 1; i >= 0 && matched.length < 8; i -= 1) {
      const line = output[i];
      if (errorRegex.test(line)) matched.unshift(line);
    }
    if (matched.length > 0) return matched.join("\n");
    // Fallback: last 5 lines.
    return output.slice(-5).join("\n");
  }, [output]);

  // Close the menu on outside click.
  useEffect(() => {
    if (!menuOpen) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    window.addEventListener("mousedown", handleClick);
    return () => window.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

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

  // ──────────── PR 7 handoff handlers ────────────

  function handleDiagnoseLatestError() {
    if (!project) return;
    setMenuOpen(false);
    const errorBlock = lastErrorLines.trim() || "(no recent error captured)";
    const prompt =
      `@bug-analyzer Help me diagnose this error from my Coder project ` +
      `'${project.name}':\n\n\`\`\`\n${errorBlock}\n\`\`\``;
    // Switch to Solo mode and route to the chat page with prefill.
    setMode("solo");
    navigate(`/?prefill=${encodeURIComponent(prompt)}`);
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
          <div className="relative" ref={menuRef}>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setMenuOpen((v) => !v)}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              title="More actions"
            >
              <MoreHorizontal className="w-3.5 h-3.5" />
            </Button>
            {menuOpen && (
              <div
                role="menu"
                className={cn(
                  "absolute right-0 top-full mt-1 z-30 w-64",
                  "rounded-xl border border-neutral-200 dark:border-neutral-800",
                  "bg-white dark:bg-neutral-900 shadow-lg p-1",
                )}
              >
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false);
                    setIndexDialogOpen(true);
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-left rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-800 dark:text-neutral-100"
                >
                  <Database className="w-3.5 h-3.5 text-primary-500" />
                  Index as Knowledge Base
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={handleDiagnoseLatestError}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-left rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-800 dark:text-neutral-100"
                >
                  <Bug className="w-3.5 h-3.5 text-amber-500" />
                  Diagnose latest error with @bug-analyzer
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false);
                    setDistributeDialogOpen(true);
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-left rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-800 dark:text-neutral-100"
                >
                  <Upload className="w-3.5 h-3.5 text-sky-500" />
                  Distribute artifact
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {handoffBanner && (
        <div className="mx-6 mt-3 rounded-xl border border-emerald-200 dark:border-emerald-700/40 bg-emerald-50 dark:bg-emerald-500/5 px-4 py-2 text-sm text-emerald-700 dark:text-emerald-300 flex items-center justify-between gap-3">
          <span className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
            <span>{handoffBanner}</span>
            <Link
              to="/knowledge"
              className="ml-1 underline underline-offset-2 hover:text-emerald-900 dark:hover:text-emerald-100"
            >
              Open Knowledge
            </Link>
          </span>
          <button
            type="button"
            onClick={() => setHandoffBanner(null)}
            className="p-1 rounded hover:bg-emerald-100 dark:hover:bg-emerald-500/10"
            aria-label="Dismiss"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {project && (
        <>
          <IndexAsKbDialog
            open={indexDialogOpen}
            project={project}
            onClose={() => setIndexDialogOpen(false)}
            onSuccess={(message) => {
              setIndexDialogOpen(false);
              setHandoffBanner(message);
            }}
          />
          <DistributeArtifactDialog
            open={distributeDialogOpen}
            project={project}
            onClose={() => setDistributeDialogOpen(false)}
          />
        </>
      )}

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
// Chat panel — wired to /api/v1/ai-chat (PR 12). One session per project so
// chat history is isolated from the global Chat page.
// ---------------------------------------------------------------------------

function ChatPanel({ projectId }: { projectId: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const sessionIdRef = useRef<string>(`coder-${projectId}`);
  const abortRef = useRef<AbortController | null>(null);

  async function handleSend() {
    const text = draft.trim();
    if (!text || busy) return;

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content: text,
    };
    const assistantId = `a-${Date.now()}`;
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
    };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setDraft("");
    setBusy(true);

    const ctl = new AbortController();
    abortRef.current = ctl;

    try {
      const { sendMessageStream } = await import("@/lib/api/chat-client");
      for await (const chunk of sendMessageStream(
        text,
        sessionIdRef.current,
        undefined,
        undefined,
        ctl.signal,
        undefined,
      )) {
        if (chunk.type === "chunk") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: m.content + chunk.data } : m,
            ),
          );
        } else if (chunk.type === "error") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + `\n\n[error] ${chunk.data}` }
                : m,
            ),
          );
        }
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  function handleStop() {
    abortRef.current?.abort();
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
        <span className="text-[11px] text-neutral-400 truncate">
          session {sessionIdRef.current.slice(0, 14)}…
        </span>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 min-h-0">
        {messages.length === 0 ? (
          <div className="text-xs text-neutral-500 dark:text-neutral-400 text-center py-12">
            Tell Solo Coder what you want to build.
            <br />
            <span className="text-[11px]">
              Uses your default model. Multi-agent roles arrive in the next PR.
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
          disabled={busy}
          placeholder="Describe what to build, or ask a question…"
          className={cn(
            "flex-1 resize-none px-3 py-2 rounded-xl text-sm",
            "bg-neutral-50 dark:bg-neutral-800",
            "border border-neutral-200 dark:border-neutral-700",
            "text-neutral-900 dark:text-white",
            "placeholder:text-neutral-400 dark:placeholder:text-neutral-500",
            "focus:outline-none focus:ring-2 focus:ring-primary-500/40 focus:border-primary-500",
            "disabled:opacity-60",
          )}
        />
        {busy ? (
          <Button size="sm" variant="ghost" onClick={handleStop}>
            <Square className="w-3.5 h-3.5" /> Stop
          </Button>
        ) : (
          <Button size="sm" variant="primary" onClick={handleSend}>
            <Send className="w-3.5 h-3.5" /> Send
          </Button>
        )}
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

// ---------------------------------------------------------------------------
// PR 7: Index-as-Knowledge-Base dialog
// ---------------------------------------------------------------------------

const SCHEDULE_OPTIONS: { value: IndexAsKbSchedule; label: string }[] = [
  { value: "manual", label: "Manual (run on demand)" },
  { value: "1h", label: "Every hour" },
  { value: "6h", label: "Every 6 hours" },
  { value: "24h", label: "Every 24 hours" },
];

function IndexAsKbDialog({
  open,
  project,
  onClose,
  onSuccess,
}: {
  open: boolean;
  project: CoderProject;
  onClose: () => void;
  onSuccess: (message: string) => void;
}) {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [selectedKbId, setSelectedKbId] = useState<string>("");
  const [schedule, setSchedule] = useState<IndexAsKbSchedule>("manual");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setErr(null);
    listKnowledgeBases()
      .then((list) => {
        if (cancelled) return;
        setKnowledgeBases(list);
        if (list.length > 0) setSelectedKbId(list[0].id);
      })
      .catch((e) => {
        if (cancelled) return;
        setErr(e instanceof Error ? e.message : "Failed to load KBs");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  async function handleIndex() {
    if (!selectedKbId) {
      setErr("Pick a knowledge base first.");
      return;
    }
    setSubmitting(true);
    setErr(null);
    try {
      await indexCoderProjectAsKb(project.project_id, {
        kb_id: selectedKbId,
        label: project.name,
        schedule,
      });
      onSuccess(
        `Indexing started — open Knowledge to follow progress.`,
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to start indexing");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Index project as Knowledge Base"
      actions={
        <>
          <Button variant="ghost" size="sm" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleIndex}
            disabled={submitting || loading || !selectedKbId}
          >
            {submitting ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Database className="w-3.5 h-3.5" />
            )}
            Index
          </Button>
        </>
      }
    >
      <p className="mb-4 text-xs text-neutral-500 dark:text-neutral-400">
        Add this project's folder as a folder-mapped source on a Knowledge
        Base. Files will be chunked, embedded locally, and queryable from
        chats and agents.
      </p>

      {loading ? (
        <div className="flex items-center gap-2 text-xs text-neutral-500">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Loading knowledge bases…
        </div>
      ) : knowledgeBases.length === 0 ? (
        <div className="rounded-lg border border-dashed border-neutral-300 dark:border-neutral-700 p-3 text-xs text-neutral-600 dark:text-neutral-400 flex items-center justify-between">
          <span>No knowledge bases yet.</span>
          <Link to="/knowledge" className="text-primary-600 hover:underline">
            Create one →
          </Link>
        </div>
      ) : (
        <>
          <div className="mb-4">
            <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
              Knowledge base
            </label>
            <div className="mt-1 max-h-48 overflow-y-auto rounded-lg border border-neutral-200 dark:border-neutral-700 divide-y divide-neutral-100 dark:divide-neutral-800">
              {knowledgeBases.map((kb) => (
                <label
                  key={kb.id}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 cursor-pointer text-sm",
                    selectedKbId === kb.id
                      ? "bg-primary-50 dark:bg-primary-500/10"
                      : "hover:bg-neutral-50 dark:hover:bg-neutral-800",
                  )}
                >
                  <input
                    type="radio"
                    name="kb"
                    value={kb.id}
                    checked={selectedKbId === kb.id}
                    onChange={() => setSelectedKbId(kb.id)}
                    className="accent-primary-500"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-neutral-900 dark:text-white truncate">
                      {kb.name}
                    </div>
                    <div className="text-[11px] text-neutral-500 dark:text-neutral-400">
                      {kb.doc_count} docs · {kb.chunk_count} chunks
                    </div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div className="mb-2">
            <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
              Schedule
            </label>
            <select
              value={schedule}
              onChange={(e) =>
                setSchedule(e.target.value as IndexAsKbSchedule)
              }
              className="mt-1 w-full rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 px-3 py-2 text-sm text-neutral-900 dark:text-white"
            >
              {SCHEDULE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        </>
      )}

      {err && (
        <div className="mt-3 rounded-lg border border-red-200 dark:border-red-700/40 bg-red-50 dark:bg-red-500/5 px-3 py-2 text-xs text-red-700 dark:text-red-300">
          {err}
        </div>
      )}
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// PR 7: Distribute-artifact dialog (stubbed — backend wiring lands later)
// ---------------------------------------------------------------------------

function DistributeArtifactDialog({
  open,
  project: _project,
  onClose,
}: {
  open: boolean;
  project: CoderProject;
  onClose: () => void;
}) {
  const [path, setPath] = useState("dist/index.html");
  const [connections, setConnections] = useState<ConnectionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedConnectionId, setSelectedConnectionId] = useState("");
  const [info, setInfo] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setInfo(null);
    listOutboundConnections()
      .then((list) => {
        if (cancelled) return;
        setConnections(list);
        if (list.length > 0) setSelectedConnectionId(list[0].id);
      })
      .catch(() => {
        if (!cancelled) setConnections([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  function handleDistribute() {
    // PR 7 ships the dialog UX only — file streaming from disk to a
    // distribution channel will firm up in a follow-up PR. Show a friendly
    // placeholder so the menu item is functional rather than misleading.
    setInfo(
      "Distribute artifact is coming soon — file streaming from the project folder isn't wired in this build.",
    );
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Distribute artifact"
      actions={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleDistribute}
            disabled={!path.trim() || !selectedConnectionId}
          >
            <Upload className="w-3.5 h-3.5" />
            Distribute
          </Button>
        </>
      }
    >
      <p className="mb-4 text-xs text-neutral-500 dark:text-neutral-400">
        Pick a file inside the project folder and a distribution channel.
      </p>

      <div className="mb-3">
        <Input
          label="Path inside the project folder"
          placeholder="dist/index.html"
          value={path}
          onChange={(e) => setPath(e.target.value)}
        />
      </div>

      <div className="mb-2">
        <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
          Connection
        </label>
        {loading ? (
          <div className="mt-2 flex items-center gap-2 text-xs text-neutral-500">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Loading connections…
          </div>
        ) : connections.length === 0 ? (
          <div className="mt-1 rounded-lg border border-dashed border-neutral-300 dark:border-neutral-700 p-3 text-xs text-neutral-600 dark:text-neutral-400 flex items-center justify-between">
            <span>No outbound connections configured.</span>
            <Link to="/connections" className="text-primary-600 hover:underline">
              Configure →
            </Link>
          </div>
        ) : (
          <select
            value={selectedConnectionId}
            onChange={(e) => setSelectedConnectionId(e.target.value)}
            className="mt-1 w-full rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 px-3 py-2 text-sm text-neutral-900 dark:text-white"
          >
            <option value="">Pick a connection…</option>
            {connections.map((c) => (
              <option key={c.id} value={c.id}>
                {c.display_name || c.platform} ({c.platform})
              </option>
            ))}
          </select>
        )}
      </div>

      {info && (
        <div className="mt-3 rounded-lg border border-amber-200 dark:border-amber-700/40 bg-amber-50 dark:bg-amber-500/5 px-3 py-2 text-xs text-amber-800 dark:text-amber-300">
          {info}
        </div>
      )}
    </Dialog>
  );
}
