import { useEffect, useState } from "react";
import { Check } from "lucide-react";

import {
  listKnowledgeBases,
  type KnowledgeBase,
} from "@/lib/api/knowledge-base-client";
import { cn } from "@/lib/utils";

/**
 * Reusable multi-select for binding crews/agents to knowledge bases.
 * Renders an empty-state if no KBs exist yet.
 */
export function KbMultiSelect({
  value,
  onChange,
}: {
  value: string[];
  onChange: (ids: string[]) => void;
}) {
  const [kbs, setKbs] = useState<KnowledgeBase[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await listKnowledgeBases();
        if (!cancelled) setKbs(list);
      } catch {
        if (!cancelled) setKbs([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const toggle = (id: string) =>
    onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);

  if (kbs === null) {
    return (
      <p className="text-xs text-neutral-500 dark:text-neutral-400">Loading…</p>
    );
  }
  if (kbs.length === 0) {
    return (
      <p className="text-xs text-neutral-500 dark:text-neutral-400">
        No knowledge bases yet.
      </p>
    );
  }

  return (
    <div className="border border-neutral-200 dark:border-neutral-800 rounded">
      {kbs.map((kb) => {
        const on = value.includes(kb.id);
        return (
          <button
            key={kb.id}
            type="button"
            onClick={() => toggle(kb.id)}
            className={cn(
              "w-full flex items-center justify-between px-3 py-2 text-sm text-left",
              "hover:bg-neutral-50 dark:hover:bg-neutral-900",
              on && "bg-primary-50 dark:bg-primary-500/10",
            )}
          >
            <span className="text-neutral-800 dark:text-neutral-200">
              {kb.name}
              {kb.description && (
                <span className="text-xs text-neutral-500 dark:text-neutral-400 ml-2">
                  {kb.description}
                </span>
              )}
            </span>
            {on && (
              <Check className="h-4 w-4 text-primary-600 dark:text-primary-400" />
            )}
          </button>
        );
      })}
    </div>
  );
}
