import { useEffect, useRef, useState, type MouseEvent } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import {
  Bot,
  User,
  Brain,
  ChevronRight,
  Download,
  Cloud,
  ArrowRight,
  Copy,
  Check,
  Code2,
  FolderOpen,
  Plug,
  Sparkles,
  Server,
} from "lucide-react";
import type { ChatCitation, ChatMessage, DlpRedactionSummary } from "@/types/chat";
import { useEdition } from "@/config/edition";
import { CitationPanel } from "./citation-panel";
import { DlpIndicator } from "./dlp-indicator";
import vesperLogoImg from "@/assets/vesper-logo.png";

interface MessageListProps {
  messages: ChatMessage[];
  streamingContent: string;
  streamingThinking: string;
  isStreaming: boolean;
  /** No usable model is set up yet — show the finish-setup nudge instead of the generic empty state. */
  noModel?: boolean;
  /** Optional handler to populate the chat input from a starter prompt card. */
  onSelectStarterPrompt?: (prompt: string) => void;
}

/** Lightweight markdown renderer for AI chat messages. */
function renderMarkdown(text: string, citationIndices?: Set<number>): string {
  // Escape HTML
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Fenced code blocks: ```lang\n...\n```
  html = html.replace(
    /```(\w*)\n([\s\S]*?)```/g,
    (_m, lang, code) => {
      const langLabel = lang
        ? `<div class="flex items-center justify-between px-3 py-1.5 text-xs text-neutral-400 dark:text-neutral-500 bg-neutral-200 dark:bg-neutral-900 rounded-t-lg font-mono"><span>${lang}</span><button onclick="navigator.clipboard.writeText(this.closest('div').nextElementSibling.textContent)" class="hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors">Copy</button></div>`
        : "";
      return `${langLabel}<pre class="${lang ? "rounded-b-lg" : "rounded-lg"} bg-neutral-100 dark:bg-neutral-800 p-3 my-2 overflow-x-auto text-sm font-mono whitespace-pre"><code>${code.trim()}</code></pre>`;
    }
  );

  // Inline code
  html = html.replace(
    /`([^`]+)`/g,
    '<code class="px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 text-sm font-mono text-primary-600 dark:text-primary-400">$1</code>'
  );

  // Headers (### > ## > #)
  html = html.replace(
    /^### (.+)$/gm,
    '<h3 class="text-base font-semibold text-neutral-900 dark:text-neutral-100 mt-4 mb-1">$1</h3>'
  );
  html = html.replace(
    /^## (.+)$/gm,
    '<h2 class="text-lg font-semibold text-neutral-900 dark:text-neutral-100 mt-4 mb-1">$1</h2>'
  );
  html = html.replace(
    /^# (.+)$/gm,
    '<h1 class="text-xl font-bold text-neutral-900 dark:text-neutral-100 mt-4 mb-2">$1</h1>'
  );

  // Horizontal rule
  html = html.replace(/^---$/gm, '<hr class="my-3 border-neutral-200 dark:border-neutral-700" />');

  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  // Italic
  html = html.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>");

  // Strikethrough
  html = html.replace(/~~(.+?)~~/g, "<del>$1</del>");

  // Links
  html = html.replace(
    /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-primary-500 hover:underline">$1</a>'
  );

  // Blockquotes
  html = html.replace(
    /^&gt; (.+)$/gm,
    '<blockquote class="border-l-3 border-primary-400 pl-3 my-2 text-neutral-600 dark:text-neutral-400 italic">$1</blockquote>'
  );

  // Unordered lists (- or *)
  html = html.replace(
    /^(?:- |\* )(.+)$/gm,
    '<li class="ml-4 list-disc text-neutral-800 dark:text-neutral-200">$1</li>'
  );

  // Ordered lists
  html = html.replace(
    /^\d+\. (.+)$/gm,
    '<li class="ml-4 list-decimal text-neutral-800 dark:text-neutral-200">$1</li>'
  );

  // Wrap consecutive <li> elements in <ul>/<ol>
  html = html.replace(
    /((?:<li class="ml-4 list-disc[^>]*>[^<]*<\/li>\s*)+)/g,
    '<ul class="my-2 space-y-0.5">$1</ul>'
  );
  html = html.replace(
    /((?:<li class="ml-4 list-decimal[^>]*>[^<]*<\/li>\s*)+)/g,
    '<ol class="my-2 space-y-0.5">$1</ol>'
  );

  // Line breaks (but not inside pre blocks)
  html = html.replace(/\n/g, "<br />");
  // Fix br inside pre blocks
  html = html.replace(
    /(<pre[^>]*>)([\s\S]*?)(<\/pre>)/g,
    (_m, open, inner, close) => open + inner.replace(/<br \/>/g, "\n") + close
  );
  // Fix br inside list wrappers
  html = html.replace(/<\/li><br \/><li/g, "</li><li");
  html = html.replace(/<ul([^>]*)><br \/>/g, "<ul$1>");
  html = html.replace(/<br \/><\/ul>/g, "</ul>");
  html = html.replace(/<ol([^>]*)><br \/>/g, "<ol$1>");
  html = html.replace(/<br \/><\/ol>/g, "</ol>");
  // Fix br after headers/hr/blockquote
  html = html.replace(/(<\/h[123]>)<br \/>/g, "$1");
  html = html.replace(/(<hr[^>]*\/>)<br \/>/g, "$1");
  html = html.replace(/(<\/blockquote>)<br \/>/g, "$1");

  // Make inline [1], [2] references clickable citation triggers outside tags/code blocks
  if (citationIndices && citationIndices.size > 0) {
    const parts = html.split(/(<pre[\s\S]*?<\/pre>|<code[^>]*>[\s\S]*?<\/code>|<[^>]+>)/g);
    html = parts
      .map((part, idx) => {
        if (idx % 2 === 1) return part;
        return part.replace(/\[(\d+)\]/g, (full, numStr: string) => {
          const num = Number(numStr);
          if (!citationIndices.has(num)) return full;
          return `<button type="button" data-citation-idx="${num}" class="inline-flex items-center px-1 py-0.2 mx-0.5 rounded text-[11px] font-semibold bg-primary-500/15 text-primary-600 dark:text-primary-400 hover:bg-primary-500/25 transition-colors cursor-pointer align-baseline">[${num}]</button>`;
        });
      })
      .join("");
  }

  return html;
}

function ThinkingBlock({ content, streaming = false }: { content: string; streaming?: boolean }) {
  const [open, setOpen] = useState(streaming);

  // Auto-open while streaming, allow manual toggle after
  useEffect(() => {
    if (streaming) setOpen(true);
  }, [streaming]);

  return (
    <div className="mb-2 rounded-lg border border-purple-200 dark:border-purple-800/50 bg-purple-50/50 dark:bg-purple-900/20 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 w-full px-3 py-1.5 text-xs font-medium text-purple-600 dark:text-purple-400 hover:bg-purple-100/50 dark:hover:bg-purple-800/30 transition-colors"
      >
        <ChevronRight className={cn("w-3 h-3 transition-transform", open && "rotate-90")} />
        <Brain className="w-3 h-3" />
        <span>Thinking{streaming ? "..." : ""}</span>
      </button>
      {open && (
        <div className="px-3 pb-2 text-xs text-purple-700 dark:text-purple-300/80 leading-relaxed whitespace-pre-wrap border-t border-purple-200/50 dark:border-purple-800/30 pt-1.5">
          {content}
        </div>
      )}
    </div>
  );
}

function MessageBubble({
  message,
  isLast,
}: {
  message: ChatMessage;
  isLast: boolean;
}) {
  const isUser = message.message_type === "user";
  const [copied, setCopied] = useState(false);
  const [activeCitationIndex, setActiveCitationIndex] = useState<number | null>(null);

  const metadata = message.metadata;
  const citations = Array.isArray(metadata?.citations)
    ? (metadata.citations as ChatCitation[])
    : [];
  const ragMode =
    typeof metadata?.rag_mode === "string" ? metadata.rag_mode : undefined;
  const dlpRedaction = metadata?.dlp_redaction as
    | (DlpRedactionSummary & { total_redactions?: number })
    | undefined;
  const citationIndices =
    citations.length > 0 ? new Set(citations.map((c) => c.index)) : undefined;

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content || "");
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  const handleMarkdownClick = (e: MouseEvent<HTMLDivElement>) => {
    const target = (e.target as HTMLElement | null)?.closest<HTMLElement>(
      "[data-citation-idx]"
    );
    if (!target) return;
    const idx = Number(target.getAttribute("data-citation-idx"));
    if (!Number.isNaN(idx)) {
      setActiveCitationIndex((prev) => (prev === idx ? null : idx));
    }
  };

  return (
    <div
      className={cn(
        "group flex gap-3 px-4 py-3 max-w-3xl",
        isUser ? "ml-auto flex-row-reverse" : "mr-auto",
        isLast && "mb-2"
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-full",
          isUser
            ? "bg-primary-100 dark:bg-primary-500/20"
            : "bg-neutral-100 dark:bg-neutral-800"
        )}
      >
        {isUser ? (
          <User className="w-4 h-4 text-primary-600 dark:text-primary-400" />
        ) : (
          <Bot className="w-4 h-4 text-neutral-600 dark:text-neutral-400" />
        )}
      </div>

      {/* Content */}
      <div
        className={cn(
          "relative rounded-2xl px-4 py-2.5 text-sm leading-relaxed max-w-[85%]",
          isUser
            ? "bg-primary-500 text-white rounded-tr-sm"
            : "bg-neutral-100 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 rounded-tl-sm"
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <>
            {message.reasoning && (
              <ThinkingBlock content={message.reasoning} />
            )}
            <div
              onClick={handleMarkdownClick}
              className="prose prose-sm dark:prose-invert max-w-none [&_pre]:my-2 [&_code]:text-xs"
              dangerouslySetInnerHTML={{
                __html: renderMarkdown(message.content, citationIndices),
              }}
            />
            {dlpRedaction && (
              <div className="mt-2">
                <DlpIndicator summary={dlpRedaction} />
              </div>
            )}
            {citations.length > 0 && (
              <CitationPanel
                citations={citations}
                ragMode={ragMode}
                activeIndex={activeCitationIndex}
                onSelectIndex={setActiveCitationIndex}
              />
            )}
            <div className="mt-2 pt-1.5 border-t border-neutral-200/60 dark:border-neutral-700/50 flex items-center justify-end opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                type="button"
                onClick={handleCopy}
                className="inline-flex items-center gap-1 text-[11px] text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200 transition-colors"
                title="Copy response"
              >
                {copied ? (
                  <>
                    <Check className="w-3 h-3 text-emerald-500" />
                    <span className="text-emerald-600 dark:text-emerald-400">Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3 h-3" />
                    <span>Copy</span>
                  </>
                )}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function StreamingBubble({ content, thinking }: { content: string; thinking: string }) {
  return (
    <div className="flex gap-3 px-4 py-3 max-w-3xl mr-auto mb-2">
      <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-neutral-100 dark:bg-neutral-800">
        <Bot className="w-4 h-4 text-neutral-600 dark:text-neutral-400" />
      </div>
      <div className="rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm leading-relaxed max-w-[85%] bg-neutral-100 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100">
        {thinking && (
          <ThinkingBlock content={thinking} streaming />
        )}
        {content ? (
          <div
            className="prose prose-sm dark:prose-invert max-w-none [&_pre]:my-2 [&_code]:text-xs"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
          />
        ) : !thinking ? (
          <TypingIndicator />
        ) : null}
      </div>
    </div>
  );
}

function TypingIndicator() {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="flex items-center gap-2 py-1 px-1">
      <span className="w-2 h-2 rounded-full bg-neutral-400 dark:bg-neutral-500 animate-bounce [animation-delay:0ms]" />
      <span className="w-2 h-2 rounded-full bg-neutral-400 dark:bg-neutral-500 animate-bounce [animation-delay:150ms]" />
      <span className="w-2 h-2 rounded-full bg-neutral-400 dark:bg-neutral-500 animate-bounce [animation-delay:300ms]" />
      {elapsed >= 3 && (
        <span className="ml-1 text-xs text-neutral-400 dark:text-neutral-500">
          {elapsed < 8 ? "Thinking..." : `Loading model... (${elapsed}s)`}
        </span>
      )}
    </div>
  );
}

const STARTER_PROMPTS = [
  {
    icon: Code2,
    title: "Write & Benchmark Code",
    prompt:
      "Write a high-performance async worker pool in TypeScript with cancellation support and explain its memory complexity.",
    badge: "Coding",
  },
  {
    icon: FolderOpen,
    title: "Synthesize Local Documents",
    prompt:
      "Summarize the key decisions, risks, and action items from the attached Knowledge Base documents with exact citations.",
    badge: "Folder RAG",
  },
  {
    icon: Plug,
    title: "Query MCP & Data Connectors",
    prompt:
      "Using the active connector, inspect the available tables or tools and generate a structured summary report.",
    badge: "MCP / Tools",
  },
  {
    icon: Sparkles,
    title: "Architecture & Strategy Brief",
    prompt:
      "Design a local-first AI system architecture that balances latency, VRAM footprint, and zero-egress privacy guarantees.",
    badge: "Reasoning",
  },
];

function EmptyState({
  onSelectStarterPrompt,
}: {
  onSelectStarterPrompt?: (prompt: string) => void;
}) {
  const navigate = useNavigate();
  const { isLite } = useEdition();

  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-6 py-8 overflow-y-auto">
      <div className="relative flex items-center justify-center w-16 h-16 rounded-2xl overflow-hidden shadow-lg shadow-primary-500/15 ring-1 ring-primary-500/30 mb-4">
        <img
          src={vesperLogoImg}
          alt="Vesper"
          className="w-full h-full object-cover"
        />
      </div>
      <h2 className="text-xl font-bold text-neutral-900 dark:text-white mb-1.5">
        {isLite ? "Vesper Sovereign AI Workstation" : "Start a conversation"}
      </h2>
      <p className="text-xs sm:text-sm text-neutral-500 dark:text-neutral-400 max-w-md leading-relaxed mb-6">
        {isLite
          ? "Zero-telemetry local GGUF inference, private Folder RAG, and grammar-locked MCP tool execution on your metal."
          : "Ask anything — coding, private document analysis, MCP tool calls, or strategic planning."}
      </p>

      {/* Starter Prompt Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-2xl mb-6 text-left">
        {STARTER_PROMPTS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.title}
              type="button"
              onClick={() => onSelectStarterPrompt?.(item.prompt)}
              className="group flex flex-col justify-between p-3.5 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 hover:border-primary-400 dark:hover:border-primary-600 hover:shadow-sm transition-all"
            >
              <div className="flex items-center justify-between w-full mb-1.5">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-lg bg-primary-50 dark:bg-primary-500/10 text-primary-500">
                    <Icon className="w-3.5 h-3.5" />
                  </div>
                  <span className="text-xs font-semibold text-neutral-900 dark:text-white group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">
                    {item.title}
                  </span>
                </div>
                <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 text-neutral-500">
                  {item.badge}
                </span>
              </div>
              <p className="text-[11px] text-neutral-500 dark:text-neutral-400 line-clamp-2 leading-relaxed">
                {item.prompt}
              </p>
            </button>
          );
        })}
      </div>

      {/* Quick Workstation Shortcuts */}
      <div className="flex flex-wrap items-center justify-center gap-2">
        <button
          type="button"
          onClick={() => navigate("/knowledge")}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 text-neutral-600 dark:text-neutral-300 hover:border-primary-400 transition-colors"
        >
          <FolderOpen className="w-3.5 h-3.5 text-primary-500" />
          Attach Local Folder (RAG)
        </button>
        <button
          type="button"
          onClick={() => navigate("/personas")}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 text-neutral-600 dark:text-neutral-300 hover:border-primary-400 transition-colors"
        >
          <Plug className="w-3.5 h-3.5 text-purple-500" />
          Connect MCP Server
        </button>
        <button
          type="button"
          onClick={() => navigate("/server")}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 text-neutral-600 dark:text-neutral-300 hover:border-primary-400 transition-colors"
        >
          <Server className="w-3.5 h-3.5 text-emerald-500" />
          Use in Cursor / Continue (/v1)
        </button>
      </div>
    </div>
  );
}

/**
 * Shown on the empty chat when no usable model is set up yet — the landing spot
 * for a user who skipped model setup in the first-run wizard. Gives two clear
 * ways to finish: download a local model, or add a cloud provider key.
 */
function NoModelState() {
  const navigate = useNavigate();
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-8">
      <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-emerald-50 dark:bg-emerald-500/10 mb-6">
        <Download className="w-8 h-8 text-emerald-500" />
      </div>
      <h2 className="text-xl font-semibold text-neutral-900 dark:text-white mb-2">
        Set up an AI model to start chatting
      </h2>
      <p className="text-sm text-neutral-500 dark:text-neutral-400 max-w-sm leading-relaxed mb-6">
        You haven&apos;t set up a model yet. Download a free local model that
        runs on your machine, or connect a cloud provider with an API key. It
        only takes a minute.
      </p>
      <div className="flex items-center gap-2.5 flex-wrap justify-center">
        <button
          onClick={() => navigate("/models")}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-emerald-500 hover:bg-emerald-600 text-white shadow-lg shadow-emerald-500/25 transition-all"
          data-testid="chat-download-model"
        >
          <Download className="w-4 h-4" />
          Download a local model
          <ArrowRight className="w-4 h-4" />
        </button>
        <button
          onClick={() => navigate("/settings?tab=ai-providers")}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-200 hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-all"
          data-testid="chat-add-cloud-key"
        >
          <Cloud className="w-4 h-4" />
          Add a cloud key
        </button>
      </div>
    </div>
  );
}

export default function MessageList({
  messages,
  streamingContent,
  streamingThinking,
  isStreaming,
  noModel,
  onSelectStarterPrompt,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, streamingContent, streamingThinking]);

  if (messages.length === 0 && !isStreaming) {
    return noModel ? (
      <NoModelState />
    ) : (
      <EmptyState onSelectStarterPrompt={onSelectStarterPrompt} />
    );
  }

  return (
    <div className="flex-1 overflow-y-auto py-4">
      <div className="mx-auto max-w-3xl">
        {messages.map((msg, i) => (
          <MessageBubble
            key={msg.message_id}
            message={msg}
            isLast={i === messages.length - 1 && !isStreaming}
          />
        ))}
        {isStreaming && <StreamingBubble content={streamingContent} thinking={streamingThinking} />}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
