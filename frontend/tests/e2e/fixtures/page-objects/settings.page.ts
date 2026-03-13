import { type Page, type Locator, expect } from "@playwright/test";

/**
 * Page object for the Desktop Settings route ("/settings").
 *
 * The page contains 5 tabs:
 * - AI Providers: provider cards with expand, API key input, Test Connection
 * - Brand Voice: business name, industry, description, voice, audience, topics
 * - Appearance: theme (Light/Dark/System), font size (Small/Medium/Large)
 * - Data & Export: export JSON, import, clear all data
 * - About: version info, check for updates
 */
export class SettingsPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  // ── Locators ────────────────────────────────────────────────────

  /** All settings tab buttons. */
  get tabs(): Locator {
    return this.page.locator("[role='tab'], button").filter({
      hasText: /^(AI Providers|Brand Voice|Appearance|Data & Export|About)$/,
    });
  }

  /** Provider cards (in the AI Providers tab). */
  get providerCards(): Locator {
    return this.page.locator("[class*='rounded-2xl'][class*='border']").filter({
      has: this.page.locator("[class*='rounded-xl'][class*='bg-gradient-to-br']"),
    });
  }

  /** API key input fields (visible when a provider is expanded). */
  get apiKeyInputs(): Locator {
    return this.page.locator('input[type="password"]');
  }

  /** Test Connection buttons. */
  get testButtons(): Locator {
    return this.page.getByRole("button", { name: /test connection|detect ollama/i });
  }

  /** Theme selection buttons (Light, Dark, System). */
  get themeButtons(): Locator {
    return this.page.locator("button").filter({
      hasText: /^(Light|Dark|System)$/,
    });
  }

  /** Font size selection buttons. */
  get fontSizeButtons(): Locator {
    return this.page.locator("button").filter({
      hasText: /^(Small|Medium|Large)$/,
    });
  }

  /** Export data button. */
  get exportButton(): Locator {
    return this.page.getByRole("button", { name: /export as json/i });
  }

  /** Import from file button. */
  get importButton(): Locator {
    return this.page.getByRole("button", { name: /import from file/i });
  }

  /** Clear all data button. */
  get clearDataButton(): Locator {
    return this.page.getByRole("button", { name: /clear all data/i });
  }

  /** App version text in the About tab. */
  get versionText(): Locator {
    return this.page.locator("p").filter({ hasText: /version \d+\.\d+\.\d+/i });
  }

  /** Check for Updates button in the About tab. */
  get checkUpdatesButton(): Locator {
    return this.page.getByRole("button", { name: /check for updates/i });
  }

  /** Save Brand Voice button. */
  get saveBrandVoiceButton(): Locator {
    return this.page.getByRole("button", { name: /save brand voice/i });
  }

  /** "Connected" badges on provider cards. */
  get connectedBadges(): Locator {
    return this.page.locator("span, [class*='badge']").filter({
      hasText: /^Connected$/,
    });
  }

  /** "Connection successful" confirmation text. */
  get connectionSuccessText(): Locator {
    return this.page.getByText(/connection successful/i);
  }

  // ── Local AI Locators ───────────────────────────────────────────

  /** The Local AI (Built-in) provider card. */
  get localAICard(): Locator {
    return this.providerCards.filter({ hasText: "Local AI (Built-in)" }).first();
  }

  /** Local model items inside the expanded Local AI card. */
  get localModelItems(): Locator {
    return this.page.locator("[class*='rounded-xl'][class*='border']").filter({
      has: this.page.locator("text=/\\d+\\.\\d+ GB/"),
    });
  }

  /** Download buttons for local models (only visible for non-downloaded models). */
  get localModelDownloadButtons(): Locator {
    return this.page.getByRole("button", { name: /download/i }).filter({
      hasNotText: /downloaded/i,
    });
  }

  /** "Downloaded" badges on local model items. */
  get localModelDownloadedBadges(): Locator {
    return this.page.locator("text=Downloaded");
  }

  // ── Actions ─────────────────────────────────────────────────────

  /** Navigate to the settings page. */
  async goto(): Promise<void> {
    await this.page.goto("/settings");
    await this.page.waitForLoadState("networkidle");
  }

  /** Switch to a specific settings tab. */
  async switchTab(
    tabName: "AI Providers" | "Brand Voice" | "Appearance" | "Data & Export" | "About"
  ): Promise<void> {
    await this.tabs.filter({ hasText: tabName }).click();
    await this.page.waitForTimeout(300);
  }

  /**
   * Expand a provider card by clicking it.
   * @param name Provider display name (e.g., "Anthropic Claude", "OpenAI", "Ollama (Local)")
   */
  async expandProvider(name: string): Promise<void> {
    const card = this.providerCards.filter({ hasText: name }).first();
    // Click the card header button to expand
    await card.locator("button").first().click();
    await this.page.waitForTimeout(300);
  }

  /**
   * Set the API key for a provider (expand card first if needed).
   */
  async setApiKey(provider: string, key: string): Promise<void> {
    await this.expandProvider(provider);

    const card = this.providerCards.filter({ hasText: provider }).first();
    const keyInput = card.locator('input[type="password"]');
    await keyInput.fill(key);
  }

  /**
   * Click Test Connection for a specific provider.
   * The provider card must already be expanded.
   */
  async testConnection(provider: string): Promise<void> {
    const card = this.providerCards.filter({ hasText: provider }).first();
    const testBtn = card.getByRole("button", {
      name: /test connection|detect ollama/i,
    });
    await testBtn.click();

    // Wait for test to complete (loading spinner disappears)
    await this.page.waitForTimeout(2000);
  }

  /** Select a theme in the Appearance tab. */
  async setTheme(theme: "Light" | "Dark" | "System"): Promise<void> {
    await this.switchTab("Appearance");
    await this.themeButtons.filter({ hasText: theme }).click();
  }

  /** Click the Export Data button in the Data & Export tab. */
  async exportData(): Promise<void> {
    await this.switchTab("Data & Export");
    await this.exportButton.click();
    await this.page.waitForTimeout(1000);
  }

  /** Get the app version string from the About tab. */
  async getAppVersion(): Promise<string> {
    await this.switchTab("About");
    const text = await this.versionText.textContent();
    return text?.trim() ?? "";
  }
}
