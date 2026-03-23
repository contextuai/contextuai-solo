import { type Page, type Locator, expect } from "@playwright/test";

/**
 * Page object for the Desktop Connections route ("/connections").
 *
 * The page contains 6 connection cards:
 * - Telegram Bot (token-paste flow)
 * - Discord Bot (token-paste flow)
 * - Twitter / X (token-paste flow — 4 fields)
 * - LinkedIn (OAuth flow)
 * - Instagram (OAuth flow)
 * - Facebook (OAuth flow)
 *
 * Each card has a Connect/Edit button that expands a form with:
 * - Token/credential fields
 * - Direction toggles (Inbound/Outbound) for Telegram & Discord
 * - Save & Test / Cancel buttons (or Sign in with <provider> for OAuth)
 * - Disconnect (trash) button when connected
 */
export class ConnectionsPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  // ── Locators ────────────────────────────────────────────────────

  /** All connection cards. */
  get connectionCards(): Locator {
    return this.page.locator("[class*='rounded-2xl'][class*='border']").filter({
      has: this.page.locator("h3"),
    });
  }

  /** Connect buttons (shown on disconnected cards). */
  get connectButtons(): Locator {
    return this.page.locator("button").filter({ hasText: /connect/i });
  }

  /** Disconnect (trash) buttons on connected cards. */
  get disconnectButtons(): Locator {
    return this.page.locator('button[title="Disconnect"]');
  }

  /** All visible token/credential input fields in expanded forms. */
  get tokenInputs(): Locator {
    return this.page.locator(
      'input[class*="rounded-xl"]'
    );
  }

  /** Save & Test button. */
  get saveTestButton(): Locator {
    return this.page.locator("button").filter({ hasText: /save & test/i });
  }

  /** Cancel button in the expanded form. */
  get cancelButton(): Locator {
    return this.page.locator("button").filter({ hasText: /^cancel$/i });
  }

  /** The "Connected" badge. */
  get connectedBadges(): Locator {
    return this.page.locator("span").filter({ hasText: /connected/i });
  }

  // ── Helpers ─────────────────────────────────────────────────────

  /** Get a specific connection card by name. */
  private getCard(name: string): Locator {
    return this.connectionCards
      .filter({ hasText: new RegExp(name, "i") })
      .first();
  }

  /** Get the connect/edit button for a specific connection. */
  private getConnectEditButton(name: string): Locator {
    const card = this.getCard(name);
    return card.locator("button").filter({
      hasText: /connect|edit/i,
    });
  }

  // ── Actions ─────────────────────────────────────────────────────

  /** Navigate to the connections page. */
  async goto(): Promise<void> {
    await this.page.goto("/connections");
    await this.page.waitForLoadState("networkidle");
    await this.page.waitForTimeout(1500);
  }

  /**
   * Connect Telegram by entering a bot token.
   */
  async connectTelegram(token: string): Promise<void> {
    await this.getConnectEditButton("Telegram").click();
    await this.page.waitForTimeout(300);

    // Fill the bot token field
    const tokenField = this.getCard("Telegram").locator(
      'input[placeholder*="bot token" i], input[placeholder*="123456"]'
    );
    await tokenField.fill(token);

    await this.saveTestButton.click();

    // Wait for testing to complete
    await expect(this.saveTestButton).toBeHidden({ timeout: 10_000 });
  }

  /**
   * Connect Twitter/X by entering API Key, API Secret, Access Token, and Access Token Secret.
   */
  async connectTwitter(
    apiKey: string,
    apiSecret: string,
    accessToken: string,
    accessTokenSecret: string
  ): Promise<void> {
    await this.getConnectEditButton("Twitter").click();
    await this.page.waitForTimeout(300);

    const card = this.getCard("Twitter");

    await card.locator('input[placeholder*="API Key" i]').first().fill(apiKey);
    await card.locator('input[placeholder*="API Secret" i]').fill(apiSecret);
    await card.locator('input[placeholder*="Access Token" i]').first().fill(accessToken);
    await card.locator('input[placeholder*="Access Token Secret" i]').fill(accessTokenSecret);

    await this.saveTestButton.click();
    await expect(this.saveTestButton).toBeHidden({ timeout: 10_000 });
  }

  /**
   * Connect Discord by entering bot token, public key, and application ID.
   */
  async connectDiscord(
    token: string,
    publicKey: string,
    appId: string
  ): Promise<void> {
    await this.getConnectEditButton("Discord").click();
    await this.page.waitForTimeout(300);

    const card = this.getCard("Discord");

    // Fill bot token
    const tokenField = card.locator(
      'input[placeholder*="Discord bot token" i]'
    );
    await tokenField.fill(token);

    // Fill public key
    const publicKeyField = card.locator(
      'input[placeholder*="public key" i]'
    );
    await publicKeyField.fill(publicKey);

    // Fill application ID
    const appIdField = card.locator(
      'input[placeholder*="application ID" i]'
    );
    await appIdField.fill(appId);

    await this.saveTestButton.click();
    await expect(this.saveTestButton).toBeHidden({ timeout: 10_000 });
  }

  /**
   * Disconnect a connection by clicking the trash/disconnect button.
   */
  async disconnectConnection(name: string): Promise<void> {
    const card = this.getCard(name);
    const disconnectBtn = card.locator('button[title="Disconnect"]');
    await disconnectBtn.click();
    await this.page.waitForTimeout(500);
  }

  /**
   * Get the connection status for a named connection.
   * Returns "connected" if the Connected badge is visible, "disconnected" otherwise.
   */
  async getConnectionStatus(
    name: string
  ): Promise<"connected" | "disconnected"> {
    // Wait for React to re-render after save
    await this.page.waitForTimeout(500);
    const card = this.getCard(name);
    const badge = card.locator("span").filter({ hasText: /^\s*Connected\s*$/i });
    try {
      await badge.waitFor({ state: "visible", timeout: 5000 });
      return "connected";
    } catch {
      return "disconnected";
    }
  }
}
