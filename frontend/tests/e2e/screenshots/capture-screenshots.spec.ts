/**
 * Screenshot capture for website/marketing materials.
 * Run: npx playwright test tests/e2e/screenshots/capture-screenshots.spec.ts
 * Output: frontend/tests/e2e/screenshots/output/
 */
import { test, expect } from "@playwright/test";

const OUTPUT_DIR = "tests/e2e/screenshots/output";

test.describe("Website Screenshots", () => {
  test.beforeEach(async ({ page }) => {
    // Set consistent viewport for marketing screenshots
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  test("01 — Chat page with conversation", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    // Wait for sidebar and chat input to load
    await expect(page.locator('[placeholder*="message"], [placeholder*="Message"], textarea')).toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: `${OUTPUT_DIR}/01-chat-empty.png`, fullPage: false });

    // Type a message to show the input area
    const input = page.locator('textarea, [contenteditable="true"], input[type="text"]').last();
    if (await input.isVisible()) {
      await input.fill("Analyze our Q1 marketing performance and suggest improvements for Q2");
    }
    await page.screenshot({ path: `${OUTPUT_DIR}/02-chat-typing.png`, fullPage: false });
  });

  test("02 — Agents library", async ({ page }) => {
    await page.goto("/agents");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000); // Let agent cards render
    await page.screenshot({ path: `${OUTPUT_DIR}/03-agents-library.png`, fullPage: false });
  });

  test("03 — Personas page", async ({ page }) => {
    await page.goto("/personas");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${OUTPUT_DIR}/04-personas.png`, fullPage: false });
  });

  test("04 — Crews page", async ({ page }) => {
    await page.goto("/crews");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${OUTPUT_DIR}/05-crews.png`, fullPage: false });
  });

  test("05 — Crew builder dialog", async ({ page }) => {
    await page.goto("/crews");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);

    // Click create crew button
    const createBtn = page.getByRole("button", { name: /create crew/i }).first();
    if (await createBtn.isVisible()) {
      await createBtn.click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${OUTPUT_DIR}/06-crew-builder.png`, fullPage: false });
    }
  });

  test("06 — Connections page", async ({ page }) => {
    await page.goto("/connections");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
    await page.screenshot({ path: `${OUTPUT_DIR}/07-connections.png`, fullPage: false });
  });

  test("07 — Settings - AI Providers", async ({ page }) => {
    await page.goto("/settings");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
    await page.screenshot({ path: `${OUTPUT_DIR}/08-settings-providers.png`, fullPage: false });
  });

  test("08 — Settings - Appearance (dark mode)", async ({ page }) => {
    await page.goto("/settings");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);

    // Navigate to Appearance tab
    const appearanceTab = page.getByText("Appearance");
    if (await appearanceTab.isVisible()) {
      await appearanceTab.click();
      await page.waitForTimeout(500);
    }
    await page.screenshot({ path: `${OUTPUT_DIR}/09-settings-appearance.png`, fullPage: false });
  });

  test("09 — Workshop/Workspace page", async ({ page }) => {
    await page.goto("/workspace");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
    await page.screenshot({ path: `${OUTPUT_DIR}/10-workspace.png`, fullPage: false });
  });

  test("10 — Chat with model selector visible", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    // Try to open model dropdown
    const modelBtn = page.locator('button:has-text("Model"), button:has-text("Gemma"), button:has-text("Qwen"), [aria-label*="model"]').first();
    if (await modelBtn.isVisible()) {
      await modelBtn.click();
      await page.waitForTimeout(300);
    }
    await page.screenshot({ path: `${OUTPUT_DIR}/11-chat-model-selector.png`, fullPage: false });
  });
});
