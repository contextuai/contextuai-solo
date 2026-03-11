import { type Page, type Locator, expect } from "@playwright/test";

/**
 * Page object for testing desktop sidebar navigation.
 *
 * The sidebar contains 7 nav items (Chat, Personas, Agents, Crews, Workshop,
 * Connections, Settings), a collapse/expand toggle, and connection status.
 */
export class NavigationPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  // ── Locators ────────────────────────────────────────────────────

  /** The sidebar element. */
  get sidebar(): Locator {
    return this.page.locator("aside");
  }

  /** All navigation link items. */
  get navItems(): Locator {
    return this.page.locator("aside nav a");
  }

  /** The collapse/expand toggle button on the sidebar. */
  get collapseToggle(): Locator {
    return this.page.locator("aside button.absolute");
  }

  // ── Actions ─────────────────────────────────────────────────────

  /** Navigate to the app root. */
  async goto(): Promise<void> {
    await this.page.goto("/");
    await this.page.waitForLoadState("networkidle");
  }

  /** Click a navigation item by label text. */
  async navigateTo(label: string): Promise<void> {
    await this.page.locator("aside nav a", { hasText: label }).click();
    await this.page.waitForLoadState("networkidle");
  }

  /** Get all visible navigation labels. */
  async getNavLabels(): Promise<string[]> {
    const items = await this.navItems.all();
    const labels: string[] = [];
    for (const item of items) {
      const text = await item.textContent();
      if (text?.trim()) labels.push(text.trim());
    }
    return labels;
  }
}
