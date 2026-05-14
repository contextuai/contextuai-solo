import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  FolderOpen,
  Loader2,
  Plus,
  Sparkles,
  X,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { pickFolder } from "@/lib/tauri-fs";
import { createCoderProject } from "@/lib/api/coder-client";
import type { CoderTemplateInfo } from "@/lib/api/coder-client";
import {
  applyPreset,
  createRole,
  listPresets,
  setWorkflowMode,
  updateRole,
} from "@/lib/api/coder-workflow-client";
import type {
  CoderAgentRoleCreate,
  RoleKind,
  RolePresetSummary,
  WorkflowMode,
} from "@/lib/api/coder-workflow-client";
import { ModelPicker } from "@/components/coder/model-picker";
import { fetchOpenAICompat } from "@/lib/transport";
import { listCloudProviders } from "@/lib/api/cloud-providers-client";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const EMPTY_FOLDER_TEMPLATE_ID = "__empty__";

const ROLE_KIND_LABELS: Record<RoleKind, string> = {
  coder: "Coder",
  reviewer: "Code Reviewer",
  security: "Security Auditor",
  ui_ux: "UI/UX Designer",
  docs: "Docs Writer",
  tester: "Tester",
  planner: "Planner",
  custom: "Custom",
};

const WORKFLOW_MODES: { id: WorkflowMode; label: string }[] = [
  { id: "solo", label: "Solo" },
  { id: "sequential", label: "Sequential" },
  { id: "parallel", label: "Parallel" },
  { id: "custom", label: "Custom" },
];

// ---------------------------------------------------------------------------
// Local role type (before project_id / role_id are assigned)
// ---------------------------------------------------------------------------

interface LocalRole {
  /** Temp client-side id for keying React list */
  _localId: string;
  role_kind: RoleKind;
  display_name: string;
  system_prompt: string;
  model_id: string;
  temperature: number;
  max_tokens: number;
  enabled: boolean;
  order: number;
  /** Once the role is persisted, backend assigns this */
  role_id?: string;
}

function makeLocalId(): string {
  return `lr-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface NewProjectDialogProps {
  open: boolean;
  onClose: () => void;
  templates: CoderTemplateInfo[];
  presetTemplateId?: string | null;
  /** Called after successful create + role wiring. Parent should refresh list. */
  onCreated?: () => void;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function NewProjectDialog({
  open,
  onClose,
  templates,
  presetTemplateId,
  onCreated,
}: NewProjectDialogProps) {
  const navigate = useNavigate();

  // Step 1–3
  const [step, setStep] = useState<1 | 2 | 3>(1);

  // Step 1 — template
  const [templateId, setTemplateId] = useState<string | null>(null);

  // Step 2 — name + folder
  const [name, setName] = useState("");
  const [folderPath, setFolderPath] = useState("");

  // Step 3 — team & models
  const [workflowMode, setWorkflowModeState] = useState<WorkflowMode>("solo");
  const [presets, setPresets] = useState<RolePresetSummary[]>([]);
  const [selectedPresetId, setSelectedPresetId] = useState<string | null>(null);
  const [roles, setRoles] = useState<LocalRole[]>([]);
  const [sameModelForAll, setSameModelForAll] = useState(false);
  const [sharedModelId, setSharedModelId] = useState("");
  const [hasModels, setHasModels] = useState<boolean | null>(null); // null = loading
  const [showAddRole, setShowAddRole] = useState(false);

  // Submission state
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Reset on open / when preset changes
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!open) return;
    setError(null);
    setName("");
    setFolderPath("");
    setWorkflowModeState("solo");
    setSelectedPresetId(null);
    setRoles([]);
    setSameModelForAll(false);
    setSharedModelId("");
    setShowAddRole(false);
    if (presetTemplateId) {
      setTemplateId(presetTemplateId);
      setStep(2);
    } else {
      setTemplateId(null);
      setStep(1);
    }
  }, [open, presetTemplateId]);

  // Load presets + check model availability when step 3 mounts
  useEffect(() => {
    if (step !== 3) return;
    let cancelled = false;

    listPresets().then((p) => {
      if (!cancelled) setPresets(p);
    }).catch(() => {/* soft-fail */});

    Promise.all([
      fetchOpenAICompat<{ data: unknown[] }>("/v1/models").then((r) => (r.data ?? []).length > 0).catch(() => false),
      listCloudProviders().then((p) => p.length > 0).catch(() => false),
    ]).then(([hasLocal, hasCloud]) => {
      if (!cancelled) setHasModels(hasLocal || hasCloud);
    });

    return () => { cancelled = true; };
  }, [step]);

  // ---------------------------------------------------------------------------
  // Handlers — step 1 & 2
  // ---------------------------------------------------------------------------

  async function handlePickFolder() {
    setError(null);
    const picked = await pickFolder();
    if (picked) {
      setFolderPath(picked);
      if (!name) {
        const seg = picked.split(/[\\/]/).filter(Boolean).pop();
        if (seg) setName(seg);
      }
    }
  }

  function handleStep2Next() {
    setError(null);
    if (!name.trim()) { setError("Name is required"); return; }
    if (!folderPath.trim()) { setError("Folder path is required"); return; }
    setStep(3);
  }

  // ---------------------------------------------------------------------------
  // Handlers — step 3: preset apply
  // ---------------------------------------------------------------------------

  async function handleApplyPreset(presetId: string) {
    setSelectedPresetId(presetId);
    // Fetch preset detail to populate local roles
    try {
      const { getPreset } = await import("@/lib/api/coder-workflow-client");
      const detail = await getPreset(presetId);
      const newRoles: LocalRole[] = detail.roles.map((r, i) => ({
        _localId: makeLocalId(),
        role_kind: r.role_kind,
        display_name: r.display_name,
        system_prompt: r.system_prompt,
        model_id: r.model_id ?? "",
        temperature: r.temperature,
        max_tokens: r.max_tokens,
        enabled: r.enabled,
        order: r.order ?? i,
      }));
      setRoles(newRoles);
      setWorkflowModeState(detail.workflow_mode);
      setSameModelForAll(false);
      setSharedModelId("");
    } catch {
      setError("Failed to load preset details. Please try again.");
    }
  }

  // ---------------------------------------------------------------------------
  // Handlers — step 3: role mutations
  // ---------------------------------------------------------------------------

  function updateLocalRole(localId: string, patch: Partial<LocalRole>) {
    setRoles((prev) => prev.map((r) => r._localId === localId ? { ...r, ...patch } : r));
  }

  function removeLocalRole(localId: string) {
    setRoles((prev) => prev.filter((r) => r._localId !== localId));
  }

  function handleSharedModelChange(modelId: string) {
    setSharedModelId(modelId);
    setRoles((prev) => prev.map((r) => ({ ...r, model_id: modelId })));
  }

  function handleSameModelToggle(checked: boolean) {
    setSameModelForAll(checked);
    if (checked && sharedModelId) {
      setRoles((prev) => prev.map((r) => ({ ...r, model_id: sharedModelId })));
    }
  }

  function handleAddRole(newRole: LocalRole) {
    setRoles((prev) => [...prev, newRole]);
    setShowAddRole(false);
  }

  // ---------------------------------------------------------------------------
  // Gating
  // ---------------------------------------------------------------------------

  const enabledRoles = roles.filter((r) => r.enabled);
  const unconfiguiredRoles = enabledRoles.filter(
    (r) => !r.model_id || r.model_id === "" || r.model_id === "__DEFAULT__",
  );
  const canCreate =
    hasModels === true &&
    (enabledRoles.length === 0 || unconfiguiredRoles.length === 0);

  // ---------------------------------------------------------------------------
  // Submit — two-phase create
  // ---------------------------------------------------------------------------

  async function handleSubmit() {
    setError(null);
    if (!canCreate) return;

    setSubmitting(true);
    let projectId: string | null = null;
    try {
      // Phase 1: create project
      const created = await createCoderProject({
        name: name.trim(),
        folder_path: folderPath.trim(),
        template_id:
          templateId && templateId !== EMPTY_FOLDER_TEMPLATE_ID ? templateId : null,
      });
      projectId = created.project_id;

      // Phase 2: wire workflow + roles
      await setWorkflowMode(projectId, workflowMode);

      if (selectedPresetId) {
        // Apply preset (creates role rows with empty model_id on backend)
        const backendRoles = await applyPreset(projectId, selectedPresetId);
        // Now PUT each role with the user-picked model_id
        await Promise.all(
          backendRoles.map((br) => {
            const local = roles.find(
              (r) =>
                r.role_kind === br.role_kind &&
                r.display_name === br.display_name,
            );
            const modelId = local?.model_id ?? "";
            return updateRole(projectId!, br.role_id, {
              model_id: modelId,
              enabled: local?.enabled ?? br.enabled,
              system_prompt: local?.system_prompt ?? br.system_prompt,
              temperature: local?.temperature ?? br.temperature,
              max_tokens: local?.max_tokens ?? br.max_tokens,
              display_name: local?.display_name ?? br.display_name,
            });
          }),
        );
      } else {
        // User added roles inline — POST each one
        for (const role of roles) {
          const body: CoderAgentRoleCreate = {
            role_kind: role.role_kind,
            display_name: role.display_name,
            system_prompt: role.system_prompt,
            model_id: role.model_id,
            temperature: role.temperature,
            max_tokens: role.max_tokens,
            enabled: role.enabled,
            order: role.order,
          };
          await createRole(projectId, body);
        }
      }

      onCreated?.();
      navigate(`/coder/projects/${projectId}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Failed to create project: ${msg}. You can retry — the project form is still open.`);
    } finally {
      setSubmitting(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Derived
  // ---------------------------------------------------------------------------

  const selectedTemplate =
    templateId && templateId !== EMPTY_FOLDER_TEMPLATE_ID
      ? templates.find((t) => t.id === templateId) ?? null
      : null;

  const dialogTitle =
    step === 1
      ? "Pick a template"
      : step === 2
        ? "Project details"
        : "Team & models";

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <Dialog
      open={open}
      onClose={() => { if (!submitting) onClose(); }}
      title={dialogTitle}
      className="max-w-2xl"
    >
      {step === 1 && (
        <StepTemplate
          templates={templates}
          templateId={templateId}
          onSelect={(id) => { setTemplateId(id); setStep(2); }}
          onClose={onClose}
        />
      )}

      {step === 2 && (
        <StepDetails
          selectedTemplate={selectedTemplate}
          name={name}
          folderPath={folderPath}
          onNameChange={setName}
          onFolderChange={setFolderPath}
          onPickFolder={handlePickFolder}
          error={error}
          submitting={submitting}
          canGoBack={!presetTemplateId}
          onBack={() => setStep(1)}
          onClose={onClose}
          onNext={handleStep2Next}
        />
      )}

      {step === 3 && (
        <StepTeam
          workflowMode={workflowMode}
          onWorkflowModeChange={setWorkflowModeState}
          presets={presets}
          selectedPresetId={selectedPresetId}
          onApplyPreset={handleApplyPreset}
          roles={roles}
          onRoleUpdate={updateLocalRole}
          onRoleRemove={removeLocalRole}
          sameModelForAll={sameModelForAll}
          onSameModelToggle={handleSameModelToggle}
          sharedModelId={sharedModelId}
          onSharedModelChange={handleSharedModelChange}
          hasModels={hasModels}
          showAddRole={showAddRole}
          onShowAddRole={setShowAddRole}
          onAddRole={handleAddRole}
          unconfiguiredRoles={unconfiguiredRoles}
          canCreate={canCreate}
          submitting={submitting}
          error={error}
          onBack={() => setStep(2)}
          onClose={onClose}
          onSubmit={handleSubmit}
        />
      )}
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Step 1 — Template picker
// ---------------------------------------------------------------------------

function StepTemplate({
  templates,
  templateId,
  onSelect,
  onClose,
}: {
  templates: CoderTemplateInfo[];
  templateId: string | null;
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="space-y-3">
      <p className="text-xs text-neutral-500 dark:text-neutral-400">
        Templates scaffold a runtime + starter prompt. Pick "Empty folder" to use
        any folder you already have.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-[420px] overflow-y-auto pr-1">
        <TemplateOption
          id={EMPTY_FOLDER_TEMPLATE_ID}
          name="Empty folder"
          description="Bring your own folder. Solo Coder will just chat + run it."
          runtime="auto"
          selected={templateId === EMPTY_FOLDER_TEMPLATE_ID}
          onSelect={() => onSelect(EMPTY_FOLDER_TEMPLATE_ID)}
        />
        {templates.map((t) => (
          <TemplateOption
            key={t.id}
            id={t.id}
            name={t.name}
            description={t.description}
            runtime={t.runtime}
            selected={templateId === t.id}
            onSelect={() => onSelect(t.id)}
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
  );
}

// ---------------------------------------------------------------------------
// Step 2 — Project details
// ---------------------------------------------------------------------------

function StepDetails({
  selectedTemplate,
  name,
  folderPath,
  onNameChange,
  onFolderChange,
  onPickFolder,
  error,
  submitting,
  canGoBack,
  onBack,
  onClose,
  onNext,
}: {
  selectedTemplate: CoderTemplateInfo | null;
  name: string;
  folderPath: string;
  onNameChange: (v: string) => void;
  onFolderChange: (v: string) => void;
  onPickFolder: () => Promise<void>;
  error: string | null;
  submitting: boolean;
  canGoBack: boolean;
  onBack: () => void;
  onClose: () => void;
  onNext: () => void;
}) {
  return (
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
        onChange={(e) => onNameChange(e.target.value)}
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
            onChange={(e) => onFolderChange(e.target.value)}
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
          <Button size="sm" variant="secondary" onClick={onPickFolder} disabled={submitting}>
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
          onClick={onBack}
          disabled={submitting || !canGoBack}
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back
        </Button>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button size="sm" variant="primary" onClick={onNext} disabled={submitting}>
            Next <ChevronRight className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 3 — Team & models
// ---------------------------------------------------------------------------

interface StepTeamProps {
  workflowMode: WorkflowMode;
  onWorkflowModeChange: (m: WorkflowMode) => void;
  presets: RolePresetSummary[];
  selectedPresetId: string | null;
  onApplyPreset: (id: string) => Promise<void>;
  roles: LocalRole[];
  onRoleUpdate: (localId: string, patch: Partial<LocalRole>) => void;
  onRoleRemove: (localId: string) => void;
  sameModelForAll: boolean;
  onSameModelToggle: (checked: boolean) => void;
  sharedModelId: string;
  onSharedModelChange: (modelId: string) => void;
  hasModels: boolean | null;
  showAddRole: boolean;
  onShowAddRole: (v: boolean) => void;
  onAddRole: (role: LocalRole) => void;
  unconfiguiredRoles: LocalRole[];
  canCreate: boolean;
  submitting: boolean;
  error: string | null;
  onBack: () => void;
  onClose: () => void;
  onSubmit: () => void;
}

function StepTeam({
  workflowMode,
  onWorkflowModeChange,
  presets,
  selectedPresetId,
  onApplyPreset,
  roles,
  onRoleUpdate,
  onRoleRemove,
  sameModelForAll,
  onSameModelToggle,
  sharedModelId,
  onSharedModelChange,
  hasModels,
  showAddRole,
  onShowAddRole,
  onAddRole,
  unconfiguiredRoles,
  canCreate,
  submitting,
  error,
  onBack,
  onClose,
  onSubmit,
}: StepTeamProps) {
  const [presetApplying, setPresetApplying] = useState(false);
  const [presetMenuOpen, setPresetMenuOpen] = useState(false);
  const presetMenuRef = useRef<HTMLDivElement>(null);

  // Close preset menu on outside click
  useEffect(() => {
    if (!presetMenuOpen) return;
    function handler(e: MouseEvent) {
      if (presetMenuRef.current && !presetMenuRef.current.contains(e.target as Node)) {
        setPresetMenuOpen(false);
      }
    }
    window.addEventListener("mousedown", handler);
    return () => window.removeEventListener("mousedown", handler);
  }, [presetMenuOpen]);

  async function handlePresetSelect(presetId: string) {
    setPresetMenuOpen(false);
    setPresetApplying(true);
    try {
      await onApplyPreset(presetId);
    } finally {
      setPresetApplying(false);
    }
  }

  // No-models empty state
  if (hasModels === false) {
    return <NoModelsEmptyState onClose={onClose} />;
  }

  const selectedPreset = presets.find((p) => p.preset_id === selectedPresetId);

  return (
    <div className="space-y-5">
      {/* Workflow segmented control */}
      <div>
        <label className="block text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-2">
          Workflow
        </label>
        <div className="flex gap-1 p-1 bg-neutral-100 dark:bg-neutral-800 rounded-xl w-fit">
          {WORKFLOW_MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              data-testid={`workflow-mode-${m.id}`}
              onClick={() => onWorkflowModeChange(m.id)}
              className={cn(
                "px-3 py-1.5 text-xs font-medium rounded-lg transition-all",
                workflowMode === m.id
                  ? "bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white shadow-sm"
                  : "text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300",
              )}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {/* Apply preset */}
      <div>
        <label className="block text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-2">
          Apply preset (optional)
        </label>
        <div className="relative" ref={presetMenuRef}>
          <button
            type="button"
            onClick={() => setPresetMenuOpen((v) => !v)}
            disabled={presetApplying}
            className={cn(
              "flex items-center justify-between gap-2 px-3 py-2 rounded-xl text-sm w-64",
              "bg-neutral-50 dark:bg-neutral-800",
              "border border-neutral-200 dark:border-neutral-700",
              "text-neutral-900 dark:text-white",
              "hover:border-primary-500 focus:outline-none transition-all",
            )}
          >
            <span className="truncate text-left text-sm">
              {presetApplying
                ? "Applying…"
                : selectedPreset
                  ? selectedPreset.name
                  : "Pick a preset"}
            </span>
            <ChevronDown className={cn("w-4 h-4 text-neutral-400 flex-shrink-0 transition-transform", presetMenuOpen && "rotate-180")} />
          </button>
          {presetMenuOpen && (
            <div className="absolute left-0 top-full mt-1 z-50 w-64 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 shadow-xl overflow-hidden">
              {presets.map((p) => (
                <button
                  key={p.preset_id}
                  type="button"
                  onClick={() => handlePresetSelect(p.preset_id)}
                  className={cn(
                    "w-full text-left px-3 py-2.5 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors",
                    p.preset_id === selectedPresetId
                      ? "bg-primary-50 dark:bg-primary-500/10 text-primary-600 dark:text-primary-400"
                      : "text-neutral-800 dark:text-neutral-200",
                  )}
                >
                  <div className="font-medium">{p.name}</div>
                  <div className="text-[11px] text-neutral-500 dark:text-neutral-400 mt-0.5">
                    {p.description}
                  </div>
                </button>
              ))}
              {presets.length === 0 && (
                <div className="px-3 py-4 text-xs text-neutral-400 text-center">No presets available</div>
              )}
            </div>
          )}
        </div>
        {selectedPreset && (
          <p className="mt-1.5 text-[11px] text-neutral-500 dark:text-neutral-400">
            Preset applied — {selectedPreset.role_count} roles loaded. Assign a model to each before creating.
          </p>
        )}
      </div>

      {/* Roles section */}
      {hasModels === null ? (
        <div className="flex items-center gap-2 text-sm text-neutral-500 py-4">
          <Loader2 className="w-4 h-4 animate-spin" /> Checking available models…
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
              Roles
            </span>
          </div>

          {/* Same model for all shortcut */}
          {roles.length > 0 && (
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={sameModelForAll}
                onChange={(e) => onSameModelToggle(e.target.checked)}
                className="w-3.5 h-3.5 rounded accent-primary-500"
                data-testid="same-model-checkbox"
              />
              <span className="text-xs text-neutral-600 dark:text-neutral-400">
                Use the same model for all roles
              </span>
            </label>
          )}

          {/* Shared model picker */}
          {sameModelForAll && roles.length > 0 && (
            <div className="pl-5">
              <ModelPicker
                value={sharedModelId}
                onChange={onSharedModelChange}
                size="sm"
              />
            </div>
          )}

          {/* Role cards */}
          {roles.length === 0 && (
            <div className="text-xs text-neutral-400 dark:text-neutral-500 py-3 text-center border border-dashed border-neutral-200 dark:border-neutral-800 rounded-xl">
              No roles yet. Apply a preset above or add roles manually.
            </div>
          )}

          <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
            {roles.map((role) => (
              <RoleCard
                key={role._localId}
                role={role}
                showModelPicker={!sameModelForAll}
                onUpdate={(patch) => onRoleUpdate(role._localId, patch)}
                onRemove={() => onRoleRemove(role._localId)}
              />
            ))}
          </div>

          {/* Add role */}
          {!showAddRole && (
            <button
              type="button"
              onClick={() => onShowAddRole(true)}
              className="flex items-center gap-1.5 text-xs text-primary-500 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" /> Add role
            </button>
          )}

          {showAddRole && (
            <AddRoleForm
              nextOrder={roles.length}
              onAdd={onAddRole}
              onCancel={() => onShowAddRole(false)}
            />
          )}
        </div>
      )}

      {/* Gating banner */}
      {hasModels === true && unconfiguiredRoles.length > 0 && (
        <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 text-xs text-red-600 dark:text-red-400">
          <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
          <span>
            Pick a model for:{" "}
            <strong>{unconfiguiredRoles.map((r) => r.display_name).join(", ")}</strong>
          </span>
        </div>
      )}

      {error && (
        <div className="text-xs text-red-500 dark:text-red-400">{error}</div>
      )}

      {/* Footer actions */}
      <div className="flex items-center justify-between gap-2 pt-1">
        <Button size="sm" variant="ghost" onClick={onBack} disabled={submitting}>
          <ArrowLeft className="w-3.5 h-3.5" /> Back
        </Button>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            size="sm"
            variant="primary"
            onClick={onSubmit}
            disabled={!canCreate || submitting}
            data-testid="create-project-btn"
          >
            {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            Create Project
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// No-models empty state
// ---------------------------------------------------------------------------

function NoModelsEmptyState({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center gap-4">
      <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-amber-50 dark:bg-amber-500/10 text-amber-500">
        <AlertCircle className="w-7 h-7" />
      </div>
      <div>
        <h4 className="text-sm font-semibold text-neutral-900 dark:text-white mb-1">
          No models available yet
        </h4>
        <p className="text-xs text-neutral-500 dark:text-neutral-400 max-w-xs">
          Download a local model from the Model Hub, or save a cloud provider API
          key in Settings.
        </p>
      </div>
      <div className="flex items-center gap-2 flex-wrap justify-center">
        <Button
          size="sm"
          variant="secondary"
          onClick={() => { onClose(); navigate("/models"); }}
          data-testid="go-to-model-hub"
        >
          Open Model Hub
        </Button>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => { onClose(); navigate("/settings?tab=ai-providers"); }}
          data-testid="go-to-ai-providers"
        >
          Open AI Providers
        </Button>
      </div>
      <Button size="sm" variant="ghost" onClick={onClose}>
        Cancel
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Role card
// ---------------------------------------------------------------------------

function RoleCard({
  role,
  showModelPicker,
  onUpdate,
  onRemove,
}: {
  role: LocalRole;
  showModelPicker: boolean;
  onUpdate: (patch: Partial<LocalRole>) => void;
  onRemove: () => void;
}) {
  const [showPrompt, setShowPrompt] = useState(false);

  return (
    <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-neutral-900 dark:text-white truncate">
          {role.display_name}
        </span>
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Enabled toggle */}
          <button
            type="button"
            role="switch"
            aria-checked={role.enabled}
            onClick={() => onUpdate({ enabled: !role.enabled })}
            className={cn(
              "w-8 h-4.5 rounded-full transition-colors relative flex-shrink-0",
              role.enabled
                ? "bg-primary-500"
                : "bg-neutral-300 dark:bg-neutral-600",
            )}
          >
            <span
              className={cn(
                "absolute top-0.5 w-3.5 h-3.5 rounded-full bg-white shadow transition-transform",
                role.enabled ? "translate-x-4" : "translate-x-0.5",
              )}
            />
          </button>
          <button
            type="button"
            onClick={onRemove}
            className="p-1 text-neutral-400 hover:text-red-500 transition-colors"
            aria-label="Remove role"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {showModelPicker && (
        <ModelPicker
          value={role.model_id}
          onChange={(modelId) => onUpdate({ model_id: modelId })}
          size="sm"
        />
      )}

      <button
        type="button"
        onClick={() => setShowPrompt((v) => !v)}
        className="flex items-center gap-1 text-[11px] text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
      >
        <ChevronDown className={cn("w-3 h-3 transition-transform", showPrompt && "rotate-180")} />
        {showPrompt ? "Hide" : "Show"} system prompt
      </button>

      {showPrompt && (
        <textarea
          value={role.system_prompt}
          onChange={(e) => onUpdate({ system_prompt: e.target.value })}
          rows={3}
          placeholder="Describe what this role does…"
          className={cn(
            "w-full px-3 py-2 rounded-lg text-xs font-mono resize-y",
            "bg-neutral-50 dark:bg-neutral-800",
            "border border-neutral-200 dark:border-neutral-700",
            "text-neutral-900 dark:text-white",
            "placeholder:text-neutral-400 dark:placeholder:text-neutral-500",
            "focus:outline-none focus:ring-1 focus:ring-primary-500/40",
          )}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add Role mini-form
// ---------------------------------------------------------------------------

const ROLE_KINDS: RoleKind[] = [
  "coder",
  "reviewer",
  "security",
  "ui_ux",
  "docs",
  "tester",
  "planner",
  "custom",
];

function AddRoleForm({
  nextOrder,
  onAdd,
  onCancel,
}: {
  nextOrder: number;
  onAdd: (role: LocalRole) => void;
  onCancel: () => void;
}) {
  const [kind, setKind] = useState<RoleKind>("coder");
  const [displayName, setDisplayName] = useState(ROLE_KIND_LABELS["coder"]);
  const [prompt, setPrompt] = useState("");
  const [modelId, setModelId] = useState("");
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(4096);
  const [formError, setFormError] = useState<string | null>(null);

  function handleKindChange(k: RoleKind) {
    setKind(k);
    setDisplayName(ROLE_KIND_LABELS[k]);
  }

  function handleAdd() {
    setFormError(null);
    if (!modelId || modelId === "" || modelId === "__DEFAULT__") {
      setFormError("Pick a model for this role.");
      return;
    }
    onAdd({
      _localId: makeLocalId(),
      role_kind: kind,
      display_name: displayName,
      system_prompt: prompt,
      model_id: modelId,
      temperature,
      max_tokens: maxTokens,
      enabled: true,
      order: nextOrder,
    });
  }

  return (
    <div className="rounded-xl border border-primary-200 dark:border-primary-500/30 bg-primary-50/30 dark:bg-primary-500/5 p-3 space-y-3">
      <div className="text-xs font-semibold text-neutral-700 dark:text-neutral-300">
        New role
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-[11px] text-neutral-500 dark:text-neutral-400 mb-1">
            Kind
          </label>
          <select
            value={kind}
            onChange={(e) => handleKindChange(e.target.value as RoleKind)}
            className={cn(
              "w-full px-2.5 py-1.5 rounded-lg text-xs",
              "bg-white dark:bg-neutral-800",
              "border border-neutral-200 dark:border-neutral-700",
              "text-neutral-900 dark:text-white",
              "focus:outline-none focus:ring-1 focus:ring-primary-500/40",
            )}
          >
            {ROLE_KINDS.map((k) => (
              <option key={k} value={k}>
                {ROLE_KIND_LABELS[k]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-[11px] text-neutral-500 dark:text-neutral-400 mb-1">
            Display name
          </label>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className={cn(
              "w-full px-2.5 py-1.5 rounded-lg text-xs",
              "bg-white dark:bg-neutral-800",
              "border border-neutral-200 dark:border-neutral-700",
              "text-neutral-900 dark:text-white",
              "focus:outline-none focus:ring-1 focus:ring-primary-500/40",
            )}
          />
        </div>
      </div>

      <div>
        <label className="block text-[11px] text-neutral-500 dark:text-neutral-400 mb-1">
          Model
        </label>
        <ModelPicker value={modelId} onChange={setModelId} size="sm" />
      </div>

      <div>
        <label className="block text-[11px] text-neutral-500 dark:text-neutral-400 mb-1">
          System prompt
        </label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={2}
          placeholder="Describe what this role does…"
          className={cn(
            "w-full px-2.5 py-1.5 rounded-lg text-xs font-mono resize-y",
            "bg-white dark:bg-neutral-800",
            "border border-neutral-200 dark:border-neutral-700",
            "text-neutral-900 dark:text-white",
            "placeholder:text-neutral-400 dark:placeholder:text-neutral-500",
            "focus:outline-none focus:ring-1 focus:ring-primary-500/40",
          )}
        />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-[11px] text-neutral-500 dark:text-neutral-400 mb-1">
            Temperature
          </label>
          <input
            type="number"
            value={temperature}
            min={0}
            max={2}
            step={0.1}
            onChange={(e) => setTemperature(parseFloat(e.target.value) || 0.7)}
            className={cn(
              "w-full px-2.5 py-1.5 rounded-lg text-xs",
              "bg-white dark:bg-neutral-800",
              "border border-neutral-200 dark:border-neutral-700",
              "text-neutral-900 dark:text-white",
              "focus:outline-none focus:ring-1 focus:ring-primary-500/40",
            )}
          />
        </div>
        <div>
          <label className="block text-[11px] text-neutral-500 dark:text-neutral-400 mb-1">
            Max tokens
          </label>
          <input
            type="number"
            value={maxTokens}
            min={256}
            max={32768}
            step={256}
            onChange={(e) => setMaxTokens(parseInt(e.target.value) || 4096)}
            className={cn(
              "w-full px-2.5 py-1.5 rounded-lg text-xs",
              "bg-white dark:bg-neutral-800",
              "border border-neutral-200 dark:border-neutral-700",
              "text-neutral-900 dark:text-white",
              "focus:outline-none focus:ring-1 focus:ring-primary-500/40",
            )}
          />
        </div>
      </div>

      {formError && (
        <div className="text-[11px] text-red-500 dark:text-red-400">{formError}</div>
      )}

      <div className="flex items-center gap-2 justify-end">
        <Button size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button size="sm" variant="primary" onClick={handleAdd}>
          <Plus className="w-3.5 h-3.5" /> Add
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TemplateOption (unchanged from original)
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Legacy export — keep backward-compatible prop shape
// The parent (projects.tsx) currently passes `onSubmit`. We accept it but
// ignore it since the dialog now handles the full create flow.
// ---------------------------------------------------------------------------

export type { NewProjectDialogProps };
