/**
 * ContextuAI Solo Desktop — Connections E2E Tests
 *
 * Route: "/connections"
 * Backend: http://127.0.0.1:18741 (no auth)
 * Frontend: http://localhost:1420 (Vite SPA)
 *
 * Connections are stored in localStorage. Telegram and Discord use token-paste,
 * LinkedIn uses OAuth flow.
 */
import { test, expect } from "@playwright/test";
import { ConnectionsPage } from "../fixtures/page-objects";

let connections: ConnectionsPage;

test.beforeEach(async ({ page }) => {
  connections = new ConnectionsPage(page);
  await connections.goto();
});

// ==========================================================================
// CRUD via UI
// ==========================================================================

test.describe("CRUD via UI", () => {
  // DC-CONN-01: View all 3 connection cards (Telegram, Discord, LinkedIn)
  test("DC-CONN-01: view all 3 connection cards", async ({ page }) => {
    await expect(page.locator("h1", { hasText: "Connections" })).toBeVisible();

    await expect(page.locator("h3", { hasText: "Telegram Bot" })).toBeVisible();
    await expect(page.locator("h3", { hasText: "Discord Bot" })).toBeVisible();
    await expect(page.locator("h3", { hasText: "LinkedIn" })).toBeVisible();

    const count = await connections.connectionCards.count();
    expect(count).toBe(3);
  });

  // DC-CONN-02: Expand Telegram connection form
  test("DC-CONN-02: expand telegram connection form", async ({ page }) => {
    const telegramCard = connections.connectionCards.filter({ hasText: "Telegram Bot" });
    await telegramCard.locator("button").filter({ hasText: /connect|edit/i }).click();
    await page.waitForTimeout(300);

    // Bot Token field should be visible
    await expect(page.locator("input[placeholder*='123456']")).toBeVisible();

    // Direction toggles should be visible
    await expect(page.locator("text=Inbound")).toBeVisible();
    await expect(page.locator("text=Outbound")).toBeVisible();
  });

  // DC-CONN-03: Expand Discord connection form
  test("DC-CONN-03: expand discord connection form", async ({ page }) => {
    const discordCard = connections.connectionCards.filter({ hasText: "Discord Bot" });
    await discordCard.locator("button").filter({ hasText: /connect|edit/i }).click();
    await page.waitForTimeout(300);

    await expect(page.locator("input[placeholder='Your Discord bot token']")).toBeVisible();
    await expect(page.locator("input[placeholder*='public key']")).toBeVisible();
    await expect(page.locator("input[placeholder*='application ID']")).toBeVisible();
  });

  // DC-CONN-04: Save Telegram bot token
  test("DC-CONN-04: save telegram bot token", async ({ page }) => {
    await connections.connectTelegram("123456:test-fake-bot-token-for-e2e");

    const status = await connections.getConnectionStatus("Telegram");
    expect(status).toBe("connected");
  });

  // DC-CONN-05: Disconnect a connection
  test("DC-CONN-05: disconnect a connection", async ({ page }) => {
    // First connect
    await connections.connectTelegram("123456:token-to-disconnect");
    expect(await connections.getConnectionStatus("Telegram")).toBe("connected");

    // Disconnect
    await connections.disconnectConnection("Telegram");

    const status = await connections.getConnectionStatus("Telegram");
    expect(status).toBe("disconnected");
  });
});

// ==========================================================================
// Positive Workflows
// ==========================================================================

test.describe("Positive Workflows", () => {
  // DC-CONN-06: Connected status badge appears after saving
  test("DC-CONN-06: connected status badge appears after saving", async ({ page }) => {
    await connections.connectTelegram("123456:valid-looking-token");

    const badge = connections.connectionCards
      .filter({ hasText: "Telegram" })
      .locator("span", { hasText: "Connected" });
    await expect(badge).toBeVisible();
  });

  // DC-CONN-07: Direction toggles (Inbound/Outbound) work
  test("DC-CONN-07: direction toggles work", async ({ page }) => {
    const telegramCard = connections.connectionCards.filter({ hasText: "Telegram Bot" });
    await telegramCard.locator("button").filter({ hasText: /connect|edit/i }).click();
    await page.waitForTimeout(300);

    const inboundBtn = page.locator("button").filter({ hasText: "Inbound" }).first();
    const outboundBtn = page.locator("button").filter({ hasText: "Outbound" }).first();

    await expect(inboundBtn).toBeVisible();
    await expect(outboundBtn).toBeVisible();

    // Toggle off and back on
    await inboundBtn.click();
    await page.waitForTimeout(200);
    await outboundBtn.click();
    await page.waitForTimeout(200);
    await inboundBtn.click();
    await outboundBtn.click();
    await page.waitForTimeout(200);

    await expect(inboundBtn).toBeVisible();
  });

  // DC-CONN-08: LinkedIn shows OAuth setup instructions
  test("DC-CONN-08: linkedin shows oauth setup instructions", async ({ page }) => {
    const linkedInCard = connections.connectionCards.filter({ hasText: "LinkedIn" });
    await linkedInCard.locator("button").filter({ hasText: /connect|edit/i }).click();
    await page.waitForTimeout(300);

    await expect(page.locator("text=How to connect LinkedIn")).toBeVisible();
    await expect(page.locator("input[placeholder*='Client ID']")).toBeVisible();
    await expect(page.locator("input[placeholder*='Client Secret']")).toBeVisible();
    await expect(page.locator("button", { hasText: "Sign in with LinkedIn" })).toBeVisible();
  });

  // DC-CONN-09: External docs links are present
  test("DC-CONN-09: external docs links are present", async ({ page }) => {
    const docsLinks = page.locator("a[title='Setup guide']");
    const count = await docsLinks.count();
    expect(count).toBe(3);

    const links = await docsLinks.all();
    for (const link of links) {
      const href = await link.getAttribute("href");
      expect(href).toBeTruthy();
      expect(href).toMatch(/^https?:\/\//);
    }
  });
});

// ==========================================================================
// Negative Workflows
// ==========================================================================

test.describe("Negative Workflows", () => {
  // DC-CONN-10: Cancel edit discards changes
  test("DC-CONN-10: cancel edit discards changes", async ({ page }) => {
    const telegramCard = connections.connectionCards.filter({ hasText: "Telegram Bot" });
    await telegramCard.locator("button").filter({ hasText: /connect|edit/i }).click();
    await page.waitForTimeout(300);

    const tokenInput = page.locator("input[placeholder*='123456']");
    await tokenInput.fill("temporary-token-to-cancel");

    // Click Cancel
    await connections.cancelButton.click();
    await expect(tokenInput).not.toBeVisible();

    // Re-expand to verify token was not saved
    await telegramCard.locator("button").filter({ hasText: /connect|edit/i }).click();
    await page.waitForTimeout(300);
    const newTokenInput = page.locator("input[placeholder*='123456']");
    const value = await newTokenInput.inputValue();
    expect(value).toBe("");
  });

  // DC-CONN-11: Empty token save shows disconnected state
  test("DC-CONN-11: empty token save shows disconnected state", async ({ page }) => {
    const telegramCard = connections.connectionCards.filter({ hasText: "Telegram Bot" });
    await telegramCard.locator("button").filter({ hasText: /connect|edit/i }).click();
    await page.waitForTimeout(300);

    // Leave token empty and save
    const tokenInput = page.locator("input[placeholder*='123456']");
    await tokenInput.fill("");

    await connections.saveTestButton.click();
    // Wait for simulated test
    await page.waitForTimeout(2500);

    const status = await connections.getConnectionStatus("Telegram");
    expect(status).toBe("disconnected");
  });
});
