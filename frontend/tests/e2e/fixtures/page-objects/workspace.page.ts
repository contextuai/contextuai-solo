import { type Page, type Locator, expect } from "@playwright/test";

/**
 * Page object for the Desktop Workspace (Workshop) route ("/workspace").
 *
 * The page contains:
 * - Header with "New Brainstorm" button
 * - Status filter pills: All, Draft, Running, Completed, Failed
 * - Refresh button
 * - Project cards list (click navigates to /workspace/:id)
 * - NewProjectDialog wizard (3-step):
 *   Step 1: Project Details (name, type, description + blueprint)
 *   Step 2: Select Agents (with search)
 *   Step 3: Review & Create
 */
export class WorkspacePage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  // ── Locators ────────────────────────────────────────────────────

  /** The "New Brainstorm" button (header — always visible). */
  get newProjectButton(): Locator {
    return this.page.getByRole("button", { name: /new brainstorm/i }).first();
  }

  /** All status filter pill buttons. */
  get statusFilters(): Locator {
    return this.page.locator("button").filter({
      hasText: /^(All|Draft|Running|Completed|Failed)$/,
    });
  }

  /** All project cards in the list. */
  get projectCards(): Locator {
    return this.page.locator("[class*='rounded-xl'][class*='cursor-pointer']").or(
      this.page.locator("[class*='rounded-xl'][class*='border']").filter({
        has: this.page.locator("h3, [class*='font-medium']"),
      })
    );
  }

  /** The refresh button. */
  get refreshButton(): Locator {
    return this.page.locator('button[title="Refresh"]');
  }

  /** Empty state when no projects exist. */
  get emptyState(): Locator {
    return this.page.getByText(/start your first workshop/i);
  }

  /** Project count text at the bottom of the list. */
  get projectCountText(): Locator {
    return this.page.locator("p").filter({ hasText: /\d+ projects?/ });
  }

  /** Loading spinner. */
  get loadingSpinner(): Locator {
    return this.page.locator("svg.animate-spin");
  }

  // ── Wizard Dialog Locators ─────────────────────────────────────

  /** The wizard dialog overlay. */
  get wizardDialog(): Locator {
    return this.page.locator(".fixed.inset-0.z-50");
  }

  /** Project name input (step 1). */
  get projectNameInput(): Locator {
    return this.wizardDialog.locator('input[placeholder="e.g. Q1 Market Analysis"]');
  }

  /** Project type select (step 1). */
  get projectTypeSelect(): Locator {
    return this.wizardDialog.locator("select");
  }

  /** Description textarea (step 1). */
  get descriptionInput(): Locator {
    return this.wizardDialog.locator("textarea");
  }

  /** "Use Blueprint" button (step 1). */
  get useBlueprintButton(): Locator {
    return this.wizardDialog.getByRole("button", { name: /use blueprint/i });
  }

  /** Agent search input (step 2). */
  get agentSearchInput(): Locator {
    return this.wizardDialog.locator('input[placeholder*="Search agents"]');
  }

  /** Agent checkbox items (step 2). */
  get agentItems(): Locator {
    return this.wizardDialog.locator("label").filter({
      has: this.page.locator("input[type='checkbox']"),
    });
  }

  /** Next button in the wizard. */
  get nextButton(): Locator {
    return this.wizardDialog.getByRole("button", { name: /next/i });
  }

  /** Back button in the wizard. */
  get backButton(): Locator {
    return this.wizardDialog.getByRole("button", { name: /back/i });
  }

  /** Cancel button in the wizard. */
  get cancelButton(): Locator {
    return this.wizardDialog.getByRole("button", { name: /cancel/i });
  }

  /** "Create & Run" submit button (step 3). */
  get submitButton(): Locator {
    return this.wizardDialog.getByRole("button", { name: /create & run/i });
  }

  /** Step indicator dots. */
  get stepIndicators(): Locator {
    return this.wizardDialog.locator(".rounded-full.w-7.h-7");
  }

  // ── Actions ─────────────────────────────────────────────────────

  /** Navigate to the workspace page. */
  async goto(): Promise<void> {
    await this.page.goto("/workspace");
    await this.page.waitForLoadState("networkidle");
  }

  /** Open the wizard by clicking "New Brainstorm". */
  async openWizard(): Promise<void> {
    await this.newProjectButton.click();
    await this.wizardDialog.waitFor({ state: "visible", timeout: 5000 });
    await this.page.waitForTimeout(300);
  }

  /** Navigate to a specific wizard step (from step 1). Fills required fields automatically. */
  async goToStep(targetStep: number): Promise<void> {
    for (let i = 1; i < targetStep; i++) {
      // Step 1 requires a name
      if (i === 1) {
        const nameValue = await this.projectNameInput.inputValue();
        if (!nameValue) {
          await this.projectNameInput.fill("Temp Project");
        }
      }
      // Step 2 requires at least one agent selected
      if (i === 2) {
        const agentCount = await this.agentItems.count();
        if (agentCount > 0) {
          // Check if any agent is already selected
          const firstAgent = this.agentItems.first();
          const isChecked = await firstAgent
            .locator("input[type='checkbox']")
            .isChecked();
          if (!isChecked) {
            await firstAgent.click();
            await this.page.waitForTimeout(200);
          }
        }
      }
      await this.nextButton.click();
      await this.page.waitForTimeout(300);
    }
  }

  /**
   * Create a project through the full wizard flow.
   */
  async createProject(data: {
    name?: string;
    description?: string;
  }): Promise<void> {
    await this.openWizard();

    // Step 1: Fill details
    if (data.name) {
      await this.projectNameInput.fill(data.name);
    }
    if (data.description) {
      await this.descriptionInput.fill(data.description);
    }

    // Next → Step 2 (Agents)
    await this.nextButton.click();
    await this.page.waitForTimeout(300);

    // Select first agent
    const agentCount = await this.agentItems.count();
    if (agentCount > 0) {
      await this.agentItems.first().click();
      await this.page.waitForTimeout(200);
    }

    // Next → Step 3 (Review)
    await this.nextButton.click();
    await this.page.waitForTimeout(300);

    // Submit
    if (await this.submitButton.isVisible()) {
      await this.submitButton.click();
    }

    await this.page.waitForTimeout(1000);
  }

  /** Search agents on step 2. */
  async searchAgents(query: string): Promise<void> {
    await this.agentSearchInput.clear();
    await this.agentSearchInput.fill(query);
    await this.page.waitForTimeout(300);
  }

  /** Click a status filter pill. */
  async filterByStatus(status: string): Promise<void> {
    await this.statusFilters
      .filter({ hasText: new RegExp(`^${status}$`, "i") })
      .click();
    await this.page.waitForTimeout(500);
  }

  /** Get the number of visible project cards. */
  async getProjectCount(): Promise<number> {
    await this.page.waitForTimeout(500);
    return this.projectCards.count();
  }

  /** Click a project card by index to navigate to its detail view. */
  async openProject(index: number): Promise<void> {
    await this.projectCards.nth(index).click();
    await this.page.waitForURL(/\/workspace\/.+/, { timeout: 10_000 });
  }
}
