import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Sun, Moon, Pencil } from "lucide-react";
import { useTheme } from "@/components/providers/theme-provider";

interface ChatHeaderProps {
  sessionTitle: string;
  onRenameSession: (title: string) => void;
}

export default function ChatHeader({
  sessionTitle,
  onRenameSession,
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
    <div className="flex items-center justify-between h-12 px-4 border-b border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900">
      {/* Left: Title */}
      <div className="flex items-center gap-2 min-w-0 flex-shrink">
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

      {/* Right: Theme toggle */}
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
  );
}
