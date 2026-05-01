import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  cancelJob,
  confirmJob,
  getJob,
  subscribeJob,
  type IndexJob,
} from "@/lib/api/personal-docs-client";

const TERMINAL: IndexJob["status"][] = ["done", "error", "cancelled"];

export function SyncProgressPanel({
  jobId,
  onDone,
}: {
  jobId: string;
  onDone: (job: IndexJob) => void;
}) {
  const [job, setJob] = useState<IndexJob | null>(null);

  useEffect(() => {
    let cleanup: (() => void) | null = null;
    let cancelled = false;
    (async () => {
      try {
        setJob(await getJob(jobId));
      } catch {
        // initial fetch failed — SSE will catch up
      }
      cleanup = await subscribeJob(jobId, (j) => {
        if (cancelled) return;
        setJob(j);
        if (TERMINAL.includes(j.status)) onDone(j);
      });
    })();
    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, [jobId, onDone]);

  if (!job) {
    return (
      <div className="p-4 text-sm text-neutral-500 dark:text-neutral-400">
        Starting…
      </div>
    );
  }

  if (job.status === "awaiting_confirmation") {
    const mb = (job.bytes_total / (1024 * 1024)).toFixed(1);
    // Rough estimate: ~30 chunks/sec on cold start, ~5 chunks/file avg
    const eta = Math.max(1, Math.ceil((job.files_total * 5) / 30 / 60));
    return (
      <div className="p-4 space-y-3">
        <p className="text-sm text-neutral-700 dark:text-neutral-200">
          Indexing this folder will process{" "}
          <strong>{job.files_total}</strong> files (~{mb} MB). Estimated
          embedding time: ~{eta} min.
        </p>
        <div className="flex gap-2">
          <Button onClick={() => confirmJob(jobId)}>Continue</Button>
          <Button variant="ghost" onClick={() => cancelJob(jobId)}>
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  const total = job.files_total || 1;
  const pct = Math.min(100, Math.round((job.files_done / total) * 100));
  const label =
    `${job.status} · ${job.files_done}/${job.files_total} files` +
    (job.files_added || job.files_updated || job.files_removed
      ? ` (added ${job.files_added}, updated ${job.files_updated}, removed ${job.files_removed})`
      : "");
  return (
    <div className="p-4 space-y-2">
      <div className="text-sm text-neutral-700 dark:text-neutral-200">
        {label}
      </div>
      <div className="w-full h-2 bg-neutral-200 dark:bg-neutral-800 rounded">
        <div
          className="h-2 bg-primary-500 dark:bg-primary-400 rounded transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      {(job.status === "running" || job.status === "walking") && (
        <Button variant="ghost" size="sm" onClick={() => cancelJob(jobId)}>
          Cancel
        </Button>
      )}
      {job.status === "error" && job.error && (
        <p className="text-sm text-red-500">Error: {job.error}</p>
      )}
    </div>
  );
}
