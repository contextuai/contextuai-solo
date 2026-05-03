import { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  deleteFolder,
  listFolders,
  syncFolder,
  updateFolder,
  type FolderSource,
} from "@/lib/api/personal-docs-client";

import { AddFolderModal } from "./add-folder-modal";
import { FolderRow } from "./folder-row";
import { SyncProgressPanel } from "./sync-progress-panel";

export function FoldersTab({ kbId }: { kbId: string }) {
  const [items, setItems] = useState<FolderSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [activeSync, setActiveSync] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await listFolders(kbId));
    } finally {
      setLoading(false);
    }
  }, [kbId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const onSync = async (s: FolderSource) => {
    try {
      const { jobId } = await syncFolder(s.id);
      setActiveSync(jobId);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Sync failed to start");
    }
  };

  const onTogglePause = async (s: FolderSource) => {
    await updateFolder(s.id, {
      status: s.status === "paused" ? "active" : "paused",
    });
    await reload();
  };

  const onDelete = async (s: FolderSource) => {
    if (
      !window.confirm(
        `Remove "${s.label}" and its indexed content from this knowledge base?`,
      )
    )
      return;
    await deleteFolder(s.id);
    await reload();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Map folders on your PC to auto-index supported documents into this
          knowledge base.
        </p>
        <Button onClick={() => setAdding(true)}>
          <Plus className="w-3.5 h-3.5" />
          Add folder
        </Button>
      </div>

      {loading ? (
        <p className="text-sm text-neutral-500 dark:text-neutral-400 py-8 text-center">
          Loading…
        </p>
      ) : items.length === 0 ? (
        <div className="px-4 py-12 text-center text-sm text-neutral-500 dark:text-neutral-400 border border-dashed border-neutral-300 dark:border-neutral-700 rounded-lg">
          No folder mappings yet. Click "Add folder" to start.
        </div>
      ) : (
        <div className="border border-neutral-200 dark:border-neutral-800 rounded-lg overflow-hidden">
          {items.map((s) => (
            <FolderRow
              key={s.id}
              source={s}
              onSync={() => onSync(s)}
              onTogglePause={() => onTogglePause(s)}
              onDelete={() => onDelete(s)}
            />
          ))}
        </div>
      )}

      {activeSync && (
        <div className="mt-4 border border-neutral-200 dark:border-neutral-800 rounded-lg overflow-hidden">
          <SyncProgressPanel
            jobId={activeSync}
            onDone={() => {
              void reload();
            }}
          />
          <div className="px-4 pb-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setActiveSync(null);
                void reload();
              }}
            >
              Dismiss
            </Button>
          </div>
        </div>
      )}

      <AddFolderModal
        kbId={kbId}
        open={adding}
        onClose={() => {
          setAdding(false);
          void reload();
        }}
        onAdded={() => void reload()}
      />
    </div>
  );
}
