import { type Page, type Locator } from "@playwright/test";

/**
 * Page object for the Desktop Blueprints route ("/blueprints").
 *
 * The page contains:
 * - Header with "Create Blueprint" button
 * - Search input and category/source filters
 * - Blueprint card grid
 * - Preview modal
 * - Create Blueprint dialog
 */
export class BlueprintsPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  // ── Locators ────────────────────────────────────────────────────

  /** Page heading. */
  get heading(): Locator {
    return this.page.locator("h1", { hasText: "Blueprints" });
  }

  /** The "Create Blueprint" button in the header. */
  get createButton(): Locator {
    return this.page.getByRole("button", { name: /create blueprint/i }).first();
  }

  /** Refresh button. */
  get refreshButton(): Locator {
    return this.page.locator('button[title="Refresh"]');
  }

  /** Search input. */
  get searchInput(): Locator {
    return this.page.locator('input[placeholder*="Search blueprints"]');
  }

  /** Category filter dropdown. */
  get categoryFilter(): Locator {
    return this.page.locator("select").filter({ hasText: /all categories/i });
  }

  /** Source filter dropdown. */
  get sourceFilter(): Locator {
    return this.page.locator("select").filter({ hasText: /all sources/i });
  }

  /** All blueprint cards in the grid. */
  get blueprintCards(): Locator {
    return this.page.locator("[class*='rounded-xl'][class*='border']").filter({
      has: this.page.locator("h3"),
    });
  }

  /** Empty state. */
  get emptyState(): Locator {
    return this.page.getByText(/no blueprints found/i);
  }

  /** Loading spinner. */
  get loadingSpinner(): Locator {
    return this.page.locator("svg.animate-spin");
  }

  /** Preview modal. */
  get previewModal(): Locator {
    return this.page.locator(".fixed").filter({
      has: this.page.locator("button").filter({ hasText: /×/ }),
    });
  }

  // ── Create Dialog Locators ─────────────────────────────────────

  /** The create dialog container. */
  get createDialog(): Locator {
    return this.page.locator(".fixed").filter({
      has: this.page.locator("h2", { hasText: "Create Blueprint" }),
    });
  }

  /** Name input in create dialog. */
  get nameInput(): Locator {
    return this.createDialog.locator('input[placeholder*="Sprint Planning"]');
  }

  /** Description input in create dialog. */
  get descriptionInput(): Locator {
    return this.createDialog.locator('input[placeholder*="Brief description"]');
  }

  /** Content textarea in create dialog. */
  get contentTextarea(): Locator {
    return this.createDialog.locator("textarea");
  }

  /** Category select in create dialog. */
  get dialogCategorySelect(): Locator {
    return this.createDialog.locator("select").first();
  }

  /** Tags input in create dialog. */
  get tagsInput(): Locator {
    return this.createDialog.locator('input[placeholder*="brainstorm"]');
  }

  /** Submit button in create dialog. */
  get submitButton(): Locator {
    return this.createDialog.getByRole("button", { name: /create blueprint/i });
  }

  /** Cancel button in create dialog. */
  get cancelButton(): Locator {
    return this.createDialog.getByRole("button", { name: /cancel/i });
  }

  // ── Actions ─────────────────────────────────────────────────────

  /** Navigate to the blueprints page. */
  async goto(): Promise<void> {
    await this.page.goto("/blueprints");
    await this.page.waitForLoadState("networkidle");
  }

  /** Get the number of visible blueprint cards. */
  async getBlueprintCount(): Promise<number> {
    await this.page.waitForTimeout(500);
    return this.blueprintCards.count();
  }

  /** Search for blueprints. */
  async search(query: string): Promise<void> {
    await this.searchInput.clear();
    await this.searchInput.fill(query);
    await this.page.waitForTimeout(500);
  }

  /** Filter by category. */
  async filterByCategory(category: string): Promise<void> {
    await this.categoryFilter.selectOption(category);
    await this.page.waitForTimeout(500);
  }

  /** Filter by source. */
  async filterBySource(source: string): Promise<void> {
    await this.sourceFilter.selectOption(source);
    await this.page.waitForTimeout(500);
  }

  /** Open the create dialog. */
  async openCreateDialog(): Promise<void> {
    await this.createButton.click();
    await this.createDialog.waitFor({ state: "visible", timeout: 5000 });
    await this.page.waitForTimeout(300);
  }

  /** Preview a blueprint card by index. */
  async previewCard(index: number): Promise<void> {
    const card = this.blueprintCards.nth(index);
    await card.hover();
    await this.page.waitForTimeout(200);
    const previewBtn = card.locator('button[title="Preview"]');
    await previewBtn.click();
    await this.page.waitForTimeout(500);
  }
}
