import { useCallback, useEffect, useRef, useState } from "react";
import { Plus, Layers, Loader2, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { RoleCard } from "@/components/coder/role-card";
import {
  type CoderAgentRole,
  type RoleKind,
  type RolePresetSummary,
  type WorkflowMode,
  type CoderAgentRoleUpdate,
  listRoles,
  createRole,
  updateRole,
  deleteRole,
  applyPreset,
  reorderRoles,
  getWorkflowMode,
  setWorkflowMode,
  listPresets,
} from "@/lib/api/coder-workflow-client";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const WORKFLOW_MODES: { value: WorkflowMode; label: string; hint: string }[] = [
  { value: "solo", label: "Solo", hint: "Single coder role handles the full request" },
  { value: "sequential", label: "Sequential", hint: "Roles execute in order, each seeing the previous output" },
  { value: "parallel", label: "Parallel", hint: "All roles run simultaneously; outputs merged" },
  { value: "custom", label: "Custom", hint: "Manual wiring — advanced" },
];

const ROLE_KIND_DEFAULTS: Record<RoleKind, { display_name: string; system_prompt: string }> = {
  coder: { display_name: "Coder", system_prompt: "You are an expert software engineer. Write clean, well-documented, production-ready code." },
  reviewer: { display_name: "Reviewer", system_prompt: "You are a code reviewer. Provide constructive feedback on code quality, correctness, and best practices." },
  security: { display_name: "Security", system_prompt: "You are a security engineer. Identify vulnerabilities, security risks, and suggest mitigations." },
  ui_ux: { display_name: "UI/UX", system_prompt: "You are a UI/UX designer. Review interfaces for usability, accessibility, and design quality." },
  docs: { display_name: "Docs", system_prompt: "You are a technical writer. Write clear, comprehensive documentation for developers." },
  tester: { display_name: "Tester", system_prompt: "You are a QA engineer. Write thorough test cases and identify edge cases." },
  planner: { display_name: "Planner", system_prompt: "You are a software architect. Decompose problems into clear implementation plans." },
  custom: { display_name: "Custom Role", system_prompt: "You are a specialized AI assistant." },
};

const ROLE_KIND_OPTIONS: RoleKind[] = [
  "coder", "reviewer", "security", "ui_ux", "docs", "tester", "planner", "custom",
];

// Cost/latency heuristic
function estimateCostLine(roles: CoderAgentRole[]): string {
  const enabled = roles.filter((r) => r.enabled);
  if (enabled.length === 0) return "No enabled roles";
  const cloudCount = enabled.filter((r) => r.model_id.includes(":")).length;
  const localCount = enabled.length - cloudCount;
  if (cloudCount === 0) return `free (local) · ${localCount} local role${localCount !== 1 ? "s" : ""}`;
  if (localCount === 0) return `varies (~$0.001–0.05/turn) · ${cloudCount} cloud role${cloudCount !== 1 ? "s" : ""}`;
  return `~$${(cloudCount * 0.01).toFixed(3)}/turn · ${localCount} local + ${cloudCount} cloud`;
}

// ---------------------------------------------------------------------------
// Debounce hook
// ---------------------------------------------------------------------------

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState<T>(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

// ---------------------------------------------------------------------------
// Main TeamPanel component
// ---------------------------------------------------------------------------

interface TeamPanelProps {
  projectId: string;
}

interface RoleSaveState {
  saving: boolean;
  saved: boolean;
}

export function TeamPanel({ projectId }: TeamPanelProps) {
  const [roles, setRoles] = useState<CoderAgentRole[]>([]);
  const [workflowMode, setWorkflowModeState] = useState<WorkflowMode>("solo");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  // Pending changes per role (role_id -> partial update)
  const pendingRef = useRef<Map<string, CoderAgentRoleUpdate>>(new Map());
  // Save state per role
  const [saveStates, setSaveStates] = useState<Record<string, RoleSaveState>>({});

  // Dialogs
  const [presetDialogOpen, setPresetDialogOpen] = useState(false);
  const [addRoleDialogOpen, setAddRoleDialogOpen] = useState(false);
  const [presets, setPresets] = useState<RolePresetSummary[]>([]);
  const [presetsLoading, setPresetsLoading] = useState(false);
  const [newRoleKind, setNewRoleKind] = useState<RoleKind>("coder");
  const [addingRole, setAddingRole] = useState(false);
  const [applyingPreset, setApplyingPreset] = useState(false);

  // Drag state
  const dragIndexRef = useRef<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

  // Load roles + workflow mode
  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [fetchedRoles, fetchedMode] = await Promise.all([
        listRoles(projectId),
        getWorkflowMode(projectId),
      ]);
      setRoles(fetchedRoles);
      setWorkflowModeState(fetchedMode);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load team configuration");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Toast auto-clear
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(id);
  }, [toast]);

  // ---------------------------------------------------------------------------
  // Debounced save for each role
  // ---------------------------------------------------------------------------

  // We flush pending saves via a timer per role
  const saveTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  function queueSave(roleId: string, patch: CoderAgentRoleUpdate) {
    // Merge into pending
    const current = pendingRef.current.get(roleId) ?? {};
    pendingRef.current.set(roleId, { ...current, ...patch });

    setSaveStates((prev) => ({ ...prev, [roleId]: { saving: true, saved: false } }));

    // Cancel existing timer
    const existing = saveTimersRef.current.get(roleId);
    if (existing) clearTimeout(existing);

    const timer = setTimeout(async () => {
      const pending = pendingRef.current.get(roleId);
      if (!pending) return;
      pendingRef.current.delete(roleId);
      try {
        const updated = await updateRole(projectId, roleId, pending);
        setRoles((prev) => prev.map((r) => (r.role_id === roleId ? updated : r)));
        setSaveStates((prev) => ({ ...prev, [roleId]: { saving: false, saved: true } }));
        // Clear saved indicator after 2s
        setTimeout(() => {
          setSaveStates((prev) => ({ ...prev, [roleId]: { saving: false, saved: false } }));
        }, 2000);
      } catch {
        setSaveStates((prev) => ({ ...prev, [roleId]: { saving: false, saved: false } }));
      }
    }, 400);

    saveTimersRef.current.set(roleId, timer);
  }

  function handleRoleChange(roleId: string, partial: CoderAgentRoleUpdate) {
    // Optimistic update locally
    setRoles((prev) =>
      prev.map((r) => (r.role_id === roleId ? { ...r, ...partial } : r)),
    );
    queueSave(roleId, partial);
  }

  // ---------------------------------------------------------------------------
  // Delete / duplicate
  // ---------------------------------------------------------------------------

  async function handleDeleteRole(roleId: string) {
    try {
      await deleteRole(projectId, roleId);
      setRoles((prev) => prev.filter((r) => r.role_id !== roleId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete role");
    }
  }

  async function handleDuplicateRole(role: CoderAgentRole) {
    try {
      const created = await createRole(projectId, {
        role_kind: role.role_kind,
        display_name: `${role.display_name} (copy)`,
        system_prompt: role.system_prompt,
        model_id: role.model_id,
        temperature: role.temperature,
        max_tokens: role.max_tokens,
        enabled: role.enabled,
        order: roles.length + 1,
      });
      setRoles((prev) => [...prev, created]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to duplicate role");
    }
  }

  // ---------------------------------------------------------------------------
  // Workflow mode change
  // ---------------------------------------------------------------------------

  async function handleModeChange(mode: WorkflowMode) {
    setWorkflowModeState(mode);
    try {
      await setWorkflowMode(projectId, mode);
    } catch {
      // revert on failure
      await loadData();
    }
  }

  // ---------------------------------------------------------------------------
  // Presets
  // ---------------------------------------------------------------------------

  async function openPresetDialog() {
    setPresetsLoading(true);
    setPresetDialogOpen(true);
    try {
      const list = await listPresets();
      setPresets(list);
    } catch {
      setPresets([]);
    } finally {
      setPresetsLoading(false);
    }
  }

  async function handleApplyPreset(presetId: string) {
    setApplyingPreset(true);
    try {
      const newRoles = await applyPreset(projectId, presetId);
      const mode = await getWorkflowMode(projectId);
      setRoles(newRoles);
      setWorkflowModeState(mode);
      setPresetDialogOpen(false);
      setToast("Preset applied");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to apply preset");
    } finally {
      setApplyingPreset(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Add role
  // ---------------------------------------------------------------------------

  async function handleAddRole() {
    setAddingRole(true);
    try {
      const defaults = ROLE_KIND_DEFAULTS[newRoleKind];
      const created = await createRole(projectId, {
        role_kind: newRoleKind,
        display_name: defaults.display_name,
        system_prompt: defaults.system_prompt,
        model_id: "",
        temperature: 0.7,
        max_tokens: 4096,
        enabled: true,
        order: roles.length + 1,
      });
      setRoles((prev) => [...prev, created]);
      setAddRoleDialogOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create role");
    } finally {
      setAddingRole(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Drag and drop (HTML5 native)
  // ---------------------------------------------------------------------------

  function handleDragStart(index: number) {
    dragIndexRef.current = index;
  }

  function handleDragOver(e: React.DragEvent, index: number) {
    e.preventDefault();
    setDragOverIndex(index);
  }

  function handleDrop(e: React.DragEvent, dropIndex: number) {
    e.preventDefault();
    const dragIndex = dragIndexRef.current;
    if (dragIndex === null || dragIndex === dropIndex) {
      setDragOverIndex(null);
      return;
    }

    const reordered = [...roles];
    const [dragged] = reordered.splice(dragIndex, 1);
    reordered.splice(dropIndex, 0, dragged);
    setRoles(reordered);
    setDragOverIndex(null);
    dragIndexRef.current = null;

    // Persist reorder
    reorderRoles(projectId, reordered.map((r) => r.role_id)).catch(() => {
      // silently fail; roles will re-sync on next load
    });
  }

  function handleDragEnd() {
    setDragOverIndex(null);
    dragIndexRef.current = null;
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 gap-2 text-neutral-500 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading team…
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4 overflow-y-auto h-full">
      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-xl border border-emerald-200 dark:border-emerald-700/40 bg-emerald-50 dark:bg-emerald-500/10 px-4 py-2.5 text-sm text-emerald-700 dark:text-emerald-300 shadow-lg">
          <CheckCircle2 className="w-4 h-4" />
          {toast}
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="rounded-xl border border-red-200 dark:border-red-700/40 bg-red-50 dark:bg-red-500/5 px-4 py-2 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {/* Workflow section */}
      <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
        <div className="flex items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-primary-500" />
            <span className="text-sm font-semibold text-neutral-900 dark:text-white">Workflow</span>
          </div>
          <Button size="sm" variant="secondary" onClick={openPresetDialog}>
            Apply preset
          </Button>
        </div>

        {/* Mode selector */}
        <div
          className="grid grid-cols-4 gap-1 rounded-xl border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 p-1"
          role="radiogroup"
          aria-label="Workflow mode"
        >
          {WORKFLOW_MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              role="radio"
              aria-checked={workflowMode === m.value}
              data-testid={`workflow-mode-${m.value}`}
              onClick={() => handleModeChange(m.value)}
              title={m.hint}
              className={cn(
                "px-3 py-2 rounded-lg text-xs font-medium transition-all",
                workflowMode === m.value
                  ? "bg-white dark:bg-neutral-900 text-primary-600 dark:text-primary-400 shadow-sm"
                  : "text-neutral-600 dark:text-neutral-400 hover:text-neutral-800 dark:hover:text-neutral-200",
              )}
            >
              {m.label}
            </button>
          ))}
        </div>

        {/* Current mode hint */}
        <p className="mt-2 text-xs text-neutral-500 dark:text-neutral-400">
          {WORKFLOW_MODES.find((m) => m.value === workflowMode)?.hint}
        </p>

        {/* Cost estimate */}
        <div className="mt-3 pt-3 border-t border-neutral-100 dark:border-neutral-800 text-xs text-neutral-500 dark:text-neutral-400">
          Estimated cost/turn: {estimateCostLine(roles)}
        </div>
      </div>

      {/* Roles section */}
      <div className="rounded-2xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
        <div className="flex items-center justify-between gap-3 mb-4">
          <span className="text-sm font-semibold text-neutral-900 dark:text-white">
            Roles{roles.length > 0 && <span className="ml-1.5 text-neutral-400 font-normal">({roles.length})</span>}
          </span>
          <span className="text-[11px] text-neutral-400 dark:text-neutral-500">drag to reorder</span>
        </div>

        {roles.length === 0 ? (
          <div className="py-8 text-center text-sm text-neutral-400 dark:text-neutral-500 border border-dashed border-neutral-200 dark:border-neutral-700 rounded-xl">
            No roles yet. Apply a preset or add a role.
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {roles.map((role, index) => (
              <RoleCard
                key={role.role_id}
                role={role}
                onChange={(partial) => handleRoleChange(role.role_id, partial)}
                onDelete={() => handleDeleteRole(role.role_id)}
                onDuplicate={() => handleDuplicateRole(role)}
                onDragStart={() => handleDragStart(index)}
                onDragOver={(e) => handleDragOver(e, index)}
                onDrop={(e) => handleDrop(e, index)}
                onDragEnd={handleDragEnd}
                isDraggingOver={dragOverIndex === index}
                saving={saveStates[role.role_id]?.saving}
                saved={saveStates[role.role_id]?.saved}
              />
            ))}
          </div>
        )}

        {/* Add role button */}
        <Button
          size="sm"
          variant="secondary"
          className="mt-4 w-full"
          onClick={() => setAddRoleDialogOpen(true)}
        >
          <Plus className="w-3.5 h-3.5" /> Add role
        </Button>
      </div>

      {/* Preset dialog */}
      <Dialog
        open={presetDialogOpen}
        onClose={() => setPresetDialogOpen(false)}
        title="Apply a preset"
        className="max-w-lg"
      >
        <p className="mb-4 text-xs text-neutral-500 dark:text-neutral-400">
          Presets replace your current roles with a curated team configuration.
        </p>
        {presetsLoading ? (
          <div className="flex items-center gap-2 text-xs text-neutral-500 py-4">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading presets…
          </div>
        ) : presets.length === 0 ? (
          <p className="text-xs text-neutral-400">No presets available.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {presets.map((preset) => (
              <button
                key={preset.preset_id}
                type="button"
                onClick={() => handleApplyPreset(preset.preset_id)}
                disabled={applyingPreset}
                className={cn(
                  "w-full text-left rounded-xl border border-neutral-200 dark:border-neutral-700 p-4",
                  "hover:border-primary-500 hover:bg-primary-50 dark:hover:bg-primary-500/5 transition-colors",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-neutral-900 dark:text-white">{preset.name}</div>
                    <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">{preset.description}</div>
                  </div>
                  <div className="flex-shrink-0 text-right">
                    <div className="text-xs font-medium text-neutral-600 dark:text-neutral-300">{preset.role_count} roles</div>
                    <div className="text-[11px] text-neutral-400 capitalize">{preset.workflow_mode}</div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </Dialog>

      {/* Add role dialog */}
      <Dialog
        open={addRoleDialogOpen}
        onClose={() => setAddRoleDialogOpen(false)}
        title="Add role"
        actions={
          <>
            <Button variant="ghost" size="sm" onClick={() => setAddRoleDialogOpen(false)} disabled={addingRole}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" onClick={handleAddRole} disabled={addingRole}>
              {addingRole ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
              Add
            </Button>
          </>
        }
      >
        <div>
          <label className="block text-xs font-medium text-neutral-700 dark:text-neutral-300 mb-2">
            Role type
          </label>
          <div className="grid grid-cols-2 gap-2">
            {ROLE_KIND_OPTIONS.map((kind) => (
              <button
                key={kind}
                type="button"
                onClick={() => setNewRoleKind(kind)}
                className={cn(
                  "px-3 py-2 rounded-xl border text-sm text-left transition-colors capitalize",
                  newRoleKind === kind
                    ? "border-primary-500 bg-primary-50 dark:bg-primary-500/10 text-primary-700 dark:text-primary-300"
                    : "border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 hover:border-neutral-300 dark:hover:border-neutral-600",
                )}
              >
                {kind === "ui_ux" ? "UI/UX" : kind.charAt(0).toUpperCase() + kind.slice(1)}
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs text-neutral-500 dark:text-neutral-400">
            {ROLE_KIND_DEFAULTS[newRoleKind].display_name} — you can customize the name, prompt, and model after creation.
          </p>
        </div>
      </Dialog>
    </div>
  );
}

// Export the debounce hook for reuse
export { useDebounce };
