import { useEffect, useRef, useState } from "react";
import {
  Code,
  FileText,
  GripVertical,
  MessageSquareDashed,
  MoreVertical,
  Palette,
  Settings2,
  ShieldCheck,
  Telescope,
  TestTube2,
  ChevronDown,
  ChevronUp,
  Loader2,
  Check,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ModelPicker } from "@/components/coder/model-picker";
import type { CoderAgentRole, RoleKind } from "@/lib/api/coder-workflow-client";

// ---------------------------------------------------------------------------
// Icons per role kind
// ---------------------------------------------------------------------------

const ROLE_ICONS: Record<RoleKind, React.ElementType> = {
  coder: Code,
  reviewer: MessageSquareDashed,
  security: ShieldCheck,
  ui_ux: Palette,
  docs: FileText,
  tester: TestTube2,
  planner: Telescope,
  custom: Settings2,
};

const ROLE_COLORS: Record<RoleKind, string> = {
  coder: "text-primary-500",
  reviewer: "text-sky-500",
  security: "text-rose-500",
  ui_ux: "text-violet-500",
  docs: "text-emerald-500",
  tester: "text-amber-500",
  planner: "text-indigo-500",
  custom: "text-neutral-500",
};

const ROLE_BG: Record<RoleKind, string> = {
  coder: "bg-primary-50 dark:bg-primary-500/10",
  reviewer: "bg-sky-50 dark:bg-sky-500/10",
  security: "bg-rose-50 dark:bg-rose-500/10",
  ui_ux: "bg-violet-50 dark:bg-violet-500/10",
  docs: "bg-emerald-50 dark:bg-emerald-500/10",
  tester: "bg-amber-50 dark:bg-amber-500/10",
  planner: "bg-indigo-50 dark:bg-indigo-500/10",
  custom: "bg-neutral-100 dark:bg-neutral-800",
};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type RolePartial = Partial<Omit<CoderAgentRole, "role_id" | "project_id">>;

interface RoleCardProps {
  role: CoderAgentRole;
  onChange: (partial: RolePartial) => void;
  onDelete: () => void;
  onDuplicate: () => void;
  /** draggable callbacks */
  onDragStart?: (e: React.DragEvent) => void;
  onDragOver?: (e: React.DragEvent) => void;
  onDrop?: (e: React.DragEvent) => void;
  onDragEnd?: (e: React.DragEvent) => void;
  isDraggingOver?: boolean;
  saving?: boolean;
  saved?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RoleCard({
  role,
  onChange,
  onDelete,
  onDuplicate,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
  isDraggingOver,
  saving,
  saved,
}: RoleCardProps) {
  const [promptOpen, setPromptOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [localName, setLocalName] = useState(role.display_name);
  const menuRef = useRef<HTMLDivElement>(null);

  // Sync local name when role changes externally
  useEffect(() => {
    setLocalName(role.display_name);
  }, [role.display_name]);

  // Close menu on outside click
  useEffect(() => {
    if (!menuOpen) return;
    function handler(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    window.addEventListener("mousedown", handler);
    return () => window.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  const Icon = ROLE_ICONS[role.role_kind];
  const iconColor = ROLE_COLORS[role.role_kind];
  const iconBg = ROLE_BG[role.role_kind];

  function handleNameBlur() {
    const trimmed = localName.trim();
    if (trimmed && trimmed !== role.display_name) {
      onChange({ display_name: trimmed });
    }
  }

  function handleModelChange(modelId: string) {
    onChange({ model_id: modelId });
  }

  function handleTemperatureChange(e: React.ChangeEvent<HTMLInputElement>) {
    onChange({ temperature: parseFloat(e.target.value) });
  }

  function handleMaxTokensChange(e: React.ChangeEvent<HTMLInputElement>) {
    onChange({ max_tokens: parseInt(e.target.value, 10) });
  }

  function handleEnabledToggle() {
    onChange({ enabled: !role.enabled });
  }

  function handlePromptChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    onChange({ system_prompt: e.target.value });
  }

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onDragEnd={onDragEnd}
      className={cn(
        "rounded-2xl border bg-white dark:bg-neutral-900 transition-all",
        isDraggingOver
          ? "border-primary-500 ring-2 ring-primary-500/20"
          : "border-neutral-200 dark:border-neutral-800",
        !role.enabled && "opacity-60",
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3">
        {/* Drag handle */}
        <div
          className="cursor-grab active:cursor-grabbing text-neutral-400 flex-shrink-0"
          title="Drag to reorder"
        >
          <GripVertical className="w-4 h-4" />
        </div>

        {/* Role icon */}
        <div className={cn("flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center", iconBg)}>
          <Icon className={cn("w-4 h-4", iconColor)} />
        </div>

        {/* Editable name */}
        <input
          type="text"
          value={localName}
          onChange={(e) => setLocalName(e.target.value)}
          onBlur={handleNameBlur}
          className={cn(
            "flex-1 min-w-0 bg-transparent border-none text-sm font-semibold",
            "text-neutral-900 dark:text-white",
            "focus:outline-none focus:ring-0",
            "placeholder:text-neutral-400",
          )}
          placeholder="Role name"
        />

        {/* Save indicator */}
        <div className="flex-shrink-0 text-[10px]">
          {saving && (
            <span className="flex items-center gap-1 text-neutral-400">
              <Loader2 className="w-3 h-3 animate-spin" /> Saving
            </span>
          )}
          {saved && !saving && (
            <span className="flex items-center gap-1 text-emerald-500">
              <Check className="w-3 h-3" /> Saved
            </span>
          )}
        </div>

        {/* Enabled toggle */}
        <button
          type="button"
          onClick={handleEnabledToggle}
          role="switch"
          aria-checked={role.enabled}
          className={cn(
            "flex-shrink-0 relative inline-flex h-5 w-9 rounded-full transition-colors",
            "focus:outline-none focus:ring-2 focus:ring-primary-500/40",
            role.enabled ? "bg-primary-500" : "bg-neutral-300 dark:bg-neutral-600",
          )}
          title={role.enabled ? "Enabled — click to disable" : "Disabled — click to enable"}
        >
          <span
            className={cn(
              "inline-block h-4 w-4 rounded-full bg-white shadow transition-transform mt-0.5",
              role.enabled ? "translate-x-4" : "translate-x-0.5",
            )}
          />
        </button>

        {/* Kebab menu */}
        <div className="relative flex-shrink-0" ref={menuRef}>
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            className="p-1 rounded-lg text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
          >
            <MoreVertical className="w-4 h-4" />
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-full mt-1 z-20 w-36 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 shadow-lg py-1">
              <button
                type="button"
                onClick={() => { setMenuOpen(false); onDuplicate(); }}
                className="w-full text-left px-3 py-1.5 text-xs text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800"
              >
                Duplicate
              </button>
              <button
                type="button"
                onClick={() => { setMenuOpen(false); onDelete(); }}
                className="w-full text-left px-3 py-1.5 text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10"
              >
                Delete
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Model picker */}
      <div className="px-4 pb-3">
        <label className="block text-[11px] font-medium text-neutral-500 dark:text-neutral-400 mb-1 uppercase tracking-wide">
          Model
        </label>
        <ModelPicker value={role.model_id} onChange={handleModelChange} />
      </div>

      {/* System prompt collapsible */}
      <div className="px-4 pb-3">
        <button
          type="button"
          onClick={() => setPromptOpen((v) => !v)}
          className="flex items-center gap-1.5 text-[11px] font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wide hover:text-neutral-700 dark:hover:text-neutral-200 transition-colors"
        >
          {promptOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          System prompt
        </button>
        {promptOpen && (
          <textarea
            rows={10}
            value={role.system_prompt}
            onChange={handlePromptChange}
            onBlur={() => onChange({ system_prompt: role.system_prompt })}
            className={cn(
              "mt-2 w-full resize-y rounded-xl px-3 py-2 text-xs font-mono",
              "bg-neutral-50 dark:bg-neutral-800",
              "border border-neutral-200 dark:border-neutral-700",
              "text-neutral-900 dark:text-white",
              "focus:outline-none focus:ring-2 focus:ring-primary-500/40 focus:border-primary-500",
            )}
            placeholder="System prompt for this role…"
          />
        )}
      </div>

      {/* Sliders */}
      <div className="grid grid-cols-2 gap-4 px-4 pb-4">
        {/* Temperature */}
        <div>
          <label className="flex items-center justify-between text-[11px] font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wide mb-1.5">
            <span>Temperature</span>
            <span className="font-mono text-neutral-700 dark:text-neutral-300">{role.temperature.toFixed(2)}</span>
          </label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={role.temperature}
            onChange={handleTemperatureChange}
            className="w-full accent-primary-500"
          />
        </div>

        {/* Max tokens */}
        <div>
          <label className="flex items-center justify-between text-[11px] font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wide mb-1.5">
            <span>Max tokens</span>
            <span className="font-mono text-neutral-700 dark:text-neutral-300">{role.max_tokens.toLocaleString()}</span>
          </label>
          <input
            type="range"
            min={256}
            max={8192}
            step={256}
            value={role.max_tokens}
            onChange={handleMaxTokensChange}
            className="w-full accent-primary-500"
          />
        </div>
      </div>
    </div>
  );
}

// Re-export helpers for use in team-panel
export { ROLE_ICONS, ROLE_COLORS, ROLE_BG };
