import { useRef, useEffect, KeyboardEvent, ChangeEvent } from "react";
import { cn } from "@/lib/utils";
import { ArrowUp, Square } from "lucide-react";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
}

export default function ChatInput({
  value,
  onChange,
  onSend,
  onStop,
  isStreaming,
  disabled,
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
