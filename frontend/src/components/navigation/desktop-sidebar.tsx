import { useState, useEffect } from "react";
import { useLocation, Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import {
  MessageSquare,
  Users,
  ClipboardCheck,
  Settings,
  ChevronLeft,
  ChevronRight,
  Monitor,
  Cloud,
  Cpu,
  Library,
  Zap,
  Plug,
  Bot,
  Brain,
  Plus,
  Check,
} from "lucide-react";
import { useAiMode } from "@/contexts/ai-mode-context";
import { useEdition } from "@/config/edition";
import { useAdvancedMode } from "@/hooks/use-advanced-mode";
import { CommandPalette } from "@/components/shell/command-palette";
import { PrivacyShield } from "@/components/privacy/privacy-shield";
import { ThemeQuickPicker } from "@/components/shell/theme-quick-picker";
import vesperLogoImg from "@/assets/vesper-logo.png";

interface NavItem {
  label: string;
  path: string;
  icon: React.ElementType;
}

// Default 5-tab Vesper navigation
const coreNavItems: NavItem[] = [
  { label: "Chat", path: "/", icon: MessageSquare },
  { label: "Local Docs", path: "/knowledge", icon: Library },
  { label: "Models", path: "/models", icon: Cpu },
  { label: "Tools & MCP", path: "/personas", icon: Plug },
  { label: "Settings", path: "/settings", icon: Settings },
];

// Advanced surfaces (off by default; enabled via Settings -> Developer -> Advanced Mode)
const advancedNavItems: NavItem[] = [
  { label: "Agents", path: "/agents", icon: Bot },
  { label: "Workspace", path: "/crews", icon: Users },
  { label: "Automations", path: "/automations", icon: Zap },
  { label: "Memory", path: "/memory", icon: Brain },
  { label: "Approvals", path: "/approvals", icon: ClipboardCheck },
];

export default function DesktopSidebar() {
  const location = useLocation();
  const { aiMode, setAiMode } = useAiMode();
  const { isLite } = useEdition();
  const { advancedMode } = useAdvancedMode();
  const [collapsed, setCollapsed] = useState(() => {
    const stored = localStorage.getItem("sidebar-collapsed");
    return stored === "true";
  });

  useEffect(() => {
    localStorage.setItem("sidebar-collapsed", String(collapsed));
  }, [collapsed]);

  const isActive = (path: string) => {
    if (path === "/") return location.pathname === "/";
    return location.pathname.startsWith(path);
  };

  const renderNavLink = (item: NavItem) => {
    const Icon = item.icon;
    const active = isActive(item.path);
    return (
      <Link
        key={item.path}
        to={item.path}
        className={cn(
          "flex items-center gap-3 px-3.5 py-2.5 rounded-full text-sm transition-all duration-150",
          active
            ? "bg-primary-500/15 text-primary-700 dark:text-primary-300 font-semibold nav-active-bar"
            : "text-neutral-600 dark:text-neutral-400 font-medium hover:bg-neutral-100/80 dark:hover:bg-neutral-800/70",
          collapsed && "justify-center px-0"
        )}
        title={collapsed ? item.label : undefined}
      >
        <Icon
          className={cn(
            "w-5 h-5 flex-shrink-0",
            active
              ? "text-primary-600 dark:text-primary-400"
              : "text-neutral-500 dark:text-neutral-400"
          )}
        />
        {!collapsed && <span className="truncate">{item.label}</span>}
      </Link>
    );
  };

  return (
    <aside
      className={cn(
        "relative flex flex-col h-full border-r transition-all duration-300 ease-in-out",
        "bg-white dark:bg-neutral-900 border-neutral-200 dark:border-neutral-800",
        collapsed ? "w-[68px]" : "w-[240px]"
      )}
    >
      {/* Brand Header */}
      <div className="flex items-center h-16 px-4 border-b border-neutral-200 dark:border-neutral-800">
        <div className="flex items-center gap-3 min-w-0">
          <img
            src={vesperLogoImg}
            alt="Vesper"
            className="flex-shrink-0 w-8 h-8 rounded-lg object-cover shadow-sm ring-1 ring-primary-500/20"
          />
          {!collapsed && (
            <div className="flex flex-col min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-bold text-neutral-900 dark:text-white truncate">
                  Vesper
                </span>
                {isLite && (
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold bg-primary-500/15 text-primary-600 dark:text-primary-400 uppercase tracking-wider">
                    Lite
                  </span>
                )}
              </div>
              <span className="text-[10px] font-medium text-primary-500 uppercase tracking-wider truncate">
                {isLite ? "by ContextuAI · GGUF Engine" : "by ContextuAI · Full Solo"}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* M3 Extended FAB: Quick New Chat + Quick Jump (Ctrl+K) */}
      <div className="px-3 pt-3 pb-1 space-y-2">
        <Link
          to="/"
          onClick={() => window.dispatchEvent(new CustomEvent("contextuai:new-chat"))}
          className={cn(
            "flex items-center justify-center gap-2.5 rounded-2xl font-semibold text-sm transition-all duration-150 active:scale-[0.98]",
            "bg-primary-500/15 hover:bg-primary-500/25 text-primary-700 dark:text-primary-300",
            "border border-primary-500/25 shadow-sm",
            collapsed ? "w-11 h-11 mx-auto p-0" : "w-full px-4 py-2.5"
          )}
          title="New Chat (Ctrl+N)"
        >
          <Plus className="w-4 h-4 shrink-0" />
          {!collapsed && <span>New Chat</span>}
        </Link>
        <CommandPalette compact collapsed={collapsed} />
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-3 space-y-1 overflow-y-auto">
        {coreNavItems.map(renderNavLink)}

        {advancedMode && (
          <div className="pt-3 mt-3 border-t border-neutral-200/80 dark:border-neutral-800 space-y-1">
            {!collapsed && (
              <div className="px-3.5 pb-1 text-[10px] font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
                Advanced
              </div>
            )}
            {advancedNavItems.map(renderNavLink)}
          </div>
        )}
      </nav>

      {/* AI Mode Toggle */}
      <div
        className={cn(
          "px-3 py-3 border-t border-neutral-200 dark:border-neutral-800"
        )}
      >
        {collapsed ? (
          <button
            onClick={() => setAiMode(aiMode === "local" ? "cloud" : "local")}
            className={cn(
              "flex items-center justify-center w-full p-2 rounded-lg transition-colors",
              aiMode === "local"
                ? "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                : "bg-sky-50 dark:bg-sky-500/10 text-sky-600 dark:text-sky-400"
            )}
            title={aiMode === "local" ? "Local AI" : "Cloud AI"}
          >
            {aiMode === "local" ? (
              <Monitor className="w-4 h-4" />
            ) : (
              <Cloud className="w-4 h-4" />
            )}
          </button>
        ) : (
          <div className="flex rounded-full bg-neutral-100 dark:bg-neutral-800/90 p-1 border border-neutral-200/70 dark:border-neutral-700/70">
            <button
              onClick={() => setAiMode("local")}
              className={cn(
                "flex items-center justify-center gap-1.5 flex-1 px-2.5 py-1.5 rounded-full text-[11px] font-semibold transition-all",
                aiMode === "local"
                  ? "bg-primary-500/15 text-primary-700 dark:text-primary-300 shadow-sm"
                  : "text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300"
              )}
            >
              {aiMode === "local" ? <Check className="w-3 h-3" /> : <Monitor className="w-3 h-3" />}
              Local
            </button>
            <button
              onClick={() => setAiMode("cloud")}
              className={cn(
                "flex items-center justify-center gap-1.5 flex-1 px-2.5 py-1.5 rounded-full text-[11px] font-semibold transition-all",
                aiMode === "cloud"
                  ? "bg-sky-500/15 text-sky-700 dark:text-sky-300 shadow-sm"
                  : "text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300"
              )}
            >
              {aiMode === "cloud" ? <Check className="w-3 h-3" /> : <Cloud className="w-3 h-3" />}
              Cloud
            </button>
          </div>
        )}
      </div>

      {/* Utility Dock (PrivacyShield + ThemeQuickPicker always visible) */}
      <div
        className={cn(
          "px-3 py-2.5 border-t border-neutral-200 dark:border-neutral-800",
          collapsed ? "flex flex-col items-center gap-2" : "flex items-center justify-between gap-2"
        )}
      >
        <PrivacyShield iconOnly={collapsed} />
        <ThemeQuickPicker placement="top-left" />
      </div>

      {/* Collapse Toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className={cn(
          "absolute -right-3 top-20 z-10",
          "flex items-center justify-center w-6 h-6 rounded-full",
          "bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700",
          "text-neutral-500 dark:text-neutral-400",
          "hover:bg-neutral-50 dark:hover:bg-neutral-700",
          "shadow-sm transition-colors"
        )}
      >
        {collapsed ? (
          <ChevronRight className="w-3.5 h-3.5" />
        ) : (
          <ChevronLeft className="w-3.5 h-3.5" />
        )}
      </button>
    </aside>
  );
}
