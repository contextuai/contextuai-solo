import { useState } from "react";
import { ChevronDown, ChevronUp, Settings2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Switch } from "@/components/ui/switch";
import type { MemorySettings } from "@/lib/api/memory-client";

function SettingRow({
  label,
  description,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium text-neutral-900 dark:text-white">
          {label}
        </p>
        <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
          {description}
        </p>
      </div>
      <Switch checked={checked} onChange={onChange} disabled={disabled} size="sm" />
    </div>
  );
}

export function MemorySettingsCard({
  settings,
  onUpdate,
}: {
  settings: MemorySettings;
  onUpdate: (patch: Partial<MemorySettings>) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <span className="flex items-center gap-2 text-sm font-medium text-neutral-900 dark:text-white">
          <Settings2 className="w-4 h-4 text-neutral-400" />
          Where memory applies
        </span>
        {expanded ? (
          <ChevronUp className="w-4 h-4 text-neutral-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-neutral-400" />
        )}
      </button>
      <div
        className={cn(
          "px-4 divide-y divide-neutral-100 dark:divide-neutral-800 border-t border-neutral-200 dark:border-neutral-800",
          expanded ? "block" : "hidden",
        )}
      >
        <SettingRow
          label="Chat"
          description="Recall relevant facts while chatting and (later) learn new ones from conversations."
          checked={settings.chat_enabled}
          onChange={(v) => onUpdate({ chat_enabled: v })}
          disabled={!settings.enabled}
        />
        <SettingRow
          label="Crews"
          description="Share memory with multi-agent crew runs."
          checked={settings.crews_enabled}
          onChange={(v) => onUpdate({ crews_enabled: v })}
          disabled={!settings.enabled}
        />
        <SettingRow
          label="Channels"
          description="Off by default — records facts from third-party messages (Telegram, Discord, Reddit, etc.)."
          checked={settings.channels_enabled}
          onChange={(v) => onUpdate({ channels_enabled: v })}
          disabled={!settings.enabled}
        />
      </div>
    </div>
  );
}
