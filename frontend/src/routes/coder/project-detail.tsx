import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Bug,
  CheckCircle2,
  Code,
  Database,
  FileText,
  FolderOpen,
  Loader2,
  MessageSquareDashed,
  MoreHorizontal,
  Palette,
  Play,
  Send,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  Square,
  Telescope,
  Terminal,
  TestTube2,
  Trash2,
  Upload,
  Users,
  Wrench,
  X,
  ChevronRight,
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
import {
  type WorkflowPlan,
  type RoleKind,
  streamWorkflow,
  previewWorkflow,
} from "@/lib/api/coder-workflow-client";
import { TeamPanel } from "@/components/coder/team-panel";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface LocalChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  // For multi-agent messages
  roleId?: string;
  roleKind?: RoleKind;
  displayName?: string;
  modelId?: string;
  tokenCount?: number;
  frozen?: boolean;
}

type RightTab = "terminal" | "team";

const DEFAULT_PREVIEW_PORT = 5173;

// ---------------------------------------------------------------------------
// Role kind colors
// ---------------------------------------------------------------------------

const ROLE_KIND_COLORS: Record<RoleKind, string> = {
  coder: "bg-primary-500",
  reviewer: "bg-sky-500",
  security: "bg-rose-500",
  ui_ux: "bg-violet-500",
  docs: "bg-emerald-500",
  tester: "bg-amber-500",
  planner: "bg-indigo-500",
  custom: "bg-neutral-500",
};

const ROLE_KIND_ICONS: Record<RoleKind, React.ElementType> = {
  coder: Code,
  reviewer: MessageSquareDashed,
  security: ShieldCheck,
  ui_ux: Palette,
  docs: FileText,
  tester: TestTube2,
  planner: Telescope,
  custom: Settings2,
};

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

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

  // Right-pane tab
  const [rightTab, setRightTab] = useState<RightTab>("terminal");

  // 3-dot menu + handoff dialogs (PR 7)
  const [menuOpen, setMenuOpen] = useState(false);
  const [indexDialogOpen, setIndexDialogOpen] = useState(false);
  const [distributeDialogOpen, setDistributeDialogOpen] = useState(false);
  const [handoffBanner, setHandoffBanner] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  const lastErrorLines = useMemo(() => {
    if (output.length === 0) return "";
    const errorRegex = /(error|exception|traceback|failed|fatal|panic)/i;
    const matched: string[] = [];
    for (let i = output.length - 1; i >= 0 && matched.length < 8; i -= 1) {
      const line = output[i];
      if (errorRegex.test(line)) matched.unshift(line);
    }
    if (matched.length > 0) return matched.join("\n");
    return output.slice(-5).join("\n");
  }, [output]);

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

  useEffect(() => {
    const el = outputBoxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [output]);

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

  function handleDiagnoseLatestError() {
    if (!project) return;
    setMenuOpen(false);
    const errorBlock = lastErrorLines.trim() || "(no recent error captured)";
    const prompt =
      `@bug-analyzer Help me diagnose this error from my Coder project ` +
      `'${project.name}':\n\n\`\`\`\n${errorBlock}\n\`\`\``;
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
        {/* Left: Chat (rewired to streamWorkflow) */}
        <ChatPanel projectId={project.project_id} />

        {/* Right: Terminal | Team tabs */}
        <div className="flex flex-col rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 min-h-0">
          {/* Tab bar */}
          <div className="flex items-center gap-1 px-3 h-11 border-b border-neutral-200 dark:border-neutral-800">
            <button
              type="button"
              data-testid="tab-terminal"
              onClick={() => setRightTab("terminal")}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
                rightTab === "terminal"
                  ? "bg-neutral-100 dark:bg-neutral-800 text-neutral-900 dark:text-white"
                  : "text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200",
              )}
            >
              <Terminal className="w-3.5 h-3.5" /> Terminal
            </button>
            <button
              type="button"
              data-testid="tab-team"
              onClick={() => setRightTab("team")}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
                rightTab === "team"
                  ? "bg-neutral-100 dark:bg-neutral-800 text-neutral-900 dark:text-white"
                  : "text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200",
              )}
            >
              <Users className="w-3.5 h-3.5" /> Team
            </button>
          </div>

          {/* Right pane content */}
          <div className="flex-1 min-h-0 overflow-hidden">
            {rightTab === "terminal" ? (
              <RunPanelContent
                project={project}
                running={running}
                busy={busy}
                previewUrl={previewUrl}
                output={output}
                outputBoxRef={outputBoxRef}
                onRun={handleRun}
                onStop={handleStop}
              />
            ) : (
              <TeamPanel projectId={project.project_id} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chat panel — rewired to streamWorkflow (PR 16)
// ---------------------------------------------------------------------------

function ChatPanel({ projectId }: { projectId: string }) {
  const [messages, setMessages] = useState<LocalChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [plan, setPlan] = useState<WorkflowPlan | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const previewTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const historyRef = useRef<{ role: "user" | "assistant"; content: string }[]>([]);

  // Auto-scroll. `block: "nearest"` keeps the scroll confined to the
  // messages container — without it, on mount with an empty list the
  // browser walks up to the document and scrolls the whole shell, pushing
  // the top-bar mode toggle off-screen.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages]);

  // Debounced preview on draft change
  useEffect(() => {
    if (!draft.trim()) {
      setPlan(null);
      return;
    }
    if (previewTimerRef.current) clearTimeout(previewTimerRef.current);
    previewTimerRef.current = setTimeout(async () => {
      setPreviewLoading(true);
      try {
        const result = await previewWorkflow(projectId, draft.trim(), historyRef.current);
        setPlan(result);
      } catch {
        setPlan(null);
      } finally {
        setPreviewLoading(false);
      }
    }, 500);
    return () => {
      if (previewTimerRef.current) clearTimeout(previewTimerRef.current);
    };
  }, [draft, projectId]);

  async function handleSend() {
    const text = draft.trim();
    if (!text || busy) return;

    const userMsg: LocalChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content: text,
    };
    setMessages((prev) => [...prev, userMsg]);
    setDraft("");
    setBusy(true);
    setPlan(null);

    const history = historyRef.current;
    historyRef.current = [...history, { role: "user", content: text }];

    const ctl = new AbortController();
    abortRef.current = ctl;

    // Track per-role message IDs
    const roleMessageIds = new Map<string, string>();

    try {
      for await (const event of streamWorkflow(
        projectId,
        text,
        history,
        ctl.signal,
      )) {
        if (event.type === "workflow_start") {
          // nothing to render yet — roles will arrive via role_start
        } else if (event.type === "role_start") {
          const msgId = `role-${event.role_id}-${Date.now()}`;
          roleMessageIds.set(event.role_id, msgId);
          const roleMsg: LocalChatMessage = {
            id: msgId,
            role: "assistant",
            content: "",
            roleId: event.role_id,
            roleKind: event.role_kind,
            displayName: event.display_name,
            modelId: event.model_id,
            frozen: false,
          };
          setMessages((prev) => [...prev, roleMsg]);
        } else if (event.type === "role_token") {
          const msgId = roleMessageIds.get(event.role_id);
          if (msgId) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === msgId ? { ...m, content: m.content + event.content } : m,
              ),
            );
          }
        } else if (event.type === "role_done") {
          const msgId = roleMessageIds.get(event.role_id);
          if (msgId) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === msgId
                  ? { ...m, frozen: true, tokenCount: event.usage.total_tokens }
                  : m,
              ),
            );
          }
        } else if (event.type === "workflow_done") {
          // Collect all role outputs as the assistant's final content for history
          const assistantContent = messages
            .filter((m) => m.role === "assistant" && m.roleId && m.frozen)
            .map((m) => `[${m.displayName ?? "assistant"}]: ${m.content}`)
            .join("\n\n");
          historyRef.current = [
            ...historyRef.current,
            { role: "assistant", content: assistantContent || "(no output)" },
          ];
        } else if (event.type === "error") {
          const errMsg: LocalChatMessage = {
            id: `err-${Date.now()}`,
            role: "assistant",
            content: `[error] ${event.error}`,
            frozen: true,
          };
          setMessages((prev) => [...prev, errMsg]);
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
          multi-agent via /run
        </span>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 min-h-0">
        {messages.length === 0 ? (
          <div className="text-xs text-neutral-500 dark:text-neutral-400 text-center py-12">
            Tell Solo Coder what you want to build.
            <br />
            <span className="text-[11px]">
              Messages route through your team's roles. Configure the Team tab to customise agents.
            </span>
          </div>
        ) : (
          messages.map((m) => (
            <ChatBubble key={m.id} message={m} />
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Preview plan card */}
      {(plan || previewLoading) && draft.trim() && (
        <div className="mx-3 mb-1 rounded-xl border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 px-3 py-2">
          {previewLoading ? (
            <div className="flex items-center gap-1.5 text-[11px] text-neutral-400">
              <Loader2 className="w-3 h-3 animate-spin" /> Calculating workflow…
            </div>
          ) : plan ? (
            <div className="flex items-center gap-1.5 text-[11px] text-neutral-600 dark:text-neutral-300 flex-wrap">
              {plan.roles.map((r, i) => (
                <span key={r.role_id} className="flex items-center gap-1">
                  <span className={cn("inline-block w-2 h-2 rounded-full", ROLE_KIND_COLORS[r.role_kind])} />
                  <span className="font-medium">{r.display_name}</span>
                  {i < plan.roles.length - 1 && (
                    <ChevronRight className="w-3 h-3 text-neutral-400" />
                  )}
                </span>
              ))}
              <span className="ml-1 text-neutral-400">· {plan.workflow_mode}</span>
            </div>
          ) : null}
        </div>
      )}

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

function ChatBubble({ message }: { message: LocalChatMessage }) {
  const isUser = message.role === "user";

  if (!isUser && message.roleKind) {
    const RoleIcon = ROLE_KIND_ICONS[message.roleKind];
    const badgeColor = ROLE_KIND_COLORS[message.roleKind];

    return (
      <div className="flex gap-2 justify-start">
        <div
          className={cn(
            "flex-shrink-0 w-7 h-7 rounded-lg flex items-center justify-center",
            badgeColor,
          )}
        >
          <RoleIcon className="w-3.5 h-3.5 text-white" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 mb-1">
            <span className="text-[11px] font-semibold text-neutral-700 dark:text-neutral-300">
              {message.displayName ?? "Assistant"}
            </span>
            {message.modelId && (
              <span className="text-[10px] text-neutral-400 font-mono">
                {message.modelId.split(":").slice(-1)[0] ?? message.modelId}
              </span>
            )}
            {message.tokenCount != null && (
              <span className="text-[10px] text-neutral-400">
                {message.tokenCount.toLocaleString()} tokens
              </span>
            )}
          </div>
          <div
            className={cn(
              "max-w-full px-3 py-2 rounded-2xl text-sm whitespace-pre-wrap break-words",
              "bg-neutral-100 dark:bg-neutral-800 text-neutral-900 dark:text-white",
            )}
          >
            {message.content || (
              <span className="text-neutral-400 dark:text-neutral-500 italic">
                <Loader2 className="w-3 h-3 animate-spin inline mr-1" />
                generating…
              </span>
            )}
          </div>
        </div>
      </div>
    );
  }

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
    </div>
  );
}

// ---------------------------------------------------------------------------
// Terminal / Run content (extracted from RunPanel to fit into right pane)
// ---------------------------------------------------------------------------

function RunPanelContent({
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
    <div className="flex flex-col h-full min-h-0">
      {/* Run controls */}
      <div className="flex items-center justify-between gap-2 px-4 h-10 border-b border-neutral-200 dark:border-neutral-800">
        <div className="flex items-center gap-2">
          <Play className="w-3.5 h-3.5 text-primary-500" />
          <span className="text-xs font-semibold text-neutral-900 dark:text-white">
            Preview & Run
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {running ? (
            <Button size="sm" variant="danger" onClick={onStop} disabled={busy}>
              {busy ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Square className="w-3.5 h-3.5" />
              )}
              Stop
            </Button>
          ) : (
            <span title={runTooltip}>
              <Button size="sm" variant="primary" onClick={onRun} disabled={runDisabled}>
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

      {/* Preview iframe */}
      <div className="flex-1 min-h-0 bg-neutral-50 dark:bg-neutral-950 border-b border-neutral-200 dark:border-neutral-800 relative">
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
      <div className="flex flex-col h-40 bg-neutral-950 text-neutral-100 flex-shrink-0">
        <div className="flex items-center gap-2 px-3 h-8 border-b border-neutral-800">
          <Terminal className="w-3.5 h-3.5 text-emerald-400" />
          <span className="text-[11px] font-mono text-neutral-300">output</span>
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
      onSuccess("Indexing started — open Knowledge to follow progress.");
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
// PR 7: Distribute-artifact dialog (stubbed)
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
