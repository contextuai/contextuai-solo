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
 * - CrewBuilder modal
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
    return this.page.getByRole("button", { name: /create crew/i });
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
   * Open the Create Crew modal.
   * The exact form depends on CrewBuilder component.
   */
  async createCrew(data: {
    name: string;
    description?: string;
    mode?: string;
  }): Promise<void> {
    await this.createButton.click();
    await this.page.waitForTimeout(500);

    // Fill name (first text input in the modal)
    const nameInput = this.page.locator('.fixed input[type="text"]').first();
    if (await nameInput.isVisible()) {
      await nameInput.fill(data.name);
    }

    if (data.description) {
      const descInput = this.page.locator(".fixed textarea").first();
      if (await descInput.isVisible()) {
        await descInput.fill(data.description);
      }
    }

    // Submit
    const submitButton = this.page
      .locator(".fixed button")
      .filter({ hasText: /create/i })
      .last();
    if (await submitButton.isVisible()) {
      await submitButton.click();
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
}
