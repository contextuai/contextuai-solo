/**
 * ContextuAI Solo Desktop — Settings E2E Tests
 *
 * Route: "/settings"
 * Backend: http://127.0.0.1:18741 (no auth)
 * Frontend: http://localhost:1420 (Vite SPA)
 *
 * Settings page has 5 tabs: AI Providers, Brand Voice, Appearance, Data & Export, About.
 */
import { test, expect } from "@playwright/test";
import { SettingsPage } from "../fixtures/page-objects";

let settings: SettingsPage;

test.beforeEach(async ({ page }) => {
  settings = new SettingsPage(page);
  await settings.goto();
});

// ==========================================================================
// CRUD via UI
// ==========================================================================

test.describe("CRUD via UI", () => {
  // DC-SETTINGS-01: Navigate between all 5 tabs
  test("DC-SETTINGS-01: navigate between all 5 tabs", async ({ page }) => {
    await expect(page.locator("h1", { hasText: "Settings" })).toBeVisible();

    const tabNames: Array<"AI Providers" | "Brand Voice" | "Appearance" | "Data & Export" | "About"> = [
      "AI Providers",
      "Brand Voice",
      "Appearance",
      "Data & Export",
      "About",
    ];

    for (const tabName of tabNames) {
      await settings.switchTab(tabName);
      await expect(page.locator("h1", { hasText: "Settings" })).toBeVisible();
    }
  });

  // DC-SETTINGS-02: AI Providers tab shows 5 providers
  test("DC-SETTINGS-02: ai providers tab shows 5 providers", async ({ page }) => {
    const providerNames = ["Anthropic Claude", "OpenAI", "Google Gemini", "AWS Bedrock", "Ollama"];
    for (const name of providerNames) {
      await expect(page.locator(`text=${name}`).first()).toBeVisible();
    }
  });

  // DC-SETTINGS-03: Expand a provider card
  test("DC-SETTINGS-03: expand a provider card", async ({ page }) => {
    await settings.expandProvider("Anthropic Claude");

    await expect(settings.apiKeyInputs.first()).toBeVisible();
    await expect(settings.testButtons.first()).toBeVisible();
  });

  // DC-SETTINGS-04: Enter and test API key
  test("DC-SETTINGS-04: enter and test api key", async ({ page }) => {
    await settings.setApiKey("Anthropic Claude", "sk-ant-test-key-1234567890-fake");
    await settings.testConnection("Anthropic Claude");

    await expect(settings.connectionSuccessText).toBeVisible();
  });

  // DC-SETTINGS-05: Brand Voice tab has all form fields
  test("DC-SETTINGS-05: brand voice tab has all form fields", async ({ page }) => {
    await settings.switchTab("Brand Voice");

    await expect(page.locator("text=Business Name")).toBeVisible();
    await expect(page.locator("text=Industry")).toBeVisible();
    await expect(page.locator("text=Brand Description")).toBeVisible();
    await expect(page.locator("text=Target Audience")).toBeVisible();
    await expect(page.locator("text=Content Topics")).toBeVisible();
    await expect(settings.saveBrandVoiceButton).toBeVisible();
  });
});

// ==========================================================================
// Positive Workflows
// ==========================================================================

test.describe("Positive Workflows", () => {
  // DC-SETTINGS-06: Theme selection (Light/Dark/System) persists
  test("DC-SETTINGS-06: theme selection persists", async ({ page }) => {
    await settings.setTheme("Dark");
    await page.waitForTimeout(500);

    const htmlClass = await page.locator("html").getAttribute("class");
    expect(htmlClass).toContain("dark");

    await settings.setTheme("Light");
    await page.waitForTimeout(500);

    const htmlClassAfter = await page.locator("html").getAttribute("class");
    expect(htmlClassAfter).not.toContain("dark");

    await settings.setTheme("System");
  });

  // DC-SETTINGS-07: Font size selection works
  test("DC-SETTINGS-07: font size selection works", async ({ page }) => {
    await settings.switchTab("Appearance");

    const fontButtons = await settings.fontSizeButtons.all();
    expect(fontButtons.length).toBe(3);

    for (const btn of fontButtons) {
      await btn.click();
      await page.waitForTimeout(200);

      const classes = await btn.getAttribute("class");
      expect(classes).toContain("border-primary");
    }
  });

  // DC-SETTINGS-08: Brand Voice preview updates dynamically
  test("DC-SETTINGS-08: brand voice preview updates dynamically", async ({ page }) => {
    await settings.switchTab("Brand Voice");

    const nameInput = page.locator("input[placeholder*='Acme Corp']");
    await nameInput.fill("TestCo");
    await page.waitForTimeout(300);

    await expect(page.locator("text=Brand Voice Preview")).toBeVisible();

    const previewText = page.locator("p.italic");
    const text = await previewText.textContent();
    expect(text).toContain("TestCo");
  });

  // DC-SETTINGS-09: Data Export downloads JSON file
  test("DC-SETTINGS-09: data export downloads json file", async ({ page }) => {
    await settings.switchTab("Data & Export");

    const downloadPromise = page.waitForEvent("download", { timeout: 10_000 });
    await settings.exportButton.click();

    const download = await downloadPromise;
    const filename = download.suggestedFilename();

    expect(filename).toContain("contextuai-solo-backup");
    expect(filename).toContain(".json");
  });

  // DC-SETTINGS-10: About tab shows version info
  test("DC-SETTINGS-10: about tab shows version info", async ({ page }) => {
    await settings.switchTab("About");

    await expect(page.locator("text=ContextuAI")).toBeVisible();
    await expect(page.locator("text=Solo")).toBeVisible();
    await expect(settings.versionText).toBeVisible();

    await expect(page.locator("text=Built with")).toBeVisible();
    await expect(page.locator("text=React")).toBeVisible();
    await expect(page.locator("text=Tauri")).toBeVisible();
    await expect(page.locator("text=FastAPI")).toBeVisible();
  });

  // DC-SETTINGS-11: Check for Updates button works
  test("DC-SETTINGS-11: check for updates button works", async ({ page }) => {
    await settings.switchTab("About");

    await expect(settings.checkUpdatesButton).toBeVisible();
    await settings.checkUpdatesButton.click();

    // Wait for simulated check (1.5s)
    await page.waitForTimeout(2500);

    await expect(page.locator("text=latest version")).toBeVisible();
  });
});

// ==========================================================================
// Negative Workflows
// ==========================================================================

test.describe("Negative Workflows", () => {
  // DC-SETTINGS-12: Test Connection with short key fails
  test("DC-SETTINGS-12: test connection with short key fails", async ({ page }) => {
    await settings.setApiKey("Anthropic Claude", "short");
    await settings.testConnection("Anthropic Claude");

    await expect(page.locator("text=Connection failed")).toBeVisible();
  });

  // DC-SETTINGS-13: Clear All Data shows confirmation dialog
  test("DC-SETTINGS-13: clear all data shows confirmation dialog", async ({ page }) => {
    await settings.switchTab("Data & Export");

    await settings.clearDataButton.click();
    await page.waitForTimeout(300);

    await expect(page.locator("text=Clear All Data?")).toBeVisible();
    await expect(page.locator("text=permanently delete")).toBeVisible();

    // Cancel — do NOT actually clear data
    const cancelBtn = page.locator("button", { hasText: "Cancel" });
    await cancelBtn.click();
    await page.waitForTimeout(300);

    await expect(page.locator("text=Clear All Data?")).not.toBeVisible();
  });
});
