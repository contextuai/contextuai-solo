import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import {
  workspaceProjectsApi,
  type WorkspaceProject,
} from "@/lib/api/workspace-projects-client";
import { ProjectCard } from "@/components/workspace/project-card";
import { ProjectResults } from "@/components/workspace/project-results";
import { NewProjectDialog } from "@/components/workspace/new-project-dialog";
import {
  FlaskConical,
  Plus,
  Loader2,
  AlertCircle,
  RefreshCw,
  Filter,
} from "lucide-react";
import { Button } from "@/components/ui/button";

// ---------------------------------------------------------------------------
// Status filter options
// ---------------------------------------------------------------------------

const STATUS_FILTERS: { value: string | null; label: string }[] = [
  { value: null, label: "All" },
  { value: "draft", label: "Draft" },
  { value: "running", label: "Running" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
];

// ---------------------------------------------------------------------------
// Workspace Page
// ---------------------------------------------------------------------------

export default function WorkspacePage() {
  const { id: projectId } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [projects, setProjects] = useState<WorkspaceProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [showNewDialog, setShowNewDialog] = useState(false);

  const loadProjects = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await workspaceProjectsApi.list(statusFilter ?? undefined);
      setProjects(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const handleProjectClick = (project: WorkspaceProject) => {
    const pid = project.project_id || project.id;
    navigate(`/workspace/${pid}`);
  };

  const handleProjectCreated = (project: WorkspaceProject) => {
    setShowNewDialog(false);
    const pid = project.project_id || project.id;
    if (pid) {
      navigate(`/workspace/${pid}`);
    }
    loadProjects();
  };

  // Show results view when a project is selected
  if (projectId) {
    return (
      <ProjectResults
        projectId={projectId}
        onBack={() => navigate("/workspace")}
      />
    );
  }

  // Project list view
  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-5 border-b border-neutral-200 dark:border-neutral-800">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-3">
            <div className={cn(
              "p-2 rounded-xl",
              "bg-primary-50 dark:bg-primary-500/10"
            )}>
              <FlaskConical className="w-5 h-5 text-primary-500" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-neutral-900 dark:text-white">
                Workspace
              </h1>
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                Multi-agent collaboration and AI projects
              </p>
            </div>
          </div>
          <Button onClick={() => setShowNewDialog(true)}>
            <Plus className="w-4 h-4" />
            New Project
          </Button>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex-shrink-0 px-6 py-3 flex items-center gap-3 border-b border-neutral-100 dark:border-neutral-800/50">
        <Filter className="w-4 h-4 text-neutral-400" />
        <div className="flex gap-1.5">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value ?? "all"}
              onClick={() => setStatusFilter(f.value)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
                statusFilter === f.value
                  ? "bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300"
                  : "bg-neutral-100 text-neutral-500 hover:bg-neutral-200 dark:bg-neutral-800 dark:text-neutral-400 dark:hover:bg-neutral-700"
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <button
          onClick={loadProjects}
          className="ml-auto p-1.5 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
          title="Refresh"
        >
          <RefreshCw className={cn("w-4 h-4 text-neutral-400", loading && "animate-spin")} />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {/* Error */}
        {error && (
          <div className="mb-4 flex items-center gap-2 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            {error}
          </div>
        )}

        {/* Loading */}
        {loading && projects.length === 0 && (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
          </div>
        )}

        {/* Empty state */}
        {!loading && projects.length === 0 && !error && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center py-16"
          >
            <div className="w-16 h-16 mx-auto mb-4 bg-neutral-100 dark:bg-neutral-800 rounded-2xl flex items-center justify-center">
              <FlaskConical className="w-8 h-8 text-neutral-400" />
            </div>
            <h3 className="text-lg font-semibold text-neutral-900 dark:text-white mb-2">
              Start your first project
            </h3>
            <p className="text-neutral-500 dark:text-neutral-400 mb-6 max-w-sm mx-auto text-sm">
              Select agents and give them a task to collaborate on. They will discuss
              and compile a final output together.
            </p>
            <Button onClick={() => setShowNewDialog(true)}>
              <Plus className="w-4 h-4" />
              New Project
            </Button>
          </motion.div>
        )}

        {/* Project list */}
        {projects.length > 0 && (
          <div className="space-y-3">
            {projects.map((project, index) => (
              <motion.div
                key={project.project_id || project.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.04 }}
              >
                <ProjectCard
                  project={project}
                  onClick={() => handleProjectClick(project)}
                />
              </motion.div>
            ))}
            <p className="text-center text-xs text-neutral-400 dark:text-neutral-500 pt-2">
              {projects.length} project{projects.length === 1 ? "" : "s"}
            </p>
          </div>
        )}
      </div>

      {/* New project dialog */}
      <NewProjectDialog
        isOpen={showNewDialog}
        onClose={() => setShowNewDialog(false)}
        onCreated={handleProjectCreated}
      />
    </div>
  );
}
