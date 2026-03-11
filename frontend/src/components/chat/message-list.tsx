import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { Bot, User } from "lucide-react";
import type { ChatMessage } from "@/types/chat";

interface MessageListProps {
  messages: ChatMessage[];
  streamingContent: string;
  isStreaming: boolean;
}

/** Lightweight markdown renderer for AI chat messages. */
function renderMarkdown(text: string): string {
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

  return html;
}

function MessageBubble({
  message,
  isLast,
}: {
  message: ChatMessage;
  isLast: boolean;
}) {
  const isUser = message.message_type === "user";

  return (
    <div
      className={cn(
        "flex gap-3 px-4 py-3 max-w-3xl",
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
          "rounded-2xl px-4 py-2.5 text-sm leading-relaxed max-w-[85%]",
          isUser
            ? "bg-primary-500 text-white rounded-tr-sm"
            : "bg-neutral-100 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 rounded-tl-sm"
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div
            className="prose prose-sm dark:prose-invert max-w-none [&_pre]:my-2 [&_code]:text-xs"
            dangerouslySetInnerHTML={{
              __html: renderMarkdown(message.content),
            }}
          />
        )}
      </div>
    </div>
  );
}

function StreamingBubble({ content }: { content: string }) {
  return (
    <div className="flex gap-3 px-4 py-3 max-w-3xl mr-auto mb-2">
      <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-neutral-100 dark:bg-neutral-800">
        <Bot className="w-4 h-4 text-neutral-600 dark:text-neutral-400" />
      </div>
      <div className="rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm leading-relaxed max-w-[85%] bg-neutral-100 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100">
        {content ? (
          <div
            className="prose prose-sm dark:prose-invert max-w-none [&_pre]:my-2 [&_code]:text-xs"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
          />
        ) : (
          <TypingIndicator />
        )}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 py-1 px-1">
      <span className="w-2 h-2 rounded-full bg-neutral-400 dark:bg-neutral-500 animate-bounce [animation-delay:0ms]" />
      <span className="w-2 h-2 rounded-full bg-neutral-400 dark:bg-neutral-500 animate-bounce [animation-delay:150ms]" />
      <span className="w-2 h-2 rounded-full bg-neutral-400 dark:bg-neutral-500 animate-bounce [animation-delay:300ms]" />
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-8">
      <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-primary-50 dark:bg-primary-500/10 mb-6">
        <Bot className="w-8 h-8 text-primary-500" />
      </div>
      <h2 className="text-xl font-semibold text-neutral-900 dark:text-white mb-2">
        Start a conversation
      </h2>
      <p className="text-sm text-neutral-500 dark:text-neutral-400 max-w-sm leading-relaxed">
        Ask me anything — coding questions, analysis, creative writing, or just
        chat. Select a model and persona above to customize my behavior.
      </p>
    </div>
  );
}

export default function MessageList({
  messages,
  streamingContent,
  isStreaming,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  if (messages.length === 0 && !isStreaming) {
    return <EmptyState />;
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
        {isStreaming && <StreamingBubble content={streamingContent} />}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
