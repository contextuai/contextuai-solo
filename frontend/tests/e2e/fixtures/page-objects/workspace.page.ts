import { type Page, type Locator, expect } from "@playwright/test";

/**
 * Page object for the Desktop Workspace (Workshop) route ("/workspace").
 *
 * The page contains:
 * - Header with "New Brainstorm" button
 * - Status filter pills: All, Draft, Running, Completed, Failed
 * - Refresh button
 * - Project cards list (click navigates to /workspace/:id)
 * - NewProjectDialog modal
 */
export class WorkspacePage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  // ── Locators ────────────────────────────────────────────────────

  /** The "New Brainstorm" button. */
  get newProjectButton(): Locator {
    return this.page.getByRole("button", { name: /new brainstorm/i });
  }

  /** All status filter pill buttons. */
  get statusFilters(): Locator {
    return this.page.locator("button").filter({
      hasText: /^(All|Draft|Running|Completed|Failed)$/,
    });
  }

  /** All project cards in the list. */
  get projectCards(): Locator {
    // ProjectCard components are clickable divs in the project list
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

  // ── Actions ─────────────────────────────────────────────────────

  /** Navigate to the workspace page. */
  async goto(): Promise<void> {
    await this.page.goto("/workspace");
    await this.page.waitForLoadState("networkidle");
  }

  /**
   * Open the New Project dialog and fill in data.
   * The exact form depends on NewProjectDialog component.
   */
  async createProject(data: {
    name?: string;
    description?: string;
    template?: string;
  }): Promise<void> {
    await this.newProjectButton.click();
    await this.page.waitForTimeout(500);

    if (data.name) {
      const nameInput = this.page.locator('.fixed input[type="text"]').first();
      if (await nameInput.isVisible()) {
        await nameInput.fill(data.name);
      }
    }

    if (data.description) {
      const descInput = this.page.locator(".fixed textarea").first();
      if (await descInput.isVisible()) {
        await descInput.fill(data.description);
      }
    }

    // Submit - look for a primary action button in the dialog
    const submitButton = this.page
      .locator(".fixed button")
      .filter({ hasText: /create|start|launch/i })
      .first();
    if (await submitButton.isVisible()) {
      await submitButton.click();
    }

    await this.page.waitForTimeout(1000);
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
    // Wait for navigation
    await this.page.waitForURL(/\/workspace\/.+/, { timeout: 10_000 });
  }
}
