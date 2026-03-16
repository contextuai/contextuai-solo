import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { DesktopAuthProvider } from "@/lib/desktop-auth";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { AiModeProvider } from "@/contexts/ai-mode-context";
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
import WizardPage from "@/routes/wizard";

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

export default function App() {
  return (
    <DesktopAuthProvider>
      <ThemeProvider>
        <AiModeProvider>
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
              <Route path="/workspace" element={<WorkspacePage />} />
              <Route path="/workspace/:id" element={<WorkspacePage />} />
              <Route path="/connections" element={<ConnectionsPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
        </AiModeProvider>
      </ThemeProvider>
    </DesktopAuthProvider>
  );
}
