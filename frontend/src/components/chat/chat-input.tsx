import { useState, useRef, useEffect, KeyboardEvent, ChangeEvent } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { ArrowUp, Square, ChevronDown, Cpu, Sparkles, Check, Monitor, Cloud, Library, X, Plus } from "lucide-react";
import type { ModelConfig } from "@/lib/api/models-client";
import { getModels } from "@/lib/api/models-client";
import type { Persona } from "@/lib/api/personas-client";
import type { KnowledgeBase } from "@/lib/api/knowledge-base-client";
import { useAiMode } from "@/contexts/ai-mode-context";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  models: ModelConfig[];
  personas: Persona[];
  knowledgeBases: KnowledgeBase[];
  selectedModelId: string | null;
  selectedPersonaId: string | null;
  selectedKnowledgeBaseId: string | null;
  onSelectModel: (modelId: string) => void;
  onSelectPersona: (personaId: string | null) => void;
  onSelectKnowledgeBase: (kbId: string | null) => void;
}

function MiniDropdown<T extends { id: string; name: string }>({
  items,
  selectedId,
  onSelect,
  label,
  icon: Icon,
  allowClear,
  emptyActionLabel,
  onEmptyAction,
}: {
  items: T[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  label: string;
  icon: React.ElementType;
  allowClear?: boolean;
  emptyActionLabel?: string;
  onEmptyAction?: () => void;
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
          "flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors border",
          selected && allowClear
            ? "border-primary-300 dark:border-primary-700 bg-primary-50/70 dark:bg-primary-500/10 text-primary-700 dark:text-primary-300"
            : "border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-700 text-neutral-600 dark:text-neutral-400"
        )}
      >
        <Icon className={cn("w-3 h-3", selected && allowClear ? "text-primary-500" : "text-neutral-400")} />
        <span className="max-w-[130px] truncate">
          {selected ? selected.name : label}
        </span>
        {selected && allowClear ? (
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => {
              e.stopPropagation();
              onSelect(null);
            }}
            className="p-0.5 rounded hover:bg-primary-200/50 dark:hover:bg-primary-800/50"
            title="Clear selection"
          >
            <X className="w-2.5 h-2.5" />
          </span>
        ) : (
          <ChevronDown
            className={cn(
              "w-2.5 h-2.5 text-neutral-400 transition-transform",
              open && "rotate-180"
            )}
          />
        )}
      </button>

      {open && (
        <div
          className={cn(
            "absolute bottom-full left-0 z-30 mb-1 py-1 w-64 max-h-60 overflow-y-auto rounded-lg shadow-lg",
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
                "flex items-center justify-between gap-2 w-full px-3 py-2 text-xs text-left",
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
            <div className="px-3 py-2.5 space-y-2">
              <p className="text-xs text-neutral-400">No items configured yet</p>
              {emptyActionLabel && onEmptyAction && (
                <button
                  type="button"
                  onClick={() => {
                    setOpen(false);
                    onEmptyAction();
                  }}
                  className="inline-flex items-center gap-1 text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline"
                >
                  <Plus className="w-3 h-3" />
                  {emptyActionLabel}
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ChatInput({
  value,
  onChange,
  onSend,
  onStop,
  isStreaming,
  disabled,
  models,
  personas,
  knowledgeBases,
  selectedModelId,
  selectedPersonaId,
  selectedKnowledgeBaseId,
  onSelectModel,
  onSelectPersona,
  onSelectKnowledgeBase,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const navigate = useNavigate();
  const { aiMode } = useAiMode();
  const [showAllModels, setShowAllModels] = useState(false);
  const [allModels, setAllModels] = useState<ModelConfig[]>([]);

  // When "Show all models" is toggled, fetch unfiltered models
  useEffect(() => {
    if (showAllModels) {
      getModels().then(setAllModels).catch(() => setAllModels([]));
    }
  }, [showAllModels]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const maxHeight = 6 * 24; // ~6 lines
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
  }, [value]);

  // Focus textarea on mount
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isStreaming && value.trim()) {
        onSend();
      }
    }
  };

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    onChange(e.target.value);
  };

  const canSend = value.trim().length > 0 && !isStreaming && !disabled;

  return (
    <div className="px-4 pt-2 pb-3 bg-gradient-to-t from-neutral-50 via-neutral-50/95 to-transparent dark:from-neutral-950 dark:via-neutral-950/95">
      <div className="max-w-3xl mx-auto">
        {/* M3 Filter Chips: Model, Connector, Knowledge Base */}
        <div className="flex flex-wrap items-center gap-1.5 mb-2 px-1">
          <span
            className={cn(
              "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider",
              aiMode === "local"
                ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
                : "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400"
            )}
          >
            {aiMode === "local" ? <Monitor className="w-2.5 h-2.5" /> : <Cloud className="w-2.5 h-2.5" />}
            {aiMode}
          </span>
          <MiniDropdown
            items={showAllModels ? allModels : models}
            selectedId={selectedModelId}
            onSelect={(id) => id && onSelectModel(id)}
            label="Select model"
            icon={Cpu}
            emptyActionLabel="Download in Model Hub"
            onEmptyAction={() => navigate("/models")}
          />
          <MiniDropdown
            items={personas}
            selectedId={selectedPersonaId}
            onSelect={onSelectPersona}
            label="Connector"
            icon={Sparkles}
            allowClear
            emptyActionLabel="Add MCP / Connector"
            onEmptyAction={() => navigate("/personas")}
          />
          <MiniDropdown
            items={knowledgeBases}
            selectedId={selectedKnowledgeBaseId}
            onSelect={onSelectKnowledgeBase}
            label="Knowledge"
            icon={Library}
            allowClear
            emptyActionLabel="Add Local Docs (RAG)"
            onEmptyAction={() => navigate("/knowledge")}
          />
          <button
            type="button"
            onClick={() => setShowAllModels(!showAllModels)}
            className={cn(
              "text-[10px] font-medium px-2 py-0.5 rounded-md border transition-colors",
              showAllModels
                ? "border-primary-300 dark:border-primary-700 bg-primary-50 dark:bg-primary-500/10 text-primary-600 dark:text-primary-400"
                : "border-neutral-200 dark:border-neutral-700 text-neutral-500 dark:text-neutral-400 hover:text-neutral-700"
            )}
          >
            {showAllModels ? "Filtered" : "All models"}
          </button>
        </div>

        <div
          className={cn(
            "flex items-end gap-2.5 rounded-3xl border px-4 py-2.5 transition-all duration-150",
            "bg-white/95 dark:bg-neutral-900/95 backdrop-blur-md",
            "border-neutral-200/90 dark:border-neutral-800 shadow-sm",
            "focus-within:border-primary-500/60 dark:focus-within:border-primary-400/60",
            "focus-within:ring-2 focus-within:ring-primary-500/20 focus-within:shadow-md"
          )}
        >
          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything — Shift+Enter for new line..."
            rows={1}
            disabled={disabled}
            className={cn(
              "flex-1 resize-none bg-transparent text-sm text-neutral-900 dark:text-white",
              "placeholder:text-neutral-400 dark:placeholder:text-neutral-500",
              "focus:outline-none disabled:opacity-50",
              "max-h-36 py-1.5"
            )}
          />

          {isStreaming ? (
            <button
              onClick={onStop}
              className={cn(
                "flex-shrink-0 flex items-center justify-center w-9 h-9 rounded-full",
                "bg-red-500 hover:bg-red-600 text-white shadow-sm",
                "transition-all active:scale-95"
              )}
              title="Stop generating"
            >
              <Square className="w-3.5 h-3.5 fill-current" />
            </button>
          ) : (
            <button
              onClick={onSend}
              disabled={!canSend}
              className={cn(
                "flex-shrink-0 flex items-center justify-center w-9 h-9 rounded-full",
                "transition-all active:scale-95",
                canSend
                  ? "bg-primary-500 hover:bg-primary-600 text-white shadow-sm shadow-primary-500/30"
                  : "bg-neutral-200 dark:bg-neutral-800 text-neutral-400 dark:text-neutral-500 cursor-not-allowed"
              )}
              title="Send message"
            >
              <ArrowUp className="w-4 h-4" />
            </button>
          )}
        </div>
        <p className="text-[11px] text-neutral-400 dark:text-neutral-500 text-center mt-2">
          Enter to send, Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}
