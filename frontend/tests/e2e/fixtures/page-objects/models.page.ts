import { type Page, type Locator } from "@playwright/test";

/**
 * Page object for the Model Hub route ("/models").
 */
export class ModelsPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  // ── Navigation ──────────────────────────────────────────────────

  async goto() {
    await this.page.goto("http://localhost:1420/models");
    await this.page.waitForSelector("h1:has-text('Model Hub')", {
      timeout: 15000,
    });
  }

  // ── Locators ────────────────────────────────────────────────────

  get heading(): Locator {
    return this.page.locator("h1", { hasText: "Model Hub" });
  }

  get searchInput(): Locator {
    return this.page.locator('input[placeholder*="Search models"]');
  }

  get recommendedSection(): Locator {
    return this.page.locator("h2", { hasText: "Recommended for You" });
  }

  get allModelsSection(): Locator {
    return this.page.locator("h2", { hasText: "All Models" });
  }

  /** All model cards on the page (recommended + all). */
  get modelCards(): Locator {
    return this.page.locator("h3.text-sm.font-semibold");
  }

  /** Cards with the "Recommended" badge. */
  get recommendedBadges(): Locator {
    return this.page.locator("span:has-text('Recommended')").filter({
      hasText: "Recommended",
    });
  }

  /** Category filter pills. */
  get categoryPills(): Locator {
    return this.page.locator("button").filter({ hasText: /^(All|General|Reasoning|Coding|Creative|Multilingual|Vision)$/ });
  }

  // ── Actions ─────────────────────────────────────────────────────

  async getModelNames(): Promise<string[]> {
    const cards = this.page.locator("h3.text-sm.font-semibold");
    return cards.allTextContents();
  }

  async getRecommendedModelNames(): Promise<string[]> {
    // Recommended cards are inside the section that follows the "Recommended for You" heading
    const section = this.page.locator("div.mb-8").filter({
      has: this.page.locator("h2:has-text('Recommended for You')"),
    });
    const names = section.locator("h3.text-sm.font-semibold");
    return names.allTextContents();
  }

  async searchFor(query: string): Promise<void> {
    await this.searchInput.fill(query);
    await this.page.waitForTimeout(300);
  }

  async clearSearch(): Promise<void> {
    await this.searchInput.fill("");
    await this.page.waitForTimeout(300);
  }

  async clickCategory(name: string): Promise<void> {
    await this.page
      .locator("button")
      .filter({ hasText: new RegExp(`^${name}$`) })
      .click();
    await this.page.waitForTimeout(300);
  }
}
