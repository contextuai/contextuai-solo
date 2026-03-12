import { useState, useRef, useEffect, KeyboardEvent, ChangeEvent } from "react";
import { cn } from "@/lib/utils";
import { ArrowUp, Square, ChevronDown, Cpu, Sparkles, Check } from "lucide-react";
import type { ModelConfig } from "@/lib/api/models-client";
import type { Persona } from "@/lib/api/personas-client";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  models: ModelConfig[];
  personas: Persona[];
  selectedModelId: string | null;
  selectedPersonaId: string | null;
  onSelectModel: (modelId: string) => void;
  onSelectPersona: (personaId: string | null) => void;
}

function MiniDropdown<T extends { id: string; name: string }>({
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
          "flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium",
          "border border-neutral-200 dark:border-neutral-700",
          "bg-white dark:bg-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-700",
          "text-neutral-600 dark:text-neutral-400 transition-colors"
        )}
      >
        <Icon className="w-3 h-3 text-neutral-400" />
        <span className="max-w-[120px] truncate">
          {selected ? selected.name : label}
        </span>
        <ChevronDown
          className={cn(
            "w-2.5 h-2.5 text-neutral-400 transition-transform",
            open && "rotate-180"
          )}
        />
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

export default function ChatInput({
  value,
  onChange,
  onSend,
  onStop,
  isStreaming,
  disabled,
  models,
  personas,
  selectedModelId,
  selectedPersonaId,
  onSelectModel,
  onSelectPersona,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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
    <div className="border-t border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 px-4 py-3">
      <div className="max-w-3xl mx-auto">
        {/* Model & Persona selectors */}
        <div className="flex items-center gap-2 mb-2">
          <MiniDropdown
            items={models}
            selectedId={selectedModelId}
            onSelect={(id) => id && onSelectModel(id)}
            label="Select model"
            icon={Cpu}
          />
          <MiniDropdown
            items={personas}
            selectedId={selectedPersonaId}
            onSelect={onSelectPersona}
            label="Persona"
            icon={Sparkles}
            allowClear
          />
        </div>

        <div
          className={cn(
            "flex items-end gap-2 rounded-2xl border px-4 py-2 transition-colors",
            "bg-neutral-50 dark:bg-neutral-800/50",
            "border-neutral-200 dark:border-neutral-700",
            "focus-within:border-primary-400 dark:focus-within:border-primary-500",
            "focus-within:ring-1 focus-within:ring-primary-400/30"
          )}
        >
          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask me anything..."
            rows={1}
            disabled={disabled}
            className={cn(
              "flex-1 resize-none bg-transparent text-sm text-neutral-900 dark:text-white",
              "placeholder:text-neutral-400 dark:placeholder:text-neutral-500",
              "focus:outline-none disabled:opacity-50",
              "max-h-36 py-1"
            )}
          />

          {isStreaming ? (
            <button
              onClick={onStop}
              className={cn(
                "flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-lg",
                "bg-red-500 hover:bg-red-600 text-white",
                "transition-colors"
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
                "flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-lg",
                "transition-colors",
                canSend
                  ? "bg-primary-500 hover:bg-primary-600 text-white"
                  : "bg-neutral-200 dark:bg-neutral-700 text-neutral-400 dark:text-neutral-500 cursor-not-allowed"
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
