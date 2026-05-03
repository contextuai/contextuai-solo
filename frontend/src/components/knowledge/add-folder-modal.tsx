import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  createFolder,
  type FolderSource,
  type Schedule,
} from "@/lib/api/personal-docs-client";
import { isTauri, pickFolder } from "@/lib/tauri-fs";

import { SyncProgressPanel } from "./sync-progress-panel";

const SCHEDULES: Schedule[] = ["manual", "1h", "6h", "24h"];

export function AddFolderModal({
  kbId,
  open,
  onClose,
  onAdded,
}: {
  kbId: string;
  open: boolean;
  onClose: () => void;
  onAdded: (source: FolderSource) => void;
}) {
  const [path, setPath] = useState("");
  const [label, setLabel] = useState("");
  const [schedule, setSchedule] = useState<Schedule>("manual");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const reset = () => {
    setPath("");
    setLabel("");
    setSchedule("manual");
    setSubmitting(false);
    setError(null);
    setActiveJobId(null);
  };

  const handleClose = () => {
    onClose();
    // Defer reset so dialog close animation doesn't show a flash of new state
    setTimeout(reset, 200);
  };

  const handlePick = async () => {
    try {
      const p = await pickFolder();
      if (p) setPath(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not open folder picker");
    }
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const { source, jobId } = await createFolder(kbId, {
        path,
        label: label || undefined,
        schedule,
      });
      setActiveJobId(jobId);
      onAdded(source);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add folder");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      title={activeJobId ? "Indexing folder" : "Add folder"}
      actions={
        activeJobId ? (
          <Button variant="ghost" onClick={handleClose}>
            Close
          </Button>
        ) : (
          <>
            <Button
              variant="ghost"
              onClick={handleClose}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={!path || submitting}
            >
              {submitting ? "Adding…" : "Add"}
            </Button>
          </>
        )
      }
    >
      {activeJobId ? (
        <SyncProgressPanel
          jobId={activeJobId}
          onDone={() => {
            // keep the panel mounted so user can read the final state
          }}
        />
      ) : (
        <div className="space-y-4">
          <div>
            <label className="block text-xs text-neutral-500 dark:text-neutral-400 mb-1">
              Folder
            </label>
            <div className="flex gap-2">
              <Input
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder="C:\\Users\\me\\Documents\\Notes"
                readOnly={isTauri()}
              />
              <Button onClick={handlePick} type="button">
                Browse…
              </Button>
            </div>
            {!isTauri() && (
              <p className="text-[11px] text-amber-600 dark:text-amber-500 mt-1">
                Native folder picker is only available in the desktop build —
                type the absolute path here.
              </p>
            )}
          </div>
          <Input
            label="Label (optional)"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Notes"
          />
          <div>
            <label className="block text-xs text-neutral-500 dark:text-neutral-400 mb-1">
              Sync schedule
            </label>
            <div className="flex gap-2 flex-wrap">
              {SCHEDULES.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setSchedule(s)}
                  className={cn(
                    "px-3 py-1 text-sm rounded border transition-colors",
                    schedule === s
                      ? "border-primary-500 text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-500/10"
                      : "border-neutral-300 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300",
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
          {error && (
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          )}
          <p className="text-[11px] text-neutral-500 dark:text-neutral-400">
            Supported file types: PDF, DOCX, TXT, MD, HTML, RTF, CSV, JSON.
            Common build/dependency directories are excluded by default. The
            full file list is processed locally on your machine.
          </p>
        </div>
      )}
    </Dialog>
  );
}
