import { type Page, type Locator, expect } from "@playwright/test";

/**
 * Page object for the Desktop Personas route ("/personas").
 *
 * The page contains:
 * - Header with persona count and Create Persona button
 * - Search input and category filter pills (All, General, Technical, Creative, Business, Custom)
 * - Persona cards grid with edit (pencil) and delete (trash) buttons
 * - Wizard-style Create/Edit dialog:
 *   - Step 1: Select persona type (card grid with search)
 *   - Step 2: Configure details (name, description, category, credentials, system prompt)
 * - Delete confirmation dialog
 */
export class PersonasPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  // ── Locators ────────────────────────────────────────────────────

  /** The "Create Persona" button (header — always visible). */
  get createButton(): Locator {
    return this.page.getByRole("button", { name: /create persona/i }).first();
  }

  /** The search input field. */
  get searchInput(): Locator {
    return this.page.locator('input[placeholder="Search personas..."]');
  }

  /** All category filter pill buttons. */
  get categoryFilters(): Locator {
    return this.page.locator("button").filter({
      hasText: /^(All|General|Technical|Creative|Business|Custom)$/,
    });
  }

  /** All persona cards in the grid. */
  get personaCards(): Locator {
    return this.page.locator(".group").filter({
      has: this.page.locator("h3"),
    });
  }

  /** The refresh button. */
  get refreshButton(): Locator {
    return this.page.locator("button", {
      has: this.page.locator("svg.lucide-refresh-cw"),
    });
  }

  // ── Wizard locators ───────────────────────────────────────────

  /** The wizard dialog overlay. */
  get wizardDialog(): Locator {
    return this.page.locator(".fixed.inset-0.z-50").filter({
      has: this.page.locator("text=Add New Persona, text=Edit Persona"),
    });
  }

  /** Type search input on Step 1 of the wizard. */
  get typeSearchInput(): Locator {
    return this.page.locator('input[placeholder="Search persona types..."]');
  }

  /** Type cards on Step 1 of the wizard. */
  get typeCards(): Locator {
    return this.page.locator(".fixed.inset-0 .grid button").filter({
      has: this.page.locator("p.text-sm.font-medium"),
    });
  }

  /** Name input in step 2 of the wizard. */
  get formName(): Locator {
    return this.page.locator('input[placeholder="e.g., My Production DB"]');
  }

  /** Description input in step 2 of the wizard. */
  get formDescription(): Locator {
    return this.page.locator(
      'input[placeholder="A short description of what this persona does"]'
    );
  }

  /** Category select dropdown in step 2 of the wizard. */
  get formCategory(): Locator {
    return this.page
      .locator("select")
      .filter({ has: this.page.locator('option[value="General"]') });
  }

  /** System prompt textarea in step 2 of the wizard. */
  get formSystemPrompt(): Locator {
    return this.page.locator(
      'textarea[placeholder*="Optional instructions that define how this persona behaves"]'
    );
  }

  /** The wizard save/create button (step 2). */
  get formSaveButton(): Locator {
    return this.page
      .locator(".fixed button")
      .filter({ hasText: /^(Create|Update|Saving\.\.\.)$/ });
  }

  /** The wizard cancel button. */
  get formCancelButton(): Locator {
    return this.page.locator(".fixed button").filter({ hasText: "Cancel" });
  }

  /** The wizard "Next" button (step 1). */
  get nextButton(): Locator {
    return this.page.locator(".fixed button").filter({ hasText: "Next" });
  }

  /** The wizard "Back" button (step 2). */
  get backButton(): Locator {
    return this.page.locator(".fixed button").filter({ hasText: "Back" });
  }

  /** Delete confirmation dialog. */
  get deleteDialog(): Locator {
    return this.page.locator(".fixed").filter({ hasText: "Delete persona?" });
  }

  /** Confirm delete button in the confirmation dialog. */
  get confirmDeleteButton(): Locator {
    return this.deleteDialog.getByRole("button", { name: "Delete" });
  }

  // ── Actions ─────────────────────────────────────────────────────

  /** Navigate to the personas page. */
  async goto(): Promise<void> {
    await this.page.goto("/personas");
    await this.page.waitForLoadState("networkidle");
  }

  /**
   * Create a new persona via the wizard.
   * Step 1: Select type (clicks "Next" to proceed)
   * Step 2: Fill in details and click "Create"
   */
  async createPersona(data: {
    name: string;
    description?: string;
    type?: string;
    category?: string;
    systemPrompt?: string;
  }): Promise<void> {
    await this.createButton.click();

    // Step 1: Wait for type grid to be visible, then proceed
    await expect(this.typeSearchInput).toBeVisible({ timeout: 5_000 });

    // If a specific type is requested, click its card
    if (data.type) {
      const typeCard = this.page.locator(".fixed.inset-0 .grid button").filter({
        has: this.page.locator(`option[value="${data.type}"]`),
      });
      if (await typeCard.isVisible().catch(() => false)) {
        await typeCard.click();
      }
    }

    // Click Next to go to step 2
    await this.nextButton.click();
    await expect(this.formName).toBeVisible({ timeout: 5_000 });

    // Step 2: Fill details
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

    // Wait for wizard to close
    await expect(this.formName).toBeHidden({ timeout: 10_000 });
  }

  /**
   * Edit an existing persona by hovering over its card to reveal the edit button.
   * The edit wizard opens directly on Step 2.
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

    // Click the pencil (edit) button
    const editBtn = card.locator("button").first();
    await editBtn.dispatchEvent("click");

    // Edit mode opens directly on step 2
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

  /**
   * Delete a persona by hovering to reveal the trash button,
   * then confirming in the dialog.
   */
  async deletePersona(name: string): Promise<void> {
    const card = this.personaCards.filter({ hasText: name }).first();
    await card.scrollIntoViewIfNeeded();

    const deleteBtn = card.locator("button").last();
    await deleteBtn.dispatchEvent("click");

    await expect(this.deleteDialog).toBeVisible({ timeout: 5_000 });
    await this.confirmDeleteButton.click();

    await expect(this.deleteDialog).toBeHidden({ timeout: 10_000 });
  }

  /** Type a search query into the search input. */
  async searchPersonas(query: string): Promise<void> {
    await this.searchInput.clear();
    await this.searchInput.fill(query);
    await this.page.waitForTimeout(300);
  }

  /** Click a category filter pill. */
  async filterByCategory(category: string): Promise<void> {
    await this.page
      .locator("button")
      .filter({ hasText: new RegExp(`^${category}$`) })
      .first()
      .click();
    await this.page.waitForTimeout(300);
  }

  /** Get all visible persona names from the cards. */
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
