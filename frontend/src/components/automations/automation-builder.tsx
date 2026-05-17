import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  type Automation,
  type AutomationValidation,
  type CreateAutomationPayload,
  type ExecutionMode,
  type OutputAction,
  type TriggerType,
  validatePrompt,
} from "@/lib/api/automations-client";

import { OutputActionPicker } from "./output-action-picker";

interface Props {
  initial?: Automation | null;
  onSubmit: (payload: CreateAutomationPayload) => Promise<void> | void;
  onCancel: () => void;
  submitting?: boolean;
  submitLabel?: string;
}

export function AutomationBuilder({
  initial,
  onSubmit,
  onCancel,
  submitting,
  submitLabel = "Save",
}: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [prompt, setPrompt] = useState(initial?.prompt_template ?? "");
  const [triggerType, setTriggerType] = useState<TriggerType>(
    initial?.trigger_type ?? "manual",
  );
  const [cronExpr, setCronExpr] = useState<string>(
    (initial?.trigger_config as Record<string, unknown> | null | undefined)?.[
      "cron"
    ] as string ?? "",
  );
  const [executionMode, setExecutionMode] = useState<ExecutionMode>(
    initial?.execution_mode ?? "smart",
  );
  const [outputs, setOutputs] = useState<OutputAction[]>(
    initial?.output_actions ?? [],
  );
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState<AutomationValidation | null>(
    null,
  );

  // Auto-validate the prompt on a debounce so the detected agents update live.
  useEffect(() => {
    if (!prompt.trim()) {
      setValidation(null);
      return;
    }
    const handle = setTimeout(async () => {
      setValidating(true);
      try {
        const v = await validatePrompt(prompt);
        setValidation(v);
        // Only nudge the mode if the user hasn't manually overridden a value
        // that matches what we previously detected.
        setExecutionMode((current) => current === "smart" ? v.execution_mode : current);
      } catch (e) {
        setValidation(null);
      } finally {
        setValidating(false);
      }
    }, 400);
    return () => clearTimeout(handle);
  }, [prompt]);

  const personas = useMemo(
    () => validation?.personas_detected ?? [],
    [validation],
  );

  const canSubmit =
    name.trim().length > 0 && prompt.trim().length > 0 && personas.length > 0;

  async function handleSubmit() {
    const trigger_config =
      triggerType === "scheduled" && cronExpr.trim()
        ? { cron: cronExpr.trim() }
        : undefined;
    const payload: CreateAutomationPayload = {
      name: name.trim(),
      description: description.trim(),
      prompt_template: prompt.trim(),
      trigger_type: triggerType,
      trigger_config,
      output_actions: outputs,
    };
    await onSubmit(payload);
  }

  return (
    <div className="space-y-6">
      <Input
        label="Name"
        placeholder="e.g. Weekly LinkedIn post"
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
      />

      <Input
        label="Description (optional)"
        placeholder="What does this automation do?"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />

      <div>
        <label className="text-xs font-medium text-neutral-600 dark:text-neutral-400">
          Prompt
        </label>
        <textarea
          rows={8}
          placeholder="@market-researcher pull AI startup funding for last 30 days, then @blog-writer turn it into a 600-word post, then @editor proof it."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          className={cn(
            "mt-1 w-full rounded-xl border bg-white dark:bg-neutral-900 px-3 py-2 text-sm font-mono",
            "border-neutral-200 dark:border-neutral-800",
            "focus:outline-none focus:ring-2 focus:ring-primary-500/40",
          )}
        />
        <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
          Mention agents with <code>@agent-slug</code>. Connect steps with
          “then” for sequential, “in parallel” to fan out.
        </p>
      </div>

      {/* Validation panel */}
      <div
        className={cn(
          "rounded-xl border px-4 py-3 text-sm",
          validation?.is_valid
            ? "border-emerald-200 dark:border-emerald-700/40 bg-emerald-50/50 dark:bg-emerald-500/5"
            : validation
              ? "border-amber-200 dark:border-amber-700/40 bg-amber-50/40 dark:bg-amber-500/5"
              : "border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900/40",
        )}
      >
        <div className="flex items-center gap-2 text-xs font-medium">
          {validating ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin text-neutral-500" />
              Detecting agents…
            </>
          ) : !validation ? (
            <>
              <Sparkles className="w-3.5 h-3.5 text-neutral-400" />
              Add a prompt to detect agents.
            </>
          ) : validation.is_valid ? (
            <>
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
              {personas.length} agent{personas.length === 1 ? "" : "s"} detected ·{" "}
              <span className="font-mono">{validation.execution_mode}</span>
            </>
          ) : (
            <>
              <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
              Needs attention
            </>
          )}
        </div>
        {personas.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {personas.map((p) => (
              <span
                key={p}
                className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-mono bg-primary-50 dark:bg-primary-500/10 text-primary-700 dark:text-primary-300"
              >
                @{p}
              </span>
            ))}
          </div>
        )}
        {validation && validation.errors.length > 0 && (
          <ul className="mt-2 space-y-0.5 text-xs text-amber-700 dark:text-amber-300">
            {validation.errors.map((m) => (
              <li key={m}>· {m}</li>
            ))}
          </ul>
        )}
        {validation && validation.warnings.length > 0 && (
          <ul className="mt-2 space-y-0.5 text-xs text-neutral-600 dark:text-neutral-400">
            {validation.warnings.map((m) => (
              <li key={m}>· {m}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-xs font-medium text-neutral-600 dark:text-neutral-400">
            Execution mode
          </label>
          <select
            value={executionMode}
            onChange={(e) => setExecutionMode(e.target.value as ExecutionMode)}
            className="mt-1 w-full rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm"
          >
            <option value="sequential">Sequential</option>
            <option value="parallel">Parallel (fan out)</option>
            <option value="smart">Smart (let Solo decide)</option>
          </select>
        </div>
        <div>
          <label className="text-xs font-medium text-neutral-600 dark:text-neutral-400">
            Trigger
          </label>
          <select
            value={triggerType}
            onChange={(e) => setTriggerType(e.target.value as TriggerType)}
            className="mt-1 w-full rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2 text-sm"
          >
            <option value="manual">Manual</option>
            <option value="scheduled">Scheduled (cron)</option>
            <option value="event">Webhook event</option>
          </select>
        </div>
      </div>

      {triggerType === "scheduled" && (
        <Input
          label="Cron expression"
          placeholder="0 9 * * 1   (every Monday at 9am)"
          value={cronExpr}
          onChange={(e) => setCronExpr(e.target.value)}
        />
      )}

      <div>
        <h3 className="text-sm font-semibold text-neutral-900 dark:text-white mb-2">
          Output to
        </h3>
        <OutputActionPicker value={outputs} onChange={setOutputs} />
      </div>

      <div className="flex items-center justify-end gap-2 pt-2">
        <Button variant="ghost" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button onClick={handleSubmit} disabled={!canSubmit || submitting}>
          {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
          {submitLabel}
        </Button>
      </div>
    </div>
  );
}
