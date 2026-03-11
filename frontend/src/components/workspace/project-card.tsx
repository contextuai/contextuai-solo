import { cn } from "@/lib/utils";
import type { WorkspaceProject } from "@/lib/api/workspace-projects-client";
import {
  CheckCircle,
  XCircle,
  Loader2,
  Clock,
  FileText,
  Pause,
  Users,
  ChevronRight,
  AlertCircle,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  draft: { label: "Draft", color: "text-neutral-600 dark:text-neutral-400", bg: "bg-neutral-100 dark:bg-neutral-800" },
  queued: { label: "Queued", color: "text-blue-600 dark:text-blue-400", bg: "bg-blue-50 dark:bg-blue-900/20" },
  running: { label: "Running", color: "text-primary-600 dark:text-primary-400", bg: "bg-primary-50 dark:bg-primary-900/20" },
  paused: { label: "Paused", color: "text-amber-600 dark:text-amber-400", bg: "bg-amber-50 dark:bg-amber-900/20" },
  completed: { label: "Completed", color: "text-green-600 dark:text-green-400", bg: "bg-green-50 dark:bg-green-900/20" },
  failed: { label: "Failed", color: "text-red-600 dark:text-red-400", bg: "bg-red-50 dark:bg-red-900/20" },
  cancelled: { label: "Cancelled", color: "text-neutral-500 dark:text-neutral-400", bg: "bg-neutral-100 dark:bg-neutral-800" },
};

function StatusBadge({ status }: { status: string }) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.draft;

  const Icon = (() => {
    switch (status) {
      case "completed": return CheckCircle;
      case "failed": case "cancelled": return XCircle;
      case "running": return Loader2;
      case "paused": return Pause;
      case "queued": return Clock;
      default: return FileText;
    }
  })();

  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium", config.color, config.bg)}>
      <Icon className={cn("w-3.5 h-3.5", status === "running" && "animate-spin")} />
      {config.label}
    </span>
  );
}

function TypeBadge({ type }: { type: string }) {
  const isWorkshop = type === "workshop";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium",
        isWorkshop
          ? "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300"
          : "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
      )}
    >
      {type || "Project"}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface ProjectCardProps {
  project: WorkspaceProject;
  onClick: () => void;
}

export function ProjectCard({ project, onClick }: ProjectCardProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left bg-white dark:bg-neutral-800 rounded-xl",
        "border border-neutral-200 dark:border-neutral-700",
        "p-5 hover:shadow-md transition-all cursor-pointer group"
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          {/* Title row */}
          <div className="flex items-center gap-3 mb-2 flex-wrap">
            <h3 className="text-base font-semibold text-neutral-900 dark:text-white truncate">
              {project.title}
            </h3>
            <StatusBadge status={project.status} />
            <TypeBadge type={project.project_type} />
          </div>

          {/* Description */}
          {project.description && (
            <p className="text-sm text-neutral-600 dark:text-neutral-400 mb-3 line-clamp-2">
              {project.description}
            </p>
          )}

          {/* Meta row */}
          <div className="flex items-center gap-4 text-sm text-neutral-500 dark:text-neutral-400">
            <span className="flex items-center gap-1">
              <Users className="w-4 h-4" />
              {project.selected_agents?.length ?? 0} agents
            </span>
            <span className="flex items-center gap-1">
              <Clock className="w-4 h-4" />
              {formatDate(project.updated_at)}
            </span>
            {project.estimated_cost_usd != null && project.estimated_cost_usd > 0 && (
              <span className="text-primary-500 font-medium">
                ~${project.estimated_cost_usd.toFixed(3)}
              </span>
            )}
          </div>

          {/* Progress bar for running */}
          {project.status === "running" && (
            <div className="mt-3">
              <div className="h-1.5 bg-neutral-200 dark:bg-neutral-700 rounded-full overflow-hidden">
                <div className="h-full bg-primary-500 rounded-full animate-pulse w-2/5" />
              </div>
            </div>
          )}

          {/* Paused indicator */}
          {project.status === "paused" && (
            <div className="mt-3 flex items-center gap-2 text-sm text-amber-600 dark:text-amber-400">
              <AlertCircle className="w-4 h-4" />
              <span>Awaiting approval</span>
            </div>
          )}
        </div>

        <ChevronRight className="w-5 h-5 text-neutral-400 group-hover:text-neutral-600 dark:group-hover:text-neutral-200 transition-colors flex-shrink-0 ml-4 mt-1" />
      </div>
    </button>
  );
}
