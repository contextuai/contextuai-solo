import { type Page, type Locator, expect } from "@playwright/test";

/**
 * Page object for the Desktop Personas route ("/personas").
 *
 * Wizard-style Create flow:
 *   Step 1: Select persona type (card grid with search)
 *   Step 2: Configure details (name, description, category, credentials, system prompt)
 * Edit opens directly on Step 2.
 */
export class PersonasPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  // ── Locators ────────────────────────────────────────────────────

  get createButton(): Locator {
    return this.page.getByRole("button", { name: /create persona/i }).first();
  }

  get searchInput(): Locator {
    return this.page.locator('input[placeholder="Search personas..."]');
  }

  get categoryFilters(): Locator {
    return this.page.locator("button").filter({
      hasText: /^(All|General|Technical|Creative|Business|Custom)$/,
    });
  }

  get personaCards(): Locator {
    return this.page.locator(".group").filter({
      has: this.page.locator("h3"),
    });
  }

  get refreshButton(): Locator {
    return this.page.locator("button", {
      has: this.page.locator("svg.lucide-refresh-cw"),
    });
  }

  // ── Wizard locators ───────────────────────────────────────────

  /** Type search input on Step 1. */
  get typeSearchInput(): Locator {
    return this.page.locator('input[placeholder="Search persona types..."]');
  }

  /** Name input in Step 2. */
  get formName(): Locator {
    return this.page.locator('input[placeholder="e.g., My Production DB"]');
  }

  /** Description input in Step 2. */
  get formDescription(): Locator {
    return this.page.locator(
      'input[placeholder="A short description of what this persona does"]'
    );
  }

  /** Type select dropdown — only visible in edit mode (Step 2 fallback). */
  get formType(): Locator {
    return this.page
      .locator("select")
      .filter({ has: this.page.locator('option[value="generic"]') });
  }

  /** Category select dropdown in Step 2. */
  get formCategory(): Locator {
    return this.page
      .locator("select")
      .filter({ has: this.page.locator('option[value="General"]') });
  }

  /** System prompt textarea in Step 2. */
  get formSystemPrompt(): Locator {
    return this.page.locator(
      'textarea[placeholder*="Optional instructions that define how this persona behaves"]'
    );
  }

  /** Save/Create button (Step 2). */
  get formSaveButton(): Locator {
    return this.page
      .locator(".fixed button")
      .filter({ hasText: /^(Create|Update|Saving\.\.\.)$/ });
  }

  /** Cancel button. */
  get formCancelButton(): Locator {
    return this.page.locator(".fixed button").filter({ hasText: "Cancel" });
  }

  /** Next button (Step 1). */
  get nextButton(): Locator {
    return this.page.locator(".fixed button").filter({ hasText: "Next" });
  }

  /** Back button (Step 2). */
  get backButton(): Locator {
    return this.page.locator(".fixed button").filter({ hasText: "Back" });
  }

  /** Delete confirmation dialog. */
  get deleteDialog(): Locator {
    return this.page.locator(".fixed").filter({ hasText: "Delete persona?" });
  }

  get confirmDeleteButton(): Locator {
    return this.deleteDialog.getByRole("button", { name: "Delete" });
  }

  // ── Actions ─────────────────────────────────────────────────────

  async goto(): Promise<void> {
    await this.page.goto("/personas");
    await this.page.waitForLoadState("networkidle");
  }

  /**
   * Create a persona via the wizard.
   * Step 1 → click Next → Step 2 → fill details → Create.
   */
  async createPersona(data: {
    name: string;
    description?: string;
    type?: string;
    category?: string;
    systemPrompt?: string;
  }): Promise<void> {
    await this.createButton.click();

    // Step 1: Wait for type grid, then proceed
    await expect(this.typeSearchInput).toBeVisible({ timeout: 5_000 });
    await this.nextButton.click();

    // Step 2: Fill details
    await expect(this.formName).toBeVisible({ timeout: 5_000 });
    await this.formName.fill(data.name);

    if (data.description) {
      await this.formDescription.fill(data.description);
    }
    if (data.category) {
      await this.formCategory.selectOption(data.category);
    }
    if (data.systemPrompt) {
      await this.formSystemPrompt.fill(data.systemPrompt);
    }

    await this.formSaveButton.click();
    await expect(this.formName).toBeHidden({ timeout: 10_000 });
  }

  /**
   * Edit an existing persona. Opens directly on Step 2.
   */
  async editPersona(
    currentName: string,
    data: {
      name?: string;
      description?: string;
      type?: string;
      category?: string;
      systemPrompt?: string;
    }
  ): Promise<void> {
    const card = this.personaCards.filter({ hasText: currentName }).first();
    await card.scrollIntoViewIfNeeded();

    const editBtn = card.locator("button").first();
    await editBtn.click({ force: true });
    await expect(this.formName).toBeVisible({ timeout: 5_000 });

    if (data.name !== undefined) {
      await this.formName.clear();
      await this.formName.fill(data.name);
    }
    if (data.description !== undefined) {
      await this.formDescription.clear();
      await this.formDescription.fill(data.description);
    }
    if (data.category) {
      await this.formCategory.selectOption(data.category);
    }
    if (data.systemPrompt !== undefined) {
      await this.formSystemPrompt.clear();
      await this.formSystemPrompt.fill(data.systemPrompt);
    }

    await this.formSaveButton.click();
    await expect(this.formName).toBeHidden({ timeout: 10_000 });
  }

  async deletePersona(name: string): Promise<void> {
    const card = this.personaCards.filter({ hasText: name }).first();
    await card.scrollIntoViewIfNeeded();

    const deleteBtn = card.locator("button").last();
    await deleteBtn.click({ force: true });

    await expect(this.deleteDialog).toBeVisible({ timeout: 5_000 });
    await this.confirmDeleteButton.click();
    await expect(this.deleteDialog).toBeHidden({ timeout: 10_000 });
  }

  async searchPersonas(query: string): Promise<void> {
    await this.searchInput.clear();
    await this.searchInput.fill(query);
    await this.page.waitForTimeout(300);
  }

  async filterByCategory(category: string): Promise<void> {
    await this.page
      .locator("button")
      .filter({ hasText: new RegExp(`^${category}$`) })
      .first()
      .click();
    await this.page.waitForTimeout(300);
  }

  async getPersonaNames(): Promise<string[]> {
    const cards = this.personaCards;
    const count = await cards.count();
    const names: string[] = [];
    for (let i = 0; i < count; i++) {
      const name = await cards.nth(i).locator("h3").textContent();
      if (name) names.push(name.trim());
    }
    return names;
  }
}
