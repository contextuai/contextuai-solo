import { type Page, type Locator } from "@playwright/test";

const API = "http://127.0.0.1:18741/api/v1";
const TEST_PROJECT_DIR = `${process.env.USERPROFILE ?? process.env.HOME ?? "~"}/.contextuai-solo/test-projects`;

/**
 * Page object for the Coder Project Detail route ("/coder/projects/:id").
 *
 * Covers the Team tab introduced in PR 16:
 * - Workflow mode segmented control
 * - Preset apply dialog
 * - Role cards
 * - Add role dialog
 */
export class CoderProjectPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  // ── Navigation ─────────────────────────────────────────────────────────────

  async goto(projectId: string): Promise<void> {
    await this.page.goto(`/coder/projects/${projectId}`);
    await this.page.waitForLoadState("networkidle");
    await this.page.waitForTimeout(500);
  }

  // ── Tabs ───────────────────────────────────────────────────────────────────

  get terminalTab(): Locator {
    return this.page.locator('[data-testid="tab-terminal"]');
  }

  get teamTab(): Locator {
    return this.page.locator('[data-testid="tab-team"]');
  }

  async openTeamTab(): Promise<void> {
    await this.teamTab.click();
    await this.page.waitForTimeout(400);
  }

  // ── Workflow mode ──────────────────────────────────────────────────────────

  workflowModeButton(mode: "solo" | "sequential" | "parallel" | "custom"): Locator {
    return this.page.locator(`[data-testid="workflow-mode-${mode}"]`);
  }

  async selectWorkflowMode(mode: "solo" | "sequential" | "parallel" | "custom"): Promise<void> {
    await this.workflowModeButton(mode).click();
    await this.page.waitForTimeout(300);
  }

  // ── Presets ────────────────────────────────────────────────────────────────

  get applyPresetButton(): Locator {
    return this.page.getByRole("button", { name: /apply preset/i });
  }

  get presetDialog(): Locator {
    return this.page.locator(".fixed.inset-0.z-50");
  }

  presetOption(namePattern: RegExp | string): Locator {
    return this.presetDialog.locator("button").filter({ hasText: namePattern });
  }

  async openPresetDialog(): Promise<void> {
    await this.applyPresetButton.click();
    await this.presetDialog.waitFor({ state: "visible", timeout: 5000 });
    await this.page.waitForTimeout(300);
  }

  // ── Roles ──────────────────────────────────────────────────────────────────

  /** All visible role cards inside the Team panel. */
  get roleCards(): Locator {
    return this.page.locator("[draggable='true']");
  }

  get addRoleButton(): Locator {
    return this.page.getByRole("button", { name: /add role/i });
  }

  get addRoleDialog(): Locator {
    return this.page.locator(".fixed.inset-0.z-50");
  }

  roleEnabledToggle(index: number): Locator {
    return this.roleCards.nth(index).locator("button[role='switch']");
  }

  // ── API helpers ────────────────────────────────────────────────────────────

  /**
   * Create a temporary coder project via the API.
   * Returns the project_id.
   */
  async createTestProject(name?: string): Promise<string> {
    const projectName = name ?? `Test Project ${Date.now()}`;
    const resp = await this.page.request.post(`${API}/coder/projects`, {
      data: {
        name: projectName,
        folder_path: `${TEST_PROJECT_DIR}/${projectName.replace(/\s+/g, "-")}`,
        runtime: "auto",
      },
    });
    const data = await resp.json() as { project_id?: string; id?: string };
    const projectId = data.project_id ?? data.id;
    if (!projectId) throw new Error("Failed to create test project");
    return projectId;
  }

  /** Delete a project by id via API. */
  async deleteProject(projectId: string): Promise<void> {
    await this.page.request.delete(`${API}/coder/projects/${projectId}`).catch(() => {
      // best-effort cleanup
    });
  }

  /** Apply a preset via API directly. */
  async applyPresetViaApi(projectId: string, presetId: string): Promise<void> {
    await this.page.request.post(`${API}/coder/projects/${projectId}/roles/apply-preset`, {
      data: { preset_id: presetId },
    });
  }

  /** Get the workflow mode via API. */
  async getWorkflowModeViaApi(projectId: string): Promise<string> {
    const resp = await this.page.request.get(`${API}/coder/projects/${projectId}/workflow`);
    const data = await resp.json() as { workflow_mode: string };
    return data.workflow_mode;
  }

  /** Get roles via API. */
  async getRolesViaApi(projectId: string): Promise<unknown[]> {
    const resp = await this.page.request.get(`${API}/coder/projects/${projectId}/roles`);
    const data = await resp.json() as unknown[];
    return Array.isArray(data) ? data : [];
  }
}
