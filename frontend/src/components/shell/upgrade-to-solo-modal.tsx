/**
 * SPEC-33 (PR 2.2): Seamless "Graduate to ContextuAI Solo" In-App Unlock Modal
 *
 * Shows what unlocks when upgrading from Vesper Lite to full ContextuAI Solo
 * (113+ Business Agents, Multi-Agent Crews, 10 Social Channels, Approvals Queue,
 * Coder Mode, Unified Memory) and reassures the user that all downloaded GGUF
 * models, chats, and indexed folders remain in `~/.contextuai-solo/` with zero
 * re-downloading or migration.
 */
import { useState } from "react";
import {
  Sparkles,
  Bot,
  Users,
  Cable,
  Brain,
  Code2,
  ClipboardCheck,
  HardDrive,
  CheckCircle2,
  Loader2,
  ArrowRight,
} from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { unlockSoloEdition, type UnlockSoloResponse } from "@/config/edition";

interface UpgradeToSoloModalProps {
  open: boolean;
  onClose: () => void;
  onUnlocked?: (res: UnlockSoloResponse) => void;
}

const SOLO_FEATURES = [
  {
    icon: Bot,
    title: "113+ Specialist Agents",
    desc: "Pre-built prompt & tool agents across Marketing, Engineering, Finance, Legal, and Ops.",
    color: "text-primary-500 bg-primary-500/10",
  },
  {
    icon: Users,
    title: "Multi-Agent Crews & Dry-Run",
    desc: "Sequential, parallel, pipeline, and autonomous agent teams with sandboxed Dry-Run previews.",
    color: "text-purple-500 bg-purple-500/10",
  },
  {
    icon: Brain,
    title: "Unified Auto-Recall Memory",
    desc: "Durable semantic memory that remembers your preferences, pricing, and context across chats & crews.",
    color: "text-emerald-500 bg-emerald-500/10",
  },
  {
    icon: Cable,
    title: "10 Distribution Channels",
    desc: "Inbound & outbound bindings for Telegram, Discord, Reddit, LinkedIn, X, Slack, and Email.",
    color: "text-sky-500 bg-sky-500/10",
  },
  {
    icon: ClipboardCheck,
    title: "Human-in-the-Loop Approvals",
    desc: "Review, edit, or reject outbound social posts and agent actions before anything goes live.",
    color: "text-amber-500 bg-amber-500/10",
  },
  {
    icon: Code2,
    title: "Autonomous Coder Workspace",
    desc: "Dedicated multi-role software engineering workspace that can also run as a step inside Crews.",
    color: "text-rose-500 bg-rose-500/10",
  },
];

export function UpgradeToSoloModal({
  open,
  onClose,
  onUnlocked,
}: UpgradeToSoloModalProps) {
  const [unlocking, setUnlocking] = useState(false);
  const [result, setResult] = useState<UnlockSoloResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleUnlock = async () => {
    setUnlocking(true);
    setError(null);
    try {
      const res = await unlockSoloEdition();
      setResult(res);
      onUnlocked?.(res);
      setTimeout(() => {
        onClose();
        setResult(null);
      }, 900);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to unlock ContextuAI Solo"
      );
    } finally {
      setUnlocking(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={() => !unlocking && onClose()}
      title="Graduate to ContextuAI Solo"
      className="max-w-2xl"
      actions={
        <div className="flex items-center justify-between w-full">
          <span className="text-[11px] text-neutral-500 dark:text-neutral-400">
            You can switch back to Vesper Lite anytime in 1 click.
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={unlocking}
              onClick={onClose}
              className="px-3.5 py-2 rounded-lg text-xs font-medium text-neutral-600 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
            >
              Stay in Vesper Lite
            </button>
            <button
              type="button"
              disabled={unlocking}
              onClick={handleUnlock}
              data-testid="confirm-unlock-solo"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold text-white bg-gradient-to-r from-primary-600 to-emerald-600 hover:from-primary-500 hover:to-emerald-500 shadow-sm transition-all disabled:opacity-60"
            >
              {unlocking ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Seeding Agent Library...
                </>
              ) : result ? (
                <>
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Unlocked! ({result.agents_seeded} Agents Ready)
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" />
                  Switch to ContextuAI Solo
                  <ArrowRight className="w-3.5 h-3.5" />
                </>
              )}
            </button>
          </div>
        </div>
      }
    >
      <div className="space-y-4">
        {/* Hero Subheader */}
        <div className="p-4 rounded-xl bg-gradient-to-r from-primary-500/15 via-primary-500/5 to-primary-400/15 border border-primary-500/20">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-xl bg-primary-500 text-white shrink-0">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-neutral-900 dark:text-white">
                Turn your local GGUF engine into a full autonomous AI workforce
              </h3>
              <p className="text-xs text-neutral-600 dark:text-neutral-300 mt-1 leading-relaxed">
                Vesper Lite and ContextuAI Solo share the exact same native Rust + FastAPI runtime. Unlocking Solo expands the navigation from 6 core GGUF tools to the full 12-surface autonomous workstation—instantly in-place.
              </p>
            </div>
          </div>
        </div>

        {/* Feature Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {SOLO_FEATURES.map((feat) => {
            const Icon = feat.icon;
            return (
              <div
                key={feat.title}
                className="flex items-start gap-3 p-3 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50/70 dark:bg-neutral-800/40"
              >
                <div className={`p-2 rounded-lg shrink-0 ${feat.color}`}>
                  <Icon className="w-4 h-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-neutral-900 dark:text-white">
                    {feat.title}
                  </div>
                  <p className="text-[11px] text-neutral-500 dark:text-neutral-400 mt-0.5 leading-snug">
                    {feat.desc}
                  </p>
                </div>
              </div>
            );
          })}
        </div>

        {/* Zero-Friction Storage Guarantee */}
        <div className="flex items-center gap-3 p-3 rounded-xl border border-emerald-200 dark:border-emerald-900/50 bg-emerald-50/60 dark:bg-emerald-950/20 text-xs text-emerald-800 dark:text-emerald-300">
          <HardDrive className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
          <span>
            <strong>Zero Re-Downloading:</strong> All your downloaded{" "}
            <code className="font-mono text-[11px]">.gguf</code> models, chat sessions, MCP connectors, and indexed local folders in{" "}
            <code className="font-mono text-[11px]">~/.contextuai-solo/</code> stay right where they are.
          </span>
        </div>

        {error && (
          <div className="p-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-xs text-red-600 dark:text-red-400">
            {error}
          </div>
        )}
      </div>
    </Dialog>
  );
}
