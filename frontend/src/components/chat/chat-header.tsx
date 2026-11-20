import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Sun, Moon, Pencil, History, Brain } from "lucide-react";
import { useTheme } from "@/components/providers/theme-provider";
import { ContextMeter } from "./context-meter";
import type { ChatMessage } from "@/types/chat";
import type { ModelConfig } from "@/lib/api/models-client";

interface ChatHeaderProps {
  sessionTitle: string;
  onRenameSession: (title: string) => void;
  messages?: ChatMessage[];
  draftInput?: string;
  selectedModel?: ModelConfig | null;
  sessionsCount?: number;
  historyOpen?: boolean;
  onToggleHistory?: () => void;
  memoryOpen?: boolean;
  onToggleMemory?: () => void;
}

export default function ChatHeader({
  sessionTitle,
  onRenameSession,
  messages = [],
  draftInput = "",
  selectedModel = null,
  sessionsCount = 0,
  historyOpen = false,
  onToggleHistory,
  memoryOpen = false,
  onToggleMemory,
}: ChatHeaderProps) {
  const { resolvedTheme, setTheme } = useTheme();
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(sessionTitle);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setEditTitle(sessionTitle);
  }, [sessionTitle]);

  useEffect(() => {
    if (isEditing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [isEditing]);

  const handleSaveTitle = () => {
    const trimmed = editTitle.trim();
    if (trimmed && trimmed !== sessionTitle) {
      onRenameSession(trimmed);
    } else {
      setEditTitle(sessionTitle);
    }
    setIsEditing(false);
  };

  return (
    <div className="flex items-center justify-between h-12 px-4 border-b border-neutral-200/75 dark:border-neutral-800/90 bg-white/75 dark:bg-neutral-900/75 backdrop-blur-md">
      {/* Left: Chats History Drawer Trigger + Title */}
      <div className="flex items-center gap-2.5 min-w-0 flex-shrink">
        {onToggleHistory && (
          <button
            type="button"
            onClick={onToggleHistory}
            className={cn(
              "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-all",
              historyOpen
                ? "bg-primary-500/15 text-primary-700 dark:text-primary-300 border-primary-500/30"
                : "bg-white/80 dark:bg-neutral-800/80 text-neutral-600 dark:text-neutral-300 border-neutral-200/80 dark:border-neutral-700/80 hover:bg-neutral-100 dark:hover:bg-neutral-700"
            )}
            title="Toggle Chat History"
          >
            <History className="w-3.5 h-3.5 text-primary-500" />
            <span>Chats</span>
            {sessionsCount > 0 && (
              <span className="px-1.5 py-0.2 rounded-full text-[10px] font-semibold bg-neutral-200/80 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-200 tabular-nums">
                {sessionsCount}
              </span>
            )}
          </button>
        )}
        {isEditing ? (
          <input
            ref={inputRef}
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            onBlur={handleSaveTitle}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSaveTitle();
              if (e.key === "Escape") {
                setEditTitle(sessionTitle);
                setIsEditing(false);
              }
            }}
            className={cn(
              "px-2 py-0.5 text-sm font-medium rounded border",
              "bg-transparent border-primary-400 text-neutral-900 dark:text-white",
              "focus:outline-none focus:ring-1 focus:ring-primary-400"
            )}
          />
        ) : (
          <button
            onClick={() => setIsEditing(true)}
            className="flex items-center gap-1.5 text-sm font-medium text-neutral-900 dark:text-white hover:text-primary-500 transition-colors group"
          >
            <span className="truncate max-w-[200px]">{sessionTitle}</span>
            <Pencil className="w-3 h-3 opacity-0 group-hover:opacity-100 text-neutral-400 transition-opacity" />
          </button>
        )}
      </div>

      {/* Right: Memory Drawer + Context Meter + Theme toggle */}
      <div className="flex items-center gap-2.5">
        {onToggleMemory && (
          <button
            type="button"
            onClick={onToggleMemory}
            className={cn(
              "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-all",
              memoryOpen
                ? "bg-primary-500/15 text-primary-700 dark:text-primary-300 border-primary-500/30"
                : "bg-white/80 dark:bg-neutral-800/80 text-neutral-600 dark:text-neutral-300 border-neutral-200/80 dark:border-neutral-700/80 hover:bg-neutral-100 dark:hover:bg-neutral-700"
            )}
            title="Toggle Memory Drawer"
          >
            <Brain className="w-3.5 h-3.5 text-primary-500" />
            <span>Memory</span>
          </button>
        )}
        <ContextMeter
          messages={messages}
          draftInput={draftInput}
          selectedModel={selectedModel}
        />
        <button
          onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
          className={cn(
            "p-2 rounded-lg transition-colors",
            "hover:bg-neutral-100 dark:hover:bg-neutral-800",
            "text-neutral-500 dark:text-neutral-400"
          )}
          title={`Switch to ${resolvedTheme === "dark" ? "light" : "dark"} mode`}
        >
          {resolvedTheme === "dark" ? (
            <Sun className="w-4 h-4" />
          ) : (
            <Moon className="w-4 h-4" />
          )}
        </button>
      </div>
    </div>
  );
}
