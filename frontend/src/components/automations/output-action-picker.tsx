import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Cable,
  FileText,
  FileType,
  Globe,
  Loader2,
  Mail,
  Save,
  Send,
  Wrench,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import {
  type ConnectionSummary,
  type OutputAction,
  type OutputActionType,
  listOutboundConnections,
} from "@/lib/api/automations-client";
import {
  type CoderProject,
  listCoderProjects,
} from "@/lib/api/coder-client";

interface ActionPreset {
  type: OutputActionType;
  label: string;
  description: string;
  icon: React.ElementType;
  defaultConfig: Record<string, unknown>;
}

const PRESETS: ActionPreset[] = [
  {
    type: "generate_pdf",
    label: "Generate PDF",
    description: "Render the run as a styled PDF report.",
    icon: FileText,
    defaultConfig: { title: "Automation Report" },
  },
  {
    type: "generate_pptx",
    label: "Generate PPTX",
    description: "Build a slide deck — one slide per agent step.",
    icon: FileType,
    defaultConfig: { title: "Automation Report" },
  },
  {
    type: "save_file",
    label: "Save to file",
    description: "Drop JSON / CSV / MD into ~/.contextuai-solo/files.",
    icon: Save,
    defaultConfig: { format: "json", filename: "automation_results" },
  },
  {
    type: "webhook",
    label: "Webhook",
    description: "POST the run payload to a URL of your choice.",
    icon: Globe,
    defaultConfig: { url: "", method: "POST" },
  },
  {
    type: "send_email",
    label: "Email (SMTP)",
    description: "Send via SMTP — set SMTP_HOST in Settings.",
    icon: Mail,
    defaultConfig: { to: "", subject: "Automation Report", include_pdf: false },
  },
  {
    type: "distribute",
    label: "Distribute to channel",
    description: "Publish through a configured Distribution.",
    icon: Send,
    defaultConfig: { connection_id: "", platform: "" },
  },
  {
    type: "run_coder_project",
    label: "Run Coder project",
    description:
      "Trigger a trusted Coder project as one of this automation's steps.",
    icon: Wrench,
    defaultConfig: { project_id: "", timeout_seconds: 60 },
  },
];

interface Props {
  value: OutputAction[];
  onChange: (actions: OutputAction[]) => void;
}

export function OutputActionPicker({ value, onChange }: Props) {
  const [connections, setConnections] = useState<ConnectionSummary[]>([]);
  const [loadingConnections, setLoadingConnections] = useState(false);
  const [coderProjects, setCoderProjects] = useState<CoderProject[]>([]);
  const [loadingCoderProjects, setLoadingCoderProjects] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadingConnections(true);
    listOutboundConnections()
      .then((list) => {
        if (!cancelled) setConnections(list);
      })
      .catch(() => {
        if (!cancelled) setConnections([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingConnections(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoadingCoderProjects(true);
    listCoderProjects()
      .then((list) => {
        if (!cancelled) setCoderProjects(list);
      })
      .catch(() => {
        if (!cancelled) setCoderProjects([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingCoderProjects(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const isSelected = (type: OutputActionType) =>
    value.some((a) => a.type === type);

  function toggle(preset: ActionPreset) {
    if (isSelected(preset.type)) {
      onChange(value.filter((a) => a.type !== preset.type));
      if (open === preset.type) setOpen(null);
    } else {
      onChange([
        ...value,
        { type: preset.type, config: { ...preset.defaultConfig } },
      ]);
      setOpen(preset.type);
    }
  }

  function updateConfig(
    type: OutputActionType,
    config: Record<string, unknown>,
  ) {
    onChange(
      value.map((a) => (a.type === type ? { ...a, config } : a)),
    );
  }

  return (
    <div className="space-y-2">
      {PRESETS.map((preset) => {
        const Icon = preset.icon;
        const selected = isSelected(preset.type);
        const action = value.find((a) => a.type === preset.type);
        const isOpen = open === preset.type;

        return (
          <div
            key={preset.type}
            className={cn(
              "rounded-xl border transition-colors",
              selected
                ? "border-primary-300 dark:border-primary-700 bg-primary-50/40 dark:bg-primary-500/5"
                : "border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900",
            )}
          >
            <label className="flex items-start gap-3 px-4 py-3 cursor-pointer">
              <input
                type="checkbox"
                className="mt-1 w-4 h-4 accent-primary-500"
                checked={selected}
                onChange={() => toggle(preset)}
              />
              <Icon
                className={cn(
                  "w-4 h-4 mt-1 flex-shrink-0",
                  selected ? "text-primary-500" : "text-neutral-400",
                )}
              />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-neutral-900 dark:text-white">
                  {preset.label}
                </div>
                <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
                  {preset.description}
                </div>
              </div>
              {selected && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    setOpen(isOpen ? null : preset.type);
                  }}
                  className="text-xs text-primary-600 hover:underline"
                >
                  {isOpen ? "Hide" : "Configure"}
                </button>
              )}
            </label>

            {selected && isOpen && action && (
              <div className="px-4 pb-4 pt-1 border-t border-neutral-200 dark:border-neutral-800 space-y-3">
                {preset.type === "generate_pdf" || preset.type === "generate_pptx" ? (
                  <Input
                    label="Title"
                    value={(action.config.title as string) || ""}
                    onChange={(e) =>
                      updateConfig(preset.type, { ...action.config, title: e.target.value })
                    }
                  />
                ) : null}

                {preset.type === "save_file" ? (
                  <>
                    <div>
                      <label className="text-xs font-medium text-neutral-600 dark:text-neutral-400">
                        Format
                      </label>
                      <select
                        value={(action.config.format as string) || "json"}
                        onChange={(e) =>
                          updateConfig(preset.type, {
                            ...action.config,
                            format: e.target.value,
                          })
                        }
                        className="mt-1 w-full rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 px-3 py-2 text-sm"
                      >
                        <option value="json">JSON</option>
                        <option value="csv">CSV</option>
                        <option value="md">Markdown</option>
                        <option value="txt">Plain text</option>
                      </select>
                    </div>
                    <Input
                      label="Filename (without extension)"
                      value={(action.config.filename as string) || ""}
                      onChange={(e) =>
                        updateConfig(preset.type, {
                          ...action.config,
                          filename: e.target.value,
                        })
                      }
                    />
                  </>
                ) : null}

                {preset.type === "webhook" ? (
                  <>
                    <Input
                      label="URL"
                      placeholder="https://hooks.example.com/notify"
                      value={(action.config.url as string) || ""}
                      onChange={(e) =>
                        updateConfig(preset.type, {
                          ...action.config,
                          url: e.target.value,
                        })
                      }
                    />
                    <div>
                      <label className="text-xs font-medium text-neutral-600 dark:text-neutral-400">
                        Method
                      </label>
                      <select
                        value={(action.config.method as string) || "POST"}
                        onChange={(e) =>
                          updateConfig(preset.type, {
                            ...action.config,
                            method: e.target.value,
                          })
                        }
                        className="mt-1 w-full rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 px-3 py-2 text-sm"
                      >
                        <option value="POST">POST</option>
                        <option value="PUT">PUT</option>
                      </select>
                    </div>
                  </>
                ) : null}

                {preset.type === "send_email" ? (
                  <>
                    <Input
                      label="To (comma-separated)"
                      placeholder="alice@example.com, bob@example.com"
                      value={
                        Array.isArray(action.config.to)
                          ? (action.config.to as string[]).join(", ")
                          : (action.config.to as string) || ""
                      }
                      onChange={(e) =>
                        updateConfig(preset.type, {
                          ...action.config,
                          to: e.target.value
                            .split(",")
                            .map((s) => s.trim())
                            .filter(Boolean),
                        })
                      }
                    />
                    <Input
                      label="Subject"
                      value={(action.config.subject as string) || ""}
                      onChange={(e) =>
                        updateConfig(preset.type, {
                          ...action.config,
                          subject: e.target.value,
                        })
                      }
                    />
                    <label className="flex items-center gap-2 text-xs text-neutral-700 dark:text-neutral-300">
                      <input
                        type="checkbox"
                        className="w-3.5 h-3.5 accent-primary-500"
                        checked={Boolean(action.config.include_pdf)}
                        onChange={(e) =>
                          updateConfig(preset.type, {
                            ...action.config,
                            include_pdf: e.target.checked,
                          })
                        }
                      />
                      Attach PDF report
                    </label>
                    <p className="text-[11px] text-neutral-500 dark:text-neutral-400">
                      Solo emails go through SMTP. Set SMTP_HOST / SMTP_PORT /
                      SMTP_USER / SMTP_PASSWORD before running.
                    </p>
                  </>
                ) : null}

                {preset.type === "distribute" ? (
                  <>
                    {loadingConnections ? (
                      <div className="flex items-center gap-2 text-xs text-neutral-500">
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        Loading connections…
                      </div>
                    ) : connections.length === 0 ? (
                      <div className="rounded-lg border border-dashed border-neutral-300 dark:border-neutral-700 p-3 text-xs text-neutral-600 dark:text-neutral-400 flex items-center justify-between">
                        <span className="flex items-center gap-2">
                          <Cable className="w-3.5 h-3.5" />
                          No outbound connections configured.
                        </span>
                        <Link
                          to="/connections"
                          className="text-primary-600 hover:underline"
                        >
                          Configure →
                        </Link>
                      </div>
                    ) : (
                      <div>
                        <label className="text-xs font-medium text-neutral-600 dark:text-neutral-400">
                          Connection
                        </label>
                        <select
                          value={(action.config.connection_id as string) || ""}
                          onChange={(e) => {
                            const c = connections.find(
                              (x) => x.id === e.target.value,
                            );
                            updateConfig(preset.type, {
                              ...action.config,
                              connection_id: e.target.value,
                              platform: c?.platform || "",
                            });
                          }}
                          className="mt-1 w-full rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 px-3 py-2 text-sm"
                        >
                          <option value="">Pick a connection…</option>
                          {connections.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.display_name || c.platform} ({c.platform})
                            </option>
                          ))}
                        </select>
                      </div>
                    )}
                  </>
                ) : null}

                {preset.type === "run_coder_project" ? (
                  <>
                    {loadingCoderProjects ? (
                      <div className="flex items-center gap-2 text-xs text-neutral-500">
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        Loading Coder projects…
                      </div>
                    ) : coderProjects.filter((p) => p.trusted).length === 0 ? (
                      <div className="rounded-lg border border-dashed border-neutral-300 dark:border-neutral-700 p-3 text-xs text-neutral-600 dark:text-neutral-400 flex items-center justify-between">
                        <span className="flex items-center gap-2">
                          <Wrench className="w-3.5 h-3.5" />
                          No trusted Coder projects yet.
                        </span>
                        <Link
                          to="/coder/projects"
                          className="text-primary-600 hover:underline"
                        >
                          Create →
                        </Link>
                      </div>
                    ) : (
                      <div>
                        <label className="text-xs font-medium text-neutral-600 dark:text-neutral-400">
                          Coder project
                        </label>
                        <select
                          value={(action.config.project_id as string) || ""}
                          onChange={(e) =>
                            updateConfig(preset.type, {
                              ...action.config,
                              project_id: e.target.value,
                            })
                          }
                          className="mt-1 w-full rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 px-3 py-2 text-sm"
                        >
                          <option value="">Pick a project…</option>
                          {coderProjects
                            .filter((p) => p.trusted)
                            .map((p) => (
                              <option key={p.project_id} value={p.project_id}>
                                {p.name} ({p.runtime})
                              </option>
                            ))}
                        </select>
                      </div>
                    )}
                    <Input
                      label="Timeout (seconds)"
                      type="number"
                      min={1}
                      value={
                        action.config.timeout_seconds != null
                          ? String(action.config.timeout_seconds)
                          : "60"
                      }
                      onChange={(e) => {
                        const raw = e.target.value;
                        const parsed = Number.parseInt(raw, 10);
                        updateConfig(preset.type, {
                          ...action.config,
                          timeout_seconds: Number.isFinite(parsed) && parsed > 0
                            ? parsed
                            : 60,
                        });
                      }}
                    />
                  </>
                ) : null}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
