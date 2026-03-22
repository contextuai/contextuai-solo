import { type Page, type Locator, expect } from "@playwright/test";

/**
 * Page object for the Desktop Crews route ("/crews").
 *
 * The page contains:
 * - Header with crew/run counts, refresh button, and "Create Crew" button
 * - Stats cards (Total Crews, Running, Completed, Failed)
 * - Search input
 * - Tabs: Crews | Runs
 * - Status filter and mode filter selects (crews tab only)
 * - Crew cards with Run buttons
 * - CrewBuilder wizard (4-step):
 *   Step 1: Crew Details (name, description)
 *   Step 2: Execution Mode
 *   Step 3: Agent Team
 *   Step 4: Review & Create
 */
export class CrewsPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  // ── Locators ────────────────────────────────────────────────────

  /** The "Crews" tab button. */
  get crewsTab(): Locator {
    return this.page.locator("button").filter({ hasText: /Crews \(/ });
  }

  /** The "Runs" tab button. */
  get runsTab(): Locator {
    return this.page.locator("button").filter({ hasText: /Runs \(/ });
  }

  /** The "Create Crew" button. */
  get createButton(): Locator {
    return this.page.getByRole("button", { name: /create crew/i }).first();
  }

  /** Search input. */
  get searchInput(): Locator {
    return this.page.locator('input[placeholder*="Search"]');
  }

  /** All crew cards in the crews list. */
  get crewCards(): Locator {
    return this.page
      .locator("[class*='rounded-xl'][class*='cursor-pointer']")
      .filter({
        has: this.page.locator("h3, [class*='font-medium']"),
      });
  }

  /** Run buttons on crew cards. */
  get runButtons(): Locator {
    return this.page.locator('button[title="Run now"]');
  }

  /** Refresh button. */
  get refreshButton(): Locator {
    return this.page.locator('button[title="Refresh"]');
  }

  /** Status filter select dropdown. */
  get statusFilter(): Locator {
    return this.page.locator("select").filter({ hasText: /all statuses/i });
  }

  /** Mode filter select dropdown. */
  get modeFilter(): Locator {
    return this.page.locator("select").filter({ hasText: /all modes/i });
  }

  /** Empty state for crews. */
  get emptyCrewsState(): Locator {
    return this.page.getByText(/no crews yet/i);
  }

  /** Empty state for runs. */
  get emptyRunsState(): Locator {
    return this.page.getByText(/no runs yet/i);
  }

  /** Loading spinner. */
  get loadingSpinner(): Locator {
    return this.page.locator("svg.lucide-loader-2.animate-spin");
  }

  // ── Wizard Dialog Locators ─────────────────────────────────────

  /** The wizard dialog overlay. */
  get builderDialog(): Locator {
    return this.page.locator(".fixed.inset-0.z-50");
  }

  /** Crew name input (step 1). */
  get crewNameInput(): Locator {
    return this.builderDialog.locator('input[placeholder="e.g., Research & Analysis Team"]');
  }

  /** Crew description textarea (step 1). */
  get crewDescriptionInput(): Locator {
    return this.builderDialog.locator('textarea[placeholder="What does this crew do?"]');
  }

  /** Next button in the wizard. */
  get nextButton(): Locator {
    return this.builderDialog.getByRole("button", { name: /next/i });
  }

  /** Back button in the wizard. */
  get backButton(): Locator {
    return this.builderDialog.getByRole("button", { name: /back/i });
  }

  /** Create Crew submit button (step 4). */
  get submitButton(): Locator {
    return this.builderDialog.getByRole("button", { name: /create crew|save changes/i });
  }

  /** Step indicator dots. */
  get stepIndicators(): Locator {
    return this.builderDialog.locator(".rounded-full.w-7.h-7");
  }

  /** "Browse Library" button inside the crew builder (step 3). */
  get browseLibraryButton(): Locator {
    return this.builderDialog.getByRole("button", { name: /browse library/i });
  }

  /** The library panel overlay (appears inside the builder dialog). */
  get libraryPanel(): Locator {
    return this.builderDialog.locator(".absolute.inset-0.z-10");
  }

  /** "Agent Library" heading inside the library panel. */
  get libraryPanelHeading(): Locator {
    return this.libraryPanel.locator("h3", { hasText: "Agent Library" });
  }

  /** Search input inside the library panel. */
  get librarySearchInput(): Locator {
    return this.libraryPanel.locator('input[placeholder="Search agents..."]');
  }

  /** Agent rows (buttons) inside the library panel list. */
  get libraryAgentRows(): Locator {
    return this.libraryPanel.locator(".overflow-y-auto button.w-full");
  }

  /** Close button for the library panel. */
  get libraryCloseButton(): Locator {
    return this.libraryPanel.locator("button").filter({ has: this.page.locator("svg.lucide-x") });
  }

  /** Category filter dropdown inside the library panel. */
  get libraryCategoryFilter(): Locator {
    return this.libraryPanel.locator("select");
  }

  // ── Actions ─────────────────────────────────────────────────────

  /** Navigate to the crews page. */
  async goto(): Promise<void> {
    await this.page.goto("/crews");
    await this.page.waitForLoadState("networkidle");
  }

  /** Switch between Crews and Runs tabs. */
  async switchTab(tab: "crews" | "runs"): Promise<void> {
    if (tab === "crews") {
      await this.crewsTab.click();
    } else {
      await this.runsTab.click();
    }
    await this.page.waitForTimeout(300);
  }

  /**
   * Open the wizard and create a crew through all steps.
   */
  async createCrew(data: {
    name: string;
    description?: string;
    mode?: string;
  }): Promise<void> {
    await this.createButton.click();
    await this.page.waitForTimeout(500);

    // Step 1: Fill crew details
    await this.crewNameInput.fill(data.name);
    if (data.description) {
      await this.crewDescriptionInput.fill(data.description);
    }

    // Next → Step 2 (Execution Mode)
    await this.nextButton.click();
    await this.page.waitForTimeout(300);

    // Next → Step 3 (Agents)
    await this.nextButton.click();
    await this.page.waitForTimeout(300);

    // Next → Step 4 (Review)
    await this.nextButton.click();
    await this.page.waitForTimeout(300);

    // Submit
    const submitBtn = this.builderDialog
      .getByRole("button", { name: /create crew/i });
    if (await submitBtn.isVisible()) {
      await submitBtn.click();
    }

    await this.page.waitForTimeout(1000);
  }

  /** Search crews by query. */
  async searchCrews(query: string): Promise<void> {
    await this.searchInput.clear();
    await this.searchInput.fill(query);
    await this.page.waitForTimeout(300);
  }

  /** Get the count of visible crew cards. */
  async getCrewCount(): Promise<number> {
    return this.crewCards.count();
  }

  /** Click the Run button on a crew card by index. */
  async runCrew(index: number): Promise<void> {
    await this.runButtons.nth(index).click();
    await this.page.waitForTimeout(500);
  }

  /** Open the crew builder wizard by clicking "Create Crew". */
  async openBuilder(): Promise<void> {
    await this.createButton.click();
    await this.builderDialog.waitFor({ state: "visible", timeout: 5000 });
    await this.page.waitForTimeout(300);
  }

  /** Navigate to a specific wizard step (from step 1). */
  async goToStep(targetStep: number): Promise<void> {
    for (let i = 1; i < targetStep; i++) {
      // Fill required fields if on step 1
      if (i === 1) {
        const nameValue = await this.crewNameInput.inputValue();
        if (!nameValue) {
          await this.crewNameInput.fill("Temp Crew");
        }
      }
      await this.nextButton.click();
      await this.page.waitForTimeout(300);
    }
  }

  /** Open the library panel from within the crew builder dialog (must be on step 3). */
  async openLibraryPanel(): Promise<void> {
    await this.browseLibraryButton.click();
    await this.libraryPanel.waitFor({ state: "visible", timeout: 5000 });
    await this.page.waitForTimeout(500);
  }

  /** Search for agents in the library panel. */
  async searchLibraryAgents(query: string): Promise<void> {
    await this.librarySearchInput.clear();
    await this.librarySearchInput.fill(query);
    await this.page.waitForTimeout(600);
  }

  /** Click a library agent row by index. */
  async selectLibraryAgent(index: number): Promise<void> {
    await this.libraryAgentRows.nth(index).click();
    await this.page.waitForTimeout(300);
  }

  /** Get all agent name inputs in step 3 of the wizard. */
  get agentNameInputs(): Locator {
    return this.builderDialog.locator(
      'input[placeholder="e.g., Researcher"]'
    );
  }

  /** Get all agent instruction textareas in step 3 of the wizard. */
  get agentInstructionTextareas(): Locator {
    return this.builderDialog.locator(
      'textarea[placeholder*="What should this agent do"]'
    );
  }
}
