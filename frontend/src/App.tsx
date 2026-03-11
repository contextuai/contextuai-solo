import { BrowserRouter, Routes, Route } from "react-router-dom";
import { DesktopAuthProvider } from "@/lib/desktop-auth";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { DesktopLayout } from "@/components/navigation/desktop-layout";
import ChatPage from "@/routes/chat";
import AgentsPage from "@/routes/agents";
import CrewsPage from "@/routes/crews";
import CrewDetailPage from "@/routes/crew-detail";
import WorkspacePage from "@/routes/workspace";
import PersonasPage from "@/routes/personas";
import AnalyticsPage from "@/routes/analytics";
import ConnectionsPage from "@/routes/connections";
import SettingsPage from "@/routes/settings";
import WizardPage from "@/routes/wizard";

export default function App() {
  return (
    <DesktopAuthProvider>
      <ThemeProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/wizard" element={<WizardPage />} />
            <Route element={<DesktopLayout />}>
              <Route path="/" element={<ChatPage />} />
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
      </ThemeProvider>
    </DesktopAuthProvider>
  );
}
