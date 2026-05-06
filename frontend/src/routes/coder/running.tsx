import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Loader2,
  Play,
  Square,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  type RunningProject,
  listRunningProjects,
  stopCoderProject,
} from "@/lib/api/coder-client";

const POLL_INTERVAL_MS = 5000;

function formatRelative(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const diff = Date.now() - date.getTime();
  if (diff < 60_000) return `${Math.floor(diff / 1000)}s ago`;
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}

export default function CoderRunningPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<RunningProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [stoppingId, setStoppingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  const reload = useCallback(async () => {
    try {
      const next = await listRunningProjects();
      setItems(next);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load running list");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
    timerRef.current = window.setInterval(reload, POLL_INTERVAL_MS);
    return () => {
      if (timerRef.current != null) window.clearInterval(timerRef.current);
    };
  }, [reload]);

  async function handleStop(projectId: string) {
    setStoppingId(projectId);
    try {
      await stopCoderProject(projectId);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Stop failed");
    } finally {
      setStoppingId(null);
    }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden bg-neutral-50 dark:bg-neutral-950">
      <div className="flex items-start justify-between gap-4 px-8 pt-8 pb-5 border-b border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Play className="w-5 h-5 text-primary-500" />
            <h1 className="text-xl font-semibold text-neutral-900 dark:text-white">
              Running
            </h1>
          </div>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Projects with an active process. Refreshes every {POLL_INTERVAL_MS / 1000}s.
          </p>
        </div>
        <Button size="sm" variant="ghost" onClick={reload}>
          Refresh
        </Button>
      </div>

      {error && (
        <div className="mx-8 mt-4 rounded-xl border border-red-200 dark:border-red-700/40 bg-red-50 dark:bg-red-500/5 px-4 py-2 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-8 py-6">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-neutral-500">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading…
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-neutral-100 dark:bg-neutral-800 text-neutral-400 mb-3">
              <Play className="w-6 h-6" />
            </div>
            <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
              Nothing running
            </p>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
              Start a project from{" "}
              <Link
                to="/coder/projects"
                className="text-primary-600 dark:text-primary-400 hover:underline"
              >
                Projects
              </Link>{" "}
              to see it here.
            </p>
          </div>
        ) : (
          <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 overflow-hidden">
            <div
              className={cn(
                "grid grid-cols-[1fr_120px_140px_auto] items-center",
                "px-4 py-2.5 text-[11px] font-medium uppercase tracking-wide",
                "text-neutral-500 dark:text-neutral-400",
                "border-b border-neutral-200 dark:border-neutral-800",
              )}
            >
              <span>Project</span>
              <span>PID</span>
              <span>Started</span>
              <span className="text-right">Actions</span>
            </div>
            <ul>
              {items.map((p) => (
                <li
                  key={p.project_id}
                  className={cn(
                    "grid grid-cols-[1fr_120px_140px_auto] items-center gap-2 px-4 py-3",
                    "border-b border-neutral-100 dark:border-neutral-800 last:border-b-0",
                  )}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <Badge variant="success" dot>Live</Badge>
                    <span className="text-sm font-medium text-neutral-900 dark:text-white truncate">
                      {p.name}
                    </span>
                  </div>
                  <span className="text-xs font-mono text-neutral-500">
                    {p.pid}
                  </span>
                  <span className="text-xs text-neutral-500">
                    {formatRelative(p.started_at)}
                  </span>
                  <div className="flex items-center justify-end gap-1.5">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        navigate(`/coder/projects/${p.project_id}`)
                      }
                    >
                      Open <ArrowRight className="w-3 h-3" />
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() => handleStop(p.project_id)}
                      disabled={stoppingId === p.project_id}
                    >
                      {stoppingId === p.project_id ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <Square className="w-3 h-3" />
                      )}
                      Stop
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
