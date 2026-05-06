import { useEffect, useState } from "react";
import { ArrowLeft, FolderOpen, Loader2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { pickFolder } from "@/lib/tauri-fs";
import type { CoderTemplateInfo } from "@/lib/api/coder-client";

const EMPTY_FOLDER_TEMPLATE_ID = "__empty__";

interface NewProjectInput {
  name: string;
  folder_path: string;
  template_id: string | null;
}

interface NewProjectDialogProps {
  open: boolean;
  onClose: () => void;
  templates: CoderTemplateInfo[];
  presetTemplateId?: string | null;
  submitting: boolean;
  onSubmit: (input: NewProjectInput) => void | Promise<void>;
}

export function NewProjectDialog({
  open,
  onClose,
  templates,
  presetTemplateId,
  submitting,
  onSubmit,
}: NewProjectDialogProps) {
  const [step, setStep] = useState<1 | 2>(1);
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [folderPath, setFolderPath] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Reset on open / when preset changes.
  useEffect(() => {
    if (!open) return;
    setError(null);
    setName("");
    setFolderPath("");
    if (presetTemplateId) {
      setTemplateId(presetTemplateId);
      setStep(2);
    } else {
      setTemplateId(null);
      setStep(1);
    }
  }, [open, presetTemplateId]);

  async function handlePickFolder() {
    setError(null);
    const picked = await pickFolder();
    if (picked) {
      setFolderPath(picked);
      // Default name to last path segment if empty.
      if (!name) {
        const seg = picked.split(/[\\/]/).filter(Boolean).pop();
        if (seg) setName(seg);
      }
    }
  }

  async function handleSubmit() {
    setError(null);
    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    if (!folderPath.trim()) {
      setError("Folder path is required");
      return;
    }
    await onSubmit({
      name: name.trim(),
      folder_path: folderPath.trim(),
      template_id:
        templateId && templateId !== EMPTY_FOLDER_TEMPLATE_ID ? templateId : null,
    });
  }

  const selectedTemplate =
    templateId && templateId !== EMPTY_FOLDER_TEMPLATE_ID
      ? templates.find((t) => t.id === templateId) ?? null
      : null;

  return (
    <Dialog
      open={open}
      onClose={() => !submitting && onClose()}
      title={step === 1 ? "Pick a template" : "Project details"}
      className="max-w-2xl"
    >
      {step === 1 ? (
        <div className="space-y-3">
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Templates scaffold a runtime + starter prompt. Pick "Empty folder"
            to use any folder you already have.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-[420px] overflow-y-auto pr-1">
            <TemplateOption
              id={EMPTY_FOLDER_TEMPLATE_ID}
              name="Empty folder"
              description="Bring your own folder. Solo Coder will just chat + run it."
              runtime="auto"
              selected={templateId === EMPTY_FOLDER_TEMPLATE_ID}
              onSelect={() => {
                setTemplateId(EMPTY_FOLDER_TEMPLATE_ID);
                setStep(2);
              }}
            />
            {templates.map((t) => (
              <TemplateOption
                key={t.id}
                id={t.id}
                name={t.name}
                description={t.description}
                runtime={t.runtime}
                selected={templateId === t.id}
                onSelect={() => {
                  setTemplateId(t.id);
                  setStep(2);
                }}
              />
            ))}
            {templates.length === 0 && (
              <div className="col-span-full px-3 py-6 text-xs text-center text-neutral-500 dark:text-neutral-400">
                No templates available yet.
              </div>
            )}
          </div>
          <div className="flex items-center justify-end gap-2 pt-2">
            <Button size="sm" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {selectedTemplate ? (
            <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 px-3 py-2.5">
              <div className="flex items-center gap-2 text-xs">
                <Sparkles className="w-3.5 h-3.5 text-primary-500" />
                <span className="font-medium text-neutral-900 dark:text-white">
                  {selectedTemplate.name}
                </span>
                <Badge variant="info">{selectedTemplate.runtime}</Badge>
              </div>
              <p className="mt-1.5 text-[11px] text-neutral-500 dark:text-neutral-400">
                {selectedTemplate.description}
              </p>
            </div>
          ) : (
            <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 px-3 py-2.5 text-xs text-neutral-500 dark:text-neutral-400">
              Empty folder — no template scaffolding will run.
            </div>
          )}

          <Input
            label="Project name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. landing-page"
            disabled={submitting}
          />

          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
              Folder
            </label>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={folderPath}
                onChange={(e) => setFolderPath(e.target.value)}
                placeholder="/path/to/folder"
                disabled={submitting}
                className={cn(
                  "flex-1 px-4 py-2.5 rounded-xl text-sm font-mono",
                  "bg-neutral-50 dark:bg-neutral-800",
                  "border border-neutral-200 dark:border-neutral-700",
                  "text-neutral-900 dark:text-white",
                  "placeholder:text-neutral-400 dark:placeholder:text-neutral-500",
                  "focus:outline-none focus:ring-2 focus:ring-primary-500/40 focus:border-primary-500",
                )}
              />
              <Button
                size="sm"
                variant="secondary"
                onClick={handlePickFolder}
                disabled={submitting}
              >
                <FolderOpen className="w-3.5 h-3.5" /> Browse
              </Button>
            </div>
            <p className="mt-1.5 text-xs text-neutral-500 dark:text-neutral-400">
              The folder must exist. Solo Coder will read + write inside it.
            </p>
          </div>

          {error && (
            <div className="text-xs text-red-500 dark:text-red-400">{error}</div>
          )}

          <div className="flex items-center justify-between gap-2 pt-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                if (presetTemplateId) {
                  onClose();
                } else {
                  setStep(1);
                }
              }}
              disabled={submitting}
            >
              <ArrowLeft className="w-3.5 h-3.5" /> Back
            </Button>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="ghost"
                onClick={onClose}
                disabled={submitting}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                variant="primary"
                onClick={handleSubmit}
                disabled={submitting}
              >
                {submitting ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : null}
                Create
              </Button>
            </div>
          </div>
        </div>
      )}
    </Dialog>
  );
}

function TemplateOption({
  id,
  name,
  description,
  runtime,
  selected,
  onSelect,
}: {
  id: string;
  name: string;
  description: string;
  runtime: string;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      data-template-id={id}
      className={cn(
        "flex flex-col items-start text-left gap-2 p-3 rounded-xl",
        "border transition-all",
        selected
          ? "border-primary-500 bg-primary-50 dark:bg-primary-500/10"
          : "border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 hover:border-primary-300 dark:hover:border-primary-500/40",
      )}
    >
      <div className="flex items-center gap-2 w-full">
        <span className="text-sm font-semibold text-neutral-900 dark:text-white truncate flex-1">
          {name}
        </span>
        <Badge variant="info">{runtime}</Badge>
      </div>
      <p className="text-[11px] text-neutral-500 dark:text-neutral-400 line-clamp-2">
        {description}
      </p>
    </button>
  );
}
