/**
 * 2027 Workstation Command Palette (`Ctrl+K` / `Cmd+K`)
 *
 * Keyboard-first quick switcher for jumping to any Vesper Lite or ContextuAI Solo
 * surface, toggling Local/Cloud AI mode, switching theme, or switching editions.
 */
import { useState, useEffect, useRef, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  MessageSquare,
  Cpu,
  Library,
  Plug,
  Server,
  Settings,
  Brain,
  Bot,
  Users,
  Zap,
  ClipboardCheck,
  Cable,
  Monitor,
  Cloud,
  Sun,
  Moon,
  Sparkles,
  Feather,
  Command,
  ArrowRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useEdition } from "@/config/edition";
import { useAiMode } from "@/contexts/ai-mode-context";
import { useTheme } from "@/components/providers/theme-provider";

interface CommandItem {
  id: string;
  label: string;
  subtitle: string;
  category: "Navigation" | "Quick Actions";
  icon: React.ElementType;
  keywords?: string;
  action: () => void;
}

export function CommandPalette({
  compact = false,
  collapsed = false,
}: {
  compact?: boolean;
  collapsed?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { isLite, unlockSolo, switchToLite } = useEdition();
  const { aiMode, setAiMode } = useAiMode();
  const { resolvedTheme, setTheme } = useTheme();

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      } else if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 20);
    }
  }, [open]);

  const items = useMemo<CommandItem[]>(() => {
    const nav: CommandItem[] = [
      {
        id: "nav-chat",
        label: "Go to Chat",
        subtitle: "Local GGUF & Cloud AI chat with Folder RAG & MCP tools",
        category: "Navigation",
        icon: MessageSquare,
        keywords: "chat message prompt rag conversation",
        action: () => navigate("/"),
      },
      {
        id: "nav-models",
        label: isLite ? "Go to Model Hub" : "Go to Models",
        subtitle: "Hardware X-Ray, Fit Badges, GGUF Catalog, Benchmark & HF Search",
        category: "Navigation",
        icon: Cpu,
        keywords: "models gguf download huggingface benchmark vram gpu quant",
        action: () => navigate("/models"),
      },
      {
        id: "nav-knowledge",
        label: isLite ? "Go to Local Docs (Folder RAG)" : "Go to Knowledge Base",
        subtitle: "Index local folders & PDF/DOCX/MD files for private citations",
        category: "Navigation",
        icon: Library,
        keywords: "docs knowledge rag folder pdf embeddings local",
        action: () => navigate("/knowledge"),
      },
      {
        id: "nav-connectors",
        label: isLite ? "Go to Connectors & MCP" : "Go to Connectors",
        subtitle: "Connect MCP servers, PostgreSQL, Snowflake, Web Search & APIs",
        category: "Navigation",
        icon: Plug,
        keywords: "mcp connectors tools database postgres web api personas",
        action: () => navigate("/personas"),
      },
      {
        id: "nav-server",
        label: "Go to Local OpenAI /v1 & MCP Server",
        subtitle: "Connect Cursor, Continue.dev, Aider, Claude Code & inspect /v1 requests",
        category: "Navigation",
        icon: Server,
        keywords: "server openai v1 api cursor continue aider fim",
        action: () => navigate("/server"),
      },
      {
        id: "nav-settings",
        label: "Go to Settings",
        subtitle: "AI Providers, HuggingFace Token, Brand Voice, Appearance & Backup",
        category: "Navigation",
        icon: Settings,
        keywords: "settings api keys huggingface token theme export",
        action: () => navigate("/settings"),
      },
    ];

    if (!isLite) {
      nav.push(
        {
          id: "nav-memory",
          label: "Go to Unified Memory",
          subtitle: "Auto-recalled durable facts, review queue & memory settings",
          category: "Navigation",
          icon: Brain,
          keywords: "memory facts recall preferences",
          action: () => navigate("/memory"),
        },
        {
          id: "nav-agents",
          label: "Go to Agent Library",
          subtitle: "Browse and customize 113+ specialist prompt agents",
          category: "Navigation",
          icon: Bot,
          keywords: "agents library specialist prompt",
          action: () => navigate("/agents"),
        },
        {
          id: "nav-crews",
          label: "Go to Workspace & Crews",
          subtitle: "Multi-agent crews, projects, Dry-Run sandbox & execution history",
          category: "Navigation",
          icon: Users,
          keywords: "crews workspace projects multi-agent dry run",
          action: () => navigate("/crews"),
        },
        {
          id: "nav-automations",
          label: "Go to Automations",
          subtitle: "Scheduled and event-driven workflows",
          category: "Navigation",
          icon: Zap,
          keywords: "automations schedule cron triggers",
          action: () => navigate("/automations"),
        },
        {
          id: "nav-approvals",
          label: "Go to Approvals Queue",
          subtitle: "Human-in-the-loop review for outbound posts and actions",
          category: "Navigation",
          icon: ClipboardCheck,
          keywords: "approvals review queue outbound",
          action: () => navigate("/approvals"),
        },
        {
          id: "nav-distributions",
          label: "Go to Distributions & Channels",
          subtitle: "Telegram, Discord, Reddit, LinkedIn, X & webhook connections",
          category: "Navigation",
          icon: Cable,
          keywords: "distributions channels telegram reddit discord linkedin twitter",
          action: () => navigate("/connections"),
        }
      );
    }

    const actions: CommandItem[] = [
      {
        id: "act-ai-mode",
        label:
          aiMode === "local"
            ? "Switch AI Mode to Cloud"
            : "Switch AI Mode to Local GGUF",
        subtitle:
          aiMode === "local"
            ? "Currently running 100% Local AI — switch to Cloud providers"
            : "Currently using Cloud APIs — switch to 100% Local GGUF inference",
        category: "Quick Actions",
        icon: aiMode === "local" ? Cloud : Monitor,
        keywords: "local cloud mode switch toggle",
        action: () => setAiMode(aiMode === "local" ? "cloud" : "local"),
      },
      {
        id: "act-theme",
        label:
          resolvedTheme === "dark"
            ? "Switch to Light Theme"
            : "Switch to Dark Theme",
        subtitle: "Toggle workstation appearance",
        category: "Quick Actions",
        icon: resolvedTheme === "dark" ? Sun : Moon,
        keywords: "theme dark light appearance mode",
        action: () => setTheme(resolvedTheme === "dark" ? "light" : "dark"),
      },
      isLite
        ? {
            id: "act-edition",
            label: "Unlock Full ContextuAI Solo",
            subtitle: "Seed 113+ Agents, Multi-Agent Crews, Memory & Channels in-place",
            category: "Quick Actions",
            icon: Sparkles,
            keywords: "unlock solo upgrade agents crews edition",
            action: () => {
              void unlockSolo();
            },
          }
        : {
            id: "act-edition",
            label: "Switch to Vesper Lite Mode",
            subtitle: "Streamlined 6-tab GGUF & MCP workstation view",
            category: "Quick Actions",
            icon: Feather,
            keywords: "vesper lite edition switch minimal",
            action: () => {
              void switchToLite();
            },
          },
    ];

    return [...nav, ...actions];
  }, [isLite, aiMode, resolvedTheme, navigate, setAiMode, setTheme, unlockSolo, switchToLite]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (item) =>
        item.label.toLowerCase().includes(q) ||
        item.subtitle.toLowerCase().includes(q) ||
        (item.keywords && item.keywords.toLowerCase().includes(q))
    );
  }, [items, query]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  const executeItem = (item: CommandItem) => {
    setOpen(false);
    item.action();
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          "inline-flex items-center text-xs font-medium transition-colors border",
          "bg-neutral-100/80 dark:bg-neutral-800/80 hover:bg-neutral-200/80 dark:hover:bg-neutral-700/80",
          "border-neutral-200/80 dark:border-neutral-700/80",
          collapsed
            ? "justify-center w-10 h-9 mx-auto rounded-xl px-0"
            : compact
              ? "justify-between w-full px-3 py-1.5 rounded-xl"
              : "gap-2 px-3 py-1 rounded-full"
        )}
        title="Open Command Palette (Ctrl+K / Cmd+K)"
      >
        <span className="inline-flex items-center gap-2 min-w-0">
          <Search className="w-3.5 h-3.5 text-neutral-400 shrink-0" />
          {!collapsed && (
            <span className="text-neutral-500 dark:text-neutral-400 truncate">
              Quick Jump...
            </span>
          )}
        </span>
        {!collapsed && (
          <kbd className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-mono bg-white dark:bg-neutral-900 text-neutral-500 dark:text-neutral-400 border border-neutral-200 dark:border-neutral-700 shrink-0">
            <Command className="w-2.5 h-2.5" />K
          </kbd>
        )}
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center pt-[14vh] bg-black/50 backdrop-blur-sm p-4"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-xl rounded-2xl bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Search bar */}
            <div className="flex items-center gap-3 px-4 py-3.5 border-b border-neutral-200 dark:border-neutral-800">
              <Search className="w-4 h-4 text-primary-500 shrink-0" />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "ArrowDown") {
                    e.preventDefault();
                    setSelectedIndex((i) =>
                      filtered.length ? (i + 1) % filtered.length : 0
                    );
                  } else if (e.key === "ArrowUp") {
                    e.preventDefault();
                    setSelectedIndex((i) =>
                      filtered.length
                        ? (i - 1 + filtered.length) % filtered.length
                        : 0
                    );
                  } else if (e.key === "Enter" && filtered[selectedIndex]) {
                    e.preventDefault();
                    executeItem(filtered[selectedIndex]);
                  }
                }}
                placeholder="Jump to surface, search models, toggle Local/Cloud, or switch edition..."
                className="flex-1 bg-transparent text-sm text-neutral-900 dark:text-white placeholder:text-neutral-400 focus:outline-none"
              />
              <kbd className="px-1.5 py-0.5 text-[10px] font-mono rounded bg-neutral-100 dark:bg-neutral-800 text-neutral-500">
                ESC
              </kbd>
            </div>

            {/* Results */}
            <div className="max-h-80 overflow-y-auto p-2 space-y-1">
              {filtered.length === 0 ? (
                <div className="py-8 text-center text-xs text-neutral-500">
                  No matching commands found.
                </div>
              ) : (
                filtered.map((item, idx) => {
                  const Icon = item.icon;
                  const active = idx === selectedIndex;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onMouseEnter={() => setSelectedIndex(idx)}
                      onClick={() => executeItem(item)}
                      className={cn(
                        "w-full flex items-center justify-between gap-3 px-3 py-2.5 rounded-xl text-left transition-colors",
                        active
                          ? "bg-primary-50 dark:bg-primary-500/15 text-primary-700 dark:text-primary-300"
                          : "text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800"
                      )}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div
                          className={cn(
                            "p-2 rounded-lg shrink-0",
                            active
                              ? "bg-primary-500 text-white"
                              : "bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400"
                          )}
                        >
                          <Icon className="w-4 h-4" />
                        </div>
                        <div className="min-w-0">
                          <div className="text-xs font-semibold truncate">
                            {item.label}
                          </div>
                          <div className="text-[11px] text-neutral-500 dark:text-neutral-400 truncate">
                            {item.subtitle}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-neutral-100 dark:bg-neutral-800 text-neutral-500">
                          {item.category}
                        </span>
                        <ArrowRight
                          className={cn(
                            "w-3.5 h-3.5 transition-transform",
                            active
                              ? "text-primary-500 translate-x-0.5"
                              : "text-neutral-400 opacity-0"
                          )}
                        />
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
