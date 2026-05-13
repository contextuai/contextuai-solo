import { useMemo, useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import { DesktopAuthProvider } from "@/lib/desktop-auth";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { AiModeProvider } from "@/contexts/ai-mode-context";
import { BackendStatusProvider } from "@/contexts/backend-status-context";
import { ModeProvider, useMode } from "@/contexts/mode-context";
import { DesktopLayout } from "@/components/navigation/desktop-layout";
import { WindowTitle } from "@/components/shell/window-title";
import { useKeyboardShortcuts } from "@/hooks/use-keyboard-shortcuts";
import ChatPage from "@/routes/chat";
import AgentsPage from "@/routes/agents";
import CrewsPage from "@/routes/crews";
import CrewDetailPage from "@/routes/crew-detail";
import WorkspacePage from "@/routes/workspace";
import PersonasPage from "@/routes/personas";
import AnalyticsPage from "@/routes/analytics";
import ConnectionsPage from "@/routes/connections";
import ModelsPage from "@/routes/models";
import SettingsPage from "@/routes/settings";
import ApprovalsPage from "@/routes/approvals";
import BlueprintsPage from "@/routes/blueprints";
import KnowledgePage from "@/routes/knowledge";
import AutomationsPage from "@/routes/automations";
import WizardPage from "@/routes/wizard";
import CoderProjectsPage from "@/routes/coder/projects";
import CoderProjectDetailPage from "@/routes/coder/project-detail";
import CoderRunningPage from "@/routes/coder/running";
import CoderTemplatesPage from "@/routes/coder/templates";
import { UpdateNotifier } from "@/components/update-notifier";

function isWizardComplete(): boolean {
  try {
    const data = localStorage.getItem("contextuai-solo-wizard");
    if (!data) return false;
    return JSON.parse(data).completed === true;
  } catch {
    return false;
  }
}

function RequireWizard({ children }: { children: React.ReactNode }) {
  if (!isWizardComplete()) {
    return <Navigate to="/wizard" replace />;
  }
  return <>{children}</>;
}

const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

/** Updates the HTML splash screen status text. */
function updateSplash(text: string) {
  const el = document.getElementById("splash-status");
  if (el) el.textContent = text;
}

/** Hides the HTML splash screen. */
function hideSplash() {
  const el = document.getElementById("splash");
  if (el) el.style.display = "none";
}

/** Waits for the backend sidecar to be healthy before rendering children. */
function SidecarGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(!isTauri); // dev mode: no gate

  useEffect(() => {
    if (!isTauri) { hideSplash(); return; }

    let cancelled = false;
    const check = async () => {
      const url = "http://127.0.0.1:18741/health";

      for (let attempt = 0; attempt < 60; attempt++) {
        if (cancelled) return;
        try {
          const resp = await fetch(url);
          if (resp.ok) {
            hideSplash();
            setReady(true);
            return;
          }
        } catch {
          // sidecar not up yet
        }
        updateSplash(
          attempt < 5
            ? "Starting backend..."
            : `Starting backend... (${attempt}s)`
        );
        await new Promise((r) => setTimeout(r, 1000));
      }
      updateSplash("Backend failed to start. Please restart the app.");
    };

    check();
    return () => { cancelled = true; };
  }, []);

  if (ready) return <>{children}</>;
  return null; // splash screen in index.html is visible
}

/**
 * Navigates to the correct home route whenever the app mode changes.
 *
 * - solo  → "/"               (if currently on a /coder/* route)
 * - coder → "/coder/projects" (if not already on a /coder/* route)
 *
 * Effect deps are intentionally [mode] only — we do not want to re-run
 * when the user navigates freely within /coder/* routes.
 */
function ModeRedirector() {
  const { mode } = useMode();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const onCoderRoute = location.pathname.startsWith("/coder/");
    if (mode === "coder" && !onCoderRoute) {
      navigate("/coder/projects", { replace: true });
    } else if (mode === "solo" && onCoderRoute) {
      navigate("/", { replace: true });
    }
  }, [mode]); // intentionally not depending on location

  return null;
}

/** Wires the global Cmd/Ctrl+Shift+M shortcut for toggling app mode. */
function ModeShortcutHandler() {
  const { mode, setMode } = useMode();
  const bindings = useMemo(
    () => [
      {
        combo: "mod+shift+m",
        handler: () => setMode(mode === "solo" ? "coder" : "solo"),
      },
    ],
    [mode, setMode]
  );
  useKeyboardShortcuts(bindings);
  return null;
}

export default function App() {
  return (
    <SidecarGate>
      <UpdateNotifier />
      <DesktopAuthProvider>
        <ThemeProvider>
          <AiModeProvider>
          <BackendStatusProvider>
          <ModeProvider>
          <BrowserRouter>
            <WindowTitle />
            <ModeShortcutHandler />
            <ModeRedirector />
            <Routes>
              <Route path="/wizard" element={<WizardPage />} />
              <Route element={<RequireWizard><DesktopLayout /></RequireWizard>}>
                <Route path="/" element={<ChatPage />} />
                <Route path="/models" element={<ModelsPage />} />
                <Route path="/personas" element={<PersonasPage />} />
                <Route path="/agents" element={<AgentsPage />} />
                <Route path="/agents/:id" element={<AgentsPage />} />
                <Route path="/crews" element={<CrewsPage />} />
                <Route path="/crews/:id" element={<CrewDetailPage />} />
                <Route path="/blueprints" element={<BlueprintsPage />} />
                <Route path="/workspace" element={<WorkspacePage />} />
                <Route path="/workspace/:id" element={<WorkspacePage />} />
                <Route path="/connections" element={<ConnectionsPage />} />
                <Route path="/knowledge" element={<KnowledgePage />} />
                <Route path="/automations" element={<AutomationsPage />} />
                <Route path="/approvals" element={<ApprovalsPage />} />
                <Route path="/analytics" element={<AnalyticsPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                {/* Coder mode (Phase 4 PR 6 — Coder MVP). */}
                <Route path="/coder/projects" element={<CoderProjectsPage />} />
                <Route path="/coder/projects/:id" element={<CoderProjectDetailPage />} />
                <Route path="/coder/running" element={<CoderRunningPage />} />
                <Route path="/coder/templates" element={<CoderTemplatesPage />} />
              </Route>
            </Routes>
          </BrowserRouter>
          </ModeProvider>
          </BackendStatusProvider>
          </AiModeProvider>
        </ThemeProvider>
      </DesktopAuthProvider>
    </SidecarGate>
  );
}
