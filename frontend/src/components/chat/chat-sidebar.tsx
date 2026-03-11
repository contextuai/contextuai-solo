import { useState } from "react";
import { cn } from "@/lib/utils";
import {
  Plus,
  Search,
  MessageSquare,
  Trash2,
  Archive,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeft,
} from "lucide-react";
import type { ChatSession } from "@/types/chat";

interface ChatSidebarProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  onDeleteSession: (sessionId: string) => void;
  onArchiveSession: (sessionId: string) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function getSessionTitle(session: ChatSession): string {
  return session.title || "New Chat";
}

function getSessionId(session: ChatSession): string {
  return session.id || session.sessionId || session.session_id || "";
}

export default function ChatSidebar({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  onArchiveSession,
  collapsed,
  onToggleCollapse,
}: ChatSidebarProps) {
  const [search, setSearch] = useState("");
  const [menuOpen, setMenuOpen] = useState<string | null>(null);

  const filtered = sessions.filter((s) => {
    if (!search) return true;
    const title = getSessionTitle(s).toLowerCase();
    return title.includes(search.toLowerCase());
  });

  if (collapsed) {
    return (
      <div className="flex flex-col items-center w-12 border-r border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 py-3 gap-2">
        <button
          onClick={onToggleCollapse}
          className="p-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500 dark:text-neutral-400"
          title="Expand sidebar"
        >
          <PanelLeft className="w-4 h-4" />
        </button>
        <button
          onClick={onNewChat}
          className="p-2 rounded-lg hover:bg-primary-50 dark:hover:bg-primary-500/10 text-primary-500"
          title="New chat"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col w-72 border-r border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-neutral-200 dark:border-neutral-800">
        <h2 className="text-sm font-semibold text-neutral-900 dark:text-white">
          Chats
        </h2>
        <div className="flex items-center gap-1">
          <button
            onClick={onNewChat}
            className={cn(
              "flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium",
              "bg-primary-500 hover:bg-primary-600 text-white transition-colors"
            )}
          >
            <Plus className="w-3.5 h-3.5" />
            New
          </button>
          <button
            onClick={onToggleCollapse}
            className="p-1.5 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-500 dark:text-neutral-400"
            title="Collapse sidebar"
          >
            <PanelLeftClose className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="px-3 py-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-neutral-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search chats..."
            className={cn(
              "w-full pl-8 pr-3 py-1.5 rounded-lg text-xs",
              "bg-neutral-50 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700",
              "text-neutral-900 dark:text-white placeholder:text-neutral-400",
              "focus:outline-none focus:border-primary-400 dark:focus:border-primary-500"
            )}
          />
        </div>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 py-1 space-y-0.5">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <MessageSquare className="w-8 h-8 text-neutral-300 dark:text-neutral-600 mb-2" />
            <p className="text-xs text-neutral-400 dark:text-neutral-500">
              {search ? "No matching chats" : "No conversations yet"}
            </p>
          </div>
        ) : (
          filtered.map((session) => {
            const sid = getSessionId(session);
            const isActive = sid === activeSessionId;

            return (
              <div
                key={sid}
                className={cn(
                  "group relative flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer",
                  "transition-colors text-sm",
                  isActive
                    ? "bg-primary-50 dark:bg-primary-500/10"
                    : "hover:bg-neutral-50 dark:hover:bg-neutral-800/50"
                )}
                onClick={() => onSelectSession(sid)}
              >
                <MessageSquare
                  className={cn(
                    "w-4 h-4 flex-shrink-0",
                    isActive
                      ? "text-primary-500"
                      : "text-neutral-400 dark:text-neutral-500"
                  )}
                />
                <div className="flex-1 min-w-0">
                  <p
                    className={cn(
                      "truncate text-xs font-medium",
                      isActive
                        ? "text-primary-700 dark:text-primary-300"
                        : "text-neutral-700 dark:text-neutral-300"
                    )}
                  >
                    {getSessionTitle(session)}
                  </p>
                  <p className="text-[10px] text-neutral-400 dark:text-neutral-500 mt-0.5">
                    {formatDate(session.lastMessageAt || session.updatedAt)}
                    {session.messageCount > 0 &&
                      ` \u00b7 ${session.messageCount} msgs`}
                  </p>
                </div>

                {/* Context menu trigger */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setMenuOpen(menuOpen === sid ? null : sid);
                  }}
                  className={cn(
                    "flex-shrink-0 p-1 rounded opacity-0 group-hover:opacity-100",
                    "hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-opacity"
                  )}
                >
                  <MoreHorizontal className="w-3.5 h-3.5 text-neutral-500" />
                </button>

                {/* Dropdown */}
                {menuOpen === sid && (
                  <div
                    className={cn(
                      "absolute right-2 top-full z-20 mt-1 py-1 w-36 rounded-lg shadow-lg",
                      "bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700"
                    )}
                    onMouseLeave={() => setMenuOpen(null)}
                  >
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onArchiveSession(sid);
                        setMenuOpen(null);
                      }}
                      className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-700"
                    >
                      <Archive className="w-3.5 h-3.5" />
                      Archive
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteSession(sid);
                        setMenuOpen(null);
                      }}
                      className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      Delete
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
