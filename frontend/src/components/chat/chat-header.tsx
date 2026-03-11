import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import {
  ChevronDown,
  Sun,
  Moon,
  Cpu,
  Sparkles,
  Check,
  Pencil,
} from "lucide-react";
import { useTheme } from "@/components/providers/theme-provider";
import type { ModelConfig } from "@/lib/api/models-client";
import type { Persona } from "@/lib/api/personas-client";

interface ChatHeaderProps {
  models: ModelConfig[];
  personas: Persona[];
  selectedModelId: string | null;
  selectedPersonaId: string | null;
  onSelectModel: (modelId: string) => void;
  onSelectPersona: (personaId: string | null) => void;
  sessionTitle: string;
  onRenameSession: (title: string) => void;
}

function Dropdown<T extends { id: string; name: string }>({
  items,
  selectedId,
  onSelect,
  label,
  icon: Icon,
  allowClear,
}: {
  items: T[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  label: string;
  icon: React.ElementType;
  allowClear?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selected = items.find((i) => i.id === selectedId);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          "flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium",
          "border border-neutral-200 dark:border-neutral-700",
          "bg-white dark:bg-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-700",
          "text-neutral-700 dark:text-neutral-300 transition-colors"
        )}
      >
        <Icon className="w-3.5 h-3.5 text-neutral-500" />
        <span className="max-w-[140px] truncate">
          {selected ? selected.name : label}
        </span>
        <ChevronDown
          className={cn(
            "w-3 h-3 text-neutral-400 transition-transform",
            open && "rotate-180"
          )}
        />
      </button>

      {open && (
        <div
          className={cn(
            "absolute top-full left-0 z-30 mt-1 py-1 w-64 max-h-72 overflow-y-auto rounded-lg shadow-lg",
            "bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700"
          )}
        >
          {allowClear && (
            <button
              onClick={() => {
                onSelect(null);
                setOpen(false);
              }}
              className={cn(
                "flex items-center gap-2 w-full px-3 py-2 text-xs",
                "text-neutral-500 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-700"
              )}
            >
              None (default)
            </button>
          )}
          {items.map((item) => (
            <button
              key={item.id}
              onClick={() => {
                onSelect(item.id);
                setOpen(false);
              }}
              className={cn(
                "flex items-center justify-between gap-2 w-full px-3 py-2 text-xs",
                "hover:bg-neutral-50 dark:hover:bg-neutral-700",
                item.id === selectedId
                  ? "text-primary-600 dark:text-primary-400"
                  : "text-neutral-700 dark:text-neutral-300"
              )}
            >
              <div className="min-w-0">
                <p className="font-medium truncate">{item.name}</p>
                {"provider" in item && (
                  <p className="text-[10px] text-neutral-400 mt-0.5">
                    {(item as unknown as ModelConfig).provider}
                  </p>
                )}
                {"description" in item &&
                  (item as unknown as Persona).description && (
                    <p className="text-[10px] text-neutral-400 mt-0.5 truncate">
                      {(item as unknown as Persona).description}
                    </p>
                  )}
              </div>
              {item.id === selectedId && (
                <Check className="w-3.5 h-3.5 flex-shrink-0 text-primary-500" />
              )}
            </button>
          ))}
          {items.length === 0 && (
            <p className="px-3 py-2 text-xs text-neutral-400">
              No items available
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default function ChatHeader({
  models,
  personas,
  selectedModelId,
  selectedPersonaId,
  onSelectModel,
  onSelectPersona,
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

      {/* Center: Model + Persona selectors */}
      <div className="flex items-center gap-2">
        <Dropdown
          items={models}
          selectedId={selectedModelId}
          onSelect={(id) => id && onSelectModel(id)}
          label="Select model"
          icon={Cpu}
        />
        <Dropdown
          items={personas}
          selectedId={selectedPersonaId}
          onSelect={onSelectPersona}
          label="Persona"
          icon={Sparkles}
          allowClear
        />
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
