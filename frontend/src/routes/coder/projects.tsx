import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  FolderKanban,
  FolderOpen,
  Loader2,
  Plus,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  type CoderProject,
  type CoderTemplateInfo,
  listCoderProjects,
  listCoderTemplates,
} from "@/lib/api/coder-client";
import { NewProjectDialog } from "@/components/coder/new-project-dialog";

function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "never";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const diff = Date.now() - date.getTime();
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}

export default function CoderProjectsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [projects, setProjects] = useState<CoderProject[]>([]);
  const [templates, setTemplates] = useState<CoderTemplateInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [presetTemplateId, setPresetTemplateId] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [projectList, templateList] = await Promise.all([
        listCoderProjects(),
        listCoderTemplates(),
      ]);
      setProjects(projectList);
      setTemplates(templateList);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  // Allow other pages (Templates, Running) to deep-link with `?new=1` or
  // `?new=<template_id>` to pop the dialog.
  useEffect(() => {
    const newParam = searchParams.get("new");
    if (newParam) {
      setPresetTemplateId(newParam === "1" ? null : newParam);
      setCreateOpen(true);
      const next = new URLSearchParams(searchParams);
      next.delete("new");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  function handleCreated() {
    setCreateOpen(false);
    setPresetTemplateId(null);
    // Reload the project list in the background
    reload();
  }

  return (
    <div className="flex flex-col h-full overflow-hidden bg-neutral-50 dark:bg-neutral-950">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 px-8 pt-8 pb-5 border-b border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <FolderKanban className="w-5 h-5 text-primary-500" />
            <h1 className="text-xl font-semibold text-neutral-900 dark:text-white">
              Projects
            </h1>
          </div>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Local code projects you can chat with, run, and preview side-by-side.
          </p>
        </div>
        <Button
          size="sm"
          variant="primary"
          onClick={() => {
            setPresetTemplateId(null);
            setCreateOpen(true);
          }}
        >
          <Plus className="w-3.5 h-3.5" /> New Project
        </Button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-8 py-6">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-neutral-500">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading projects…
          </div>
        ) : projects.length === 0 ? (
          <EmptyState onCreate={() => setCreateOpen(true)} />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((p) => (
              <ProjectCard
                key={p.project_id}
                project={p}
                onClick={() => navigate(`/coder/projects/${p.project_id}`)}
              />
            ))}
          </div>
        )}
      </div>

      <NewProjectDialog
        open={createOpen}
        onClose={() => {
          setCreateOpen(false);
          setPresetTemplateId(null);
        }}
        templates={templates}
        presetTemplateId={presetTemplateId}
        onCreated={handleCreated}
      />
    </div>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-primary-50 dark:bg-primary-500/10 text-primary-500 mb-4">
        <Sparkles className="w-8 h-8" />
      </div>
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
        No projects yet
      </h2>
      <p className="mt-2 max-w-sm text-sm text-neutral-500 dark:text-neutral-400">
        Create one from a template — or point us at any folder on disk — to
        start coding with Solo Coder.
      </p>
      <Button size="md" variant="primary" className="mt-6" onClick={onCreate}>
        <Plus className="w-4 h-4" /> New Project
      </Button>
    </div>
  );
}

function ProjectCard({
  project,
  onClick,
}: {
  project: CoderProject;
  onClick: () => void;
}) {
  const running = project.status === "running" || project.process_pid != null;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group flex flex-col items-stretch text-left gap-3 p-4 rounded-2xl",
        "bg-white dark:bg-neutral-900",
        "border border-neutral-200 dark:border-neutral-800",
        "hover:border-primary-300 dark:hover:border-primary-500/40",
        "hover:shadow-md transition-all",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <FolderOpen className="w-4 h-4 text-primary-500 flex-shrink-0" />
          <h3 className="text-sm font-semibold text-neutral-900 dark:text-white truncate">
            {project.name}
          </h3>
        </div>
        {running && <Badge variant="success" dot>Running</Badge>}
      </div>

      <div
        className="text-[11px] font-mono text-neutral-500 dark:text-neutral-400 truncate"
        title={project.folder_path}
      >
        {project.folder_path}
      </div>

      <div className="flex items-center flex-wrap gap-1.5">
        <Badge variant="info">{project.runtime}</Badge>
        {project.trusted ? (
          <Badge variant="success">
            <ShieldCheck className="w-3 h-3" /> Trusted
          </Badge>
        ) : (
          <Badge variant="warning">
            <ShieldAlert className="w-3 h-3" /> Untrusted
          </Badge>
        )}
      </div>

      <div className="text-[11px] text-neutral-500 dark:text-neutral-400">
        Last run · {formatRelative(project.last_run_at)}
      </div>
    </button>
  );
}
