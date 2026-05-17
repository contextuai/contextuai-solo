import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LayoutTemplate, Loader2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  type CoderTemplateInfo,
  listCoderTemplates,
} from "@/lib/api/coder-client";

export default function CoderTemplatesPage() {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<CoderTemplateInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await listCoderTemplates();
        if (!cancelled) setTemplates(list);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load templates");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function handleUse(template: CoderTemplateInfo) {
    // The Projects page reads `?new=<template_id>` to pop its New Project
    // dialog with the template pre-selected.
    navigate(`/coder/projects?new=${encodeURIComponent(template.id)}`);
  }

  return (
    <div className="flex flex-col h-full overflow-hidden bg-neutral-50 dark:bg-neutral-950">
      <div className="flex items-start justify-between gap-4 px-8 pt-8 pb-5 border-b border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <LayoutTemplate className="w-5 h-5 text-primary-500" />
            <h1 className="text-xl font-semibold text-neutral-900 dark:text-white">
              Templates
            </h1>
          </div>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Pre-built scaffolds for common project types. Pick one to start a
            new project.
          </p>
        </div>
      </div>

      {error && (
        <div className="mx-8 mt-4 rounded-xl border border-red-200 dark:border-red-700/40 bg-red-50 dark:bg-red-500/5 px-4 py-2 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-8 py-6">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-neutral-500">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading templates…
          </div>
        ) : templates.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-14 h-14 rounded-2xl bg-neutral-100 dark:bg-neutral-800 text-neutral-400 flex items-center justify-center mb-3">
              <LayoutTemplate className="w-6 h-6" />
            </div>
            <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
              No templates yet
            </p>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
              You can still create a project from any folder.
            </p>
            <Button
              size="sm"
              variant="primary"
              className="mt-4"
              onClick={() => navigate("/coder/projects?new=1")}
            >
              New Project from folder
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {templates.map((t) => (
              <TemplateCard
                key={t.id}
                template={t}
                onUse={() => handleUse(t)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function TemplateCard({
  template,
  onUse,
}: {
  template: CoderTemplateInfo;
  onUse: () => void;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 p-4 rounded-2xl",
        "bg-white dark:bg-neutral-900",
        "border border-neutral-200 dark:border-neutral-800",
        "hover:border-primary-300 dark:hover:border-primary-500/40",
        "hover:shadow-md transition-all",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Sparkles className="w-4 h-4 text-primary-500 flex-shrink-0" />
          <h3 className="text-sm font-semibold text-neutral-900 dark:text-white truncate">
            {template.name}
          </h3>
        </div>
        <Badge variant="info">{template.runtime}</Badge>
      </div>

      <p className="text-xs text-neutral-600 dark:text-neutral-400 line-clamp-3 min-h-[3em]">
        {template.description}
      </p>

      {template.init_commands.length > 0 && (
        <div className="text-[11px] font-mono bg-neutral-50 dark:bg-neutral-950 border border-neutral-200 dark:border-neutral-800 rounded-lg px-2.5 py-1.5 text-neutral-600 dark:text-neutral-400 truncate">
          $ {template.init_commands[0]}
          {template.init_commands.length > 1 && (
            <span className="text-neutral-400">
              {" "}
              + {template.init_commands.length - 1} more
            </span>
          )}
        </div>
      )}

      <Button size="sm" variant="primary" onClick={onUse} className="self-start">
        Use this template
      </Button>
    </div>
  );
}
