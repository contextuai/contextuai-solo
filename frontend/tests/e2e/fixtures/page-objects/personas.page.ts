import { type Page, type Locator, expect } from "@playwright/test";

/**
 * Page object for the Desktop Personas route ("/personas").
 *
 * The page contains:
 * - Header with persona count and Create Persona button
 * - Search input and category filter pills (All, General, Technical, Creative, Business, Custom)
 * - Persona cards grid with edit (pencil) and delete (trash) buttons
 * - Create/Edit modal with name, description, type, category, system_prompt fields
 * - Delete confirmation dialog
 */
export class PersonasPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  // ── Locators ────────────────────────────────────────────────────

  /** The "Create Persona" button in the header. */
  get createButton(): Locator {
    return this.page.getByRole("button", { name: /create persona/i });
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

  // Form fields (visible when modal is open)

  /** Name input in the create/edit modal. */
  get formName(): Locator {
    return this.page.locator('input[placeholder="e.g., Code Reviewer"]');
  }

  /** Description input in the create/edit modal. */
  get formDescription(): Locator {
    return this.page.locator(
      'input[placeholder="A short description of what this persona does"]'
    );
  }

  /** Type select dropdown in the create/edit modal. */
  get formType(): Locator {
    return this.page
      .locator("select")
      .filter({ has: this.page.locator('option[value="generic"]') });
  }

  /** Category select dropdown in the create/edit modal. */
  get formCategory(): Locator {
    return this.page
      .locator("select")
      .filter({ has: this.page.locator('option[value="General"]') });
  }

  /** System prompt textarea in the create/edit modal. */
  get formSystemPrompt(): Locator {
    return this.page.locator(
      'textarea[placeholder*="Instructions that define how this persona behaves"]'
    );
  }

  /** The modal save/create button. */
  get formSaveButton(): Locator {
    return this.page
      .locator(".fixed button")
      .filter({ hasText: /^(Create|Update|Saving\.\.\.)$/ });
  }

  /** The modal cancel button. */
  get formCancelButton(): Locator {
    return this.page.locator(".fixed button").filter({ hasText: "Cancel" });
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
   * Create a new persona via the modal form.
   */
  async createPersona(data: {
    name: string;
    description?: string;
    type?: string;
    category?: string;
    systemPrompt?: string;
  }): Promise<void> {
    await this.createButton.click();
    await expect(this.formName).toBeVisible({ timeout: 5_000 });

    await this.formName.fill(data.name);

    if (data.description) {
      await this.formDescription.fill(data.description);
    }
    if (data.type) {
      await this.formType.selectOption(data.type);
    }
    if (data.category) {
      await this.formCategory.selectOption(data.category);
    }
    if (data.systemPrompt) {
      await this.formSystemPrompt.fill(data.systemPrompt);
    }

    await this.formSaveButton.click();

    // Wait for modal to close
    await expect(this.formName).toBeHidden({ timeout: 10_000 });
  }

  /**
   * Edit an existing persona by hovering over its card to reveal the edit button.
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
    await card.hover();

    // Click the pencil (edit) button
    const editButton = card.locator("button", {
      has: this.page.locator("svg.lucide-pencil"),
    });
    await editButton.click();
    await expect(this.formName).toBeVisible({ timeout: 5_000 });

    if (data.name !== undefined) {
      await this.formName.clear();
      await this.formName.fill(data.name);
    }
    if (data.description !== undefined) {
      await this.formDescription.clear();
      await this.formDescription.fill(data.description);
    }
    if (data.type) {
      await this.formType.selectOption(data.type);
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
    await card.hover();

    const deleteButton = card.locator("button", {
      has: this.page.locator("svg.lucide-trash-2"),
    });
    await deleteButton.click();

    await expect(this.deleteDialog).toBeVisible({ timeout: 5_000 });
    await this.confirmDeleteButton.click();

    // Wait for dialog to close
    await expect(this.deleteDialog).toBeHidden({ timeout: 10_000 });
  }

  /** Type a search query into the search input. */
  async searchPersonas(query: string): Promise<void> {
    await this.searchInput.clear();
    await this.searchInput.fill(query);
    // Allow filtering to take effect
    await this.page.waitForTimeout(300);
  }

  /** Click a category filter pill. */
  async filterByCategory(category: string): Promise<void> {
    await this.page
      .locator("button")
      .filter({ hasText: new RegExp(`^${category}$`) })
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
