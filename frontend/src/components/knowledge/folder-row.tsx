import { Folder, Pause, Play, RefreshCw, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { FolderSource } from "@/lib/api/personal-docs-client";

export function FolderRow({
  source,
  onSync,
  onTogglePause,
  onDelete,
}: {
  source: FolderSource;
  onSync: () => void;
  onTogglePause: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-neutral-200 dark:border-neutral-800">
      <div className="flex items-start gap-3 min-w-0">
        <Folder className="h-4 w-4 text-neutral-500 shrink-0 mt-1" />
        <div className="min-w-0">
          <div className="text-sm font-medium text-neutral-900 dark:text-white truncate">
            {source.label}
          </div>
          <div
            className="text-xs text-neutral-500 dark:text-neutral-400 truncate"
            title={source.path}
          >
            {source.path}
          </div>
          <div className="text-[11px] text-neutral-400 mt-0.5">
            {source.file_count} file{source.file_count === 1 ? "" : "s"} ·{" "}
            schedule {source.schedule}
            {source.last_sync_at &&
              ` · synced ${new Date(source.last_sync_at).toLocaleString()}`}
            {source.status === "error" &&
              ` · ⚠ ${source.error ?? "error"}`}
            {source.status === "paused" && " · paused"}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <Button variant="ghost" size="sm" onClick={onSync} title="Sync now">
          <RefreshCw className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onTogglePause}
          title={source.status === "paused" ? "Resume" : "Pause"}
        >
          {source.status === "paused" ? (
            <Play className="h-4 w-4" />
          ) : (
            <Pause className="h-4 w-4" />
          )}
        </Button>
        <Button variant="ghost" size="sm" onClick={onDelete} title="Remove">
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
