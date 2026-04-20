import { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { DesktopAuthProvider } from "@/lib/desktop-auth";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { AiModeProvider } from "@/contexts/ai-mode-context";
import { BackendStatusProvider } from "@/contexts/backend-status-context";
import { DesktopLayout } from "@/components/navigation/desktop-layout";
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
import SchedulePage from "@/routes/schedule";
import DistributionPage from "@/routes/distribution";
import BlueprintsPage from "@/routes/blueprints";
import WizardPage from "@/routes/wizard";
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

const isTauri = typeof window !== "undefined" && "__TAURI__" in window;

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

export default function App() {
  return (
    <SidecarGate>
      <UpdateNotifier />
      <DesktopAuthProvider>
        <ThemeProvider>
          <AiModeProvider>
          <BackendStatusProvider>
          <BrowserRouter>
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
                <Route path="/approvals" element={<ApprovalsPage />} />
                <Route path="/schedule" element={<SchedulePage />} />
                <Route path="/distribution" element={<DistributionPage />} />
                <Route path="/analytics" element={<AnalyticsPage />} />
                <Route path="/settings" element={<SettingsPage />} />
              </Route>
            </Routes>
          </BrowserRouter>
          </BackendStatusProvider>
          </AiModeProvider>
        </ThemeProvider>
      </DesktopAuthProvider>
    </SidecarGate>
  );
}
