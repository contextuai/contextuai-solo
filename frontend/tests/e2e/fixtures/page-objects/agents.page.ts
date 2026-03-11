import { type Page, type Locator, expect } from "@playwright/test";

/**
 * Page object for the Desktop Agents (Agent Library) route ("/agents").
 *
 * The page contains:
 * - Header with agent count, refresh button, and "Create Agent" button
 * - Search input for filtering agents
 * - Role filter pills (All, Researcher, Writer, Analyst, etc.)
 * - Agent cards grid (click opens detail slide-over)
 * - AgentDetail slide-over panel
 * - AgentCreate dialog
 */
export class AgentsPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  // ── Locators ────────────────────────────────────────────────────

  /** Search input for filtering agents. */
  get searchInput(): Locator {
    return this.page.locator(
      'input[placeholder*="Search agents"]'
    );
  }

  /** All role filter pill buttons. */
  get roleFilters(): Locator {
    return this.page.locator(
      'button[class*="rounded-full"]'
    );
  }

  /** All agent cards in the grid. */
  get agentCards(): Locator {
    return this.page.locator(
      '[class*="cursor-pointer"][class*="rounded-xl"]'
    ).filter({ has: this.page.locator("h3") });
  }

  /** The "Create Agent" button. */
  get createButton(): Locator {
    return this.page.getByRole("button", { name: /create agent/i });
  }

  /** The refresh button. */
  get refreshButton(): Locator {
    return this.page.locator('button[title="Refresh"]');
  }

  /** The detail slide-over panel (appears when clicking a card). */
  get detailPanel(): Locator {
    return this.page.locator('[class*="fixed"][class*="right-0"]').or(
      this.page.locator('[class*="slide-over"]')
    );
  }

  /** Agent count text in the header. */
  get agentCountText(): Locator {
    return this.page.locator("span").filter({ hasText: /\d+ agents?/ });
  }

  /** Empty state when no agents match. */
  get emptyState(): Locator {
    return this.page.getByText(/no agents/i);
  }

  // ── Actions ─────────────────────────────────────────────────────

  /** Navigate to the agents page. */
  async goto(): Promise<void> {
    await this.page.goto("/agents");
    await this.page.waitForLoadState("networkidle");
  }

  /** Type a search query to filter agents. */
  async searchAgents(query: string): Promise<void> {
    await this.searchInput.clear();
    await this.searchInput.fill(query);
    await this.page.waitForTimeout(300);
  }

  /** Click a role filter pill. */
  async filterByRole(role: string): Promise<void> {
    await this.roleFilters.filter({ hasText: new RegExp(`^${role}`) }).click();
    await this.page.waitForTimeout(300);
  }

  /** Get all visible agent names from the cards. */
  async getAgentNames(): Promise<string[]> {
    const count = await this.agentCards.count();
    const names: string[] = [];
    for (let i = 0; i < count; i++) {
      const name = await this.agentCards.nth(i).locator("h3").textContent();
      if (name) names.push(name.trim());
    }
    return names;
  }

  /** Get the count of visible agent cards. */
  async getAgentCount(): Promise<number> {
    return this.agentCards.count();
  }

  /** Click an agent card to open the detail slide-over. */
  async openAgentDetail(name: string): Promise<void> {
    const card = this.agentCards.filter({ hasText: name }).first();
    await card.click();
    // Wait for detail panel to appear
    await this.page.waitForTimeout(500);
  }

  /**
   * Open the Create Agent dialog and fill in data.
   * The exact form fields depend on the AgentCreate component.
   */
  async createAgent(data: {
    name: string;
    role?: string;
    description?: string;
  }): Promise<void> {
    await this.createButton.click();
    await this.page.waitForTimeout(500);

    // Fill name field (first text input in the dialog)
    const nameInput = this.page.locator(
      '.fixed input[type="text"]'
    ).first();
    await nameInput.fill(data.name);

    if (data.description) {
      const descInput = this.page
        .locator(".fixed textarea, .fixed input")
        .filter({ has: this.page.locator('[placeholder*="description" i]') })
        .or(this.page.locator('.fixed textarea').first());
      if (await descInput.isVisible()) {
        await descInput.fill(data.description);
      }
    }

    // Submit the form
    const submitButton = this.page
      .locator(".fixed button")
      .filter({ hasText: /create/i });
    await submitButton.click();
    await this.page.waitForTimeout(1000);
  }
}
