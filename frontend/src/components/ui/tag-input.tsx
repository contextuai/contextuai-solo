import { useState, type KeyboardEvent } from "react";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

interface TagInputProps {
  label?: string;
  helperText?: string;
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
  className?: string;
}

export function TagInput({ label, helperText, tags, onChange, placeholder, className }: TagInputProps) {
  const [inputValue, setInputValue] = useState("");

  const addTag = (value: string) => {
    const trimmed = value.trim();
    if (trimmed && !tags.includes(trimmed)) {
      onChange([...tags, trimmed]);
    }
    setInputValue("");
  };

  const removeTag = (index: number) => {
    onChange(tags.filter((_, i) => i !== index));
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addTag(inputValue);
    } else if (e.key === "Backspace" && !inputValue && tags.length > 0) {
      removeTag(tags.length - 1);
    }
  };

  return (
    <div className={cn("w-full", className)}>
      {label && (
        <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
          {label}
        </label>
      )}
      <div
        className={cn(
          "flex flex-wrap gap-2 px-3 py-2.5 rounded-xl min-h-[42px]",
          "bg-neutral-50 dark:bg-neutral-800",
          "border border-neutral-200 dark:border-neutral-700",
          "focus-within:ring-2 focus-within:ring-primary-500/40 focus-within:border-primary-500",
          "transition-all"
        )}
      >
        {tags.map((tag, index) => (
          <span
            key={index}
            className={cn(
              "inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium",
              "bg-primary-50 dark:bg-primary-500/10",
              "text-primary-600 dark:text-primary-400",
              "border border-primary-200 dark:border-primary-500/20"
            )}
          >
            {tag}
            <button
              type="button"
              onClick={() => removeTag(index)}
              className="p-0.5 rounded hover:bg-primary-100 dark:hover:bg-primary-500/20 transition-colors"
            >
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={tags.length === 0 ? placeholder : "Add more..."}
          className={cn(
            "flex-1 min-w-[120px] bg-transparent text-sm",
            "text-neutral-900 dark:text-white",
            "placeholder:text-neutral-400 dark:placeholder:text-neutral-500",
            "focus:outline-none"
          )}
        />
      </div>
      {helperText && (
        <p className="mt-1.5 text-xs text-neutral-500 dark:text-neutral-400">{helperText}</p>
      )}
    </div>
  );
}
