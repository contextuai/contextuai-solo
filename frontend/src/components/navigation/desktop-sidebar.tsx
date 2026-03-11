import { useState, useEffect } from "react";
import { useLocation, Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import {
  MessageSquare,
  Sparkles,
  Bot,
  Users,
  FlaskConical,
  Cable,
  Settings,
  ChevronLeft,
  ChevronRight,
  Wifi,
  WifiOff,
} from "lucide-react";
import logoImg from "@/assets/logo.png";

interface NavItem {
  label: string;
  path: string;
  icon: React.ElementType;
}

const navItems: NavItem[] = [
  { label: "Chat", path: "/", icon: MessageSquare },
  { label: "Personas", path: "/personas", icon: Sparkles },
  { label: "Agents", path: "/agents", icon: Bot },
  { label: "Crews", path: "/crews", icon: Users },
  { label: "Workshop", path: "/workspace", icon: FlaskConical },
  { label: "Connections", path: "/connections", icon: Cable },
  { label: "Settings", path: "/settings", icon: Settings },
];

export default function DesktopSidebar() {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(() => {
    const stored = localStorage.getItem("sidebar-collapsed");
    return stored === "true";
  });
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  useEffect(() => {
    localStorage.setItem("sidebar-collapsed", String(collapsed));
  }, [collapsed]);

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  const isActive = (path: string) => {
    if (path === "/") return location.pathname === "/";
    return location.pathname.startsWith(path);
  };

  return (
    <aside
      className={cn(
        "relative flex flex-col h-screen border-r transition-all duration-300 ease-in-out",
        "bg-white dark:bg-neutral-900 border-neutral-200 dark:border-neutral-800",
        collapsed ? "w-[68px]" : "w-[240px]"
      )}
    >
      {/* Logo */}
      <div className="flex items-center h-16 px-4 border-b border-neutral-200 dark:border-neutral-800">
        <div className="flex items-center gap-3 min-w-0">
          <img src={logoImg} alt="ContextuAI" className="flex-shrink-0 w-8 h-8 rounded-lg" />
          {!collapsed && (
            <div className="flex flex-col min-w-0">
              <span className="text-sm font-bold text-neutral-900 dark:text-white truncate">
                ContextuAI
              </span>
              <span className="text-[10px] font-medium text-primary-500 uppercase tracking-wider">
                Solo
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.path);
          return (
            <Link
              key={item.path}
              to={item.path}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200",
                "hover:bg-neutral-100 dark:hover:bg-neutral-800",
                active
                  ? "bg-primary-50 dark:bg-primary-500/10 text-primary-600 dark:text-primary-400"
                  : "text-neutral-600 dark:text-neutral-400",
                collapsed && "justify-center px-0"
              )}
              title={collapsed ? item.label : undefined}
            >
              <Icon
                className={cn(
                  "w-5 h-5 flex-shrink-0",
                  active
                    ? "text-primary-500"
                    : "text-neutral-500 dark:text-neutral-400"
                )}
              />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Connection Status */}
      <div className={cn(
        "px-4 py-3 border-t border-neutral-200 dark:border-neutral-800",
        "flex items-center gap-2"
      )}>
        {isOnline ? (
          <Wifi className="w-4 h-4 text-success flex-shrink-0" />
        ) : (
          <WifiOff className="w-4 h-4 text-error flex-shrink-0" />
        )}
        {!collapsed && (
          <span className={cn(
            "text-xs font-medium",
            isOnline ? "text-success" : "text-error"
          )}>
            {isOnline ? "Connected" : "Offline"}
          </span>
        )}
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
