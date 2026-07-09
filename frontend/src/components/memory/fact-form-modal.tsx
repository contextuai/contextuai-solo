import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { MemoryFact } from "@/lib/api/memory-client";

export interface FactFormValues {
  subject: string;
  predicate: string;
  value: string;
}

export function FactFormModal({
  open,
  editingFact,
  onClose,
  onSubmit,
}: {
  open: boolean;
  editingFact: MemoryFact | null;
  onClose: () => void;
  onSubmit: (values: FactFormValues) => Promise<void>;
}) {
  const [subject, setSubject] = useState("");
  const [predicate, setPredicate] = useState("");
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setSubject(editingFact?.subject ?? "");
      setPredicate(editingFact?.predicate ?? "is");
      setValue(editingFact?.value ?? "");
      setError(null);
    }
  }, [open, editingFact]);

  async function handleSubmit() {
    if (!value.trim()) {
      setError("Value is required");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSubmit({
        subject: subject.trim() || "the user",
        predicate: predicate.trim() || "is",
        value: value.trim(),
      });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  const preview = `${subject.trim() || "the user"} ${predicate.trim() || "is"} ${value.trim() || "…"}`;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={editingFact ? "Edit memory" : "Add memory"}
      actions={
        <>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={saving}>
            {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {editingFact ? "Save" : "Add"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Subject"
            placeholder="e.g. pricing, the user"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            autoFocus
          />
          <Input
            label="Predicate"
            placeholder="e.g. is, prefers"
            value={predicate}
            onChange={(e) => setPredicate(e.target.value)}
          />
        </div>
        <Input
          label="Value"
          placeholder="e.g. $49/mo, email over calls"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          error={error ?? undefined}
        />
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          Solo will remember: <span className="italic">"{preview}"</span>
        </p>
      </div>
    </Dialog>
  );
}
