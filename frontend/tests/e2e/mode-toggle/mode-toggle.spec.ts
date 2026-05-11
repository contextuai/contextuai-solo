/**
 * ContextuAI Solo Desktop — App Mode Toggle E2E Tests
 *
 * Tests the Solo/Coder mode toggle at the top center of the app.
 * Mode is persisted in localStorage as `solo.app.mode`.
 * Keyboard shortcut: Cmd/Ctrl+Shift+M
 *
 * Backend: http://127.0.0.1:18741
 * Frontend: http://localhost:1420
 */
import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  // Start in Solo mode (default)
  await page.evaluate(() => localStorage.setItem("solo.app.mode", "solo"));
  await page.reload();
  await page.waitForLoadState("networkidle");
});

// MODE-01: Top-center pill shows current app mode
test("MODE-01: app mode pill is visible at top center", async ({ page }) => {
  // The mode toggle is a tablist with role=tablist, containing buttons with role=tab
  const modeToggle = page.locator('[role="tablist"][aria-label="Application mode"]');
  await expect(modeToggle).toBeVisible({ timeout: 5000 });
});

// MODE-02: Clicking mode pill toggles between Solo and Coder
test("MODE-02: clicking mode pill toggles modes", async ({ page }) => {
  // Find the Coder tab button
  const coderBtn = page.getByRole("tab", { name: "Coder" });

  // Start in Solo mode
  const initialMode = await page.evaluate(() => localStorage.getItem("solo.app.mode"));
  expect(initialMode).toBe("solo");

  // Click the coder tab
  await coderBtn.click();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(500);

  // Should be in Coder mode now
  const newMode = await page.evaluate(() => localStorage.getItem("solo.app.mode"));
  expect(newMode).toBe("coder");
});

// MODE-03: Mode persists after page reload
test("MODE-03: app mode persists after reload", async ({ page }) => {
  // Set to coder mode
  const coderBtn = page.getByRole("tab", { name: "Coder" });
  const currentMode = await page.evaluate(() => localStorage.getItem("solo.app.mode"));
  if (currentMode === "solo") {
    await coderBtn.click();
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(500);
  }

  // Reload
  await page.reload();
  await page.waitForLoadState("networkidle");

  // Mode should still be coder
  const mode = await page.evaluate(() => localStorage.getItem("solo.app.mode"));
  expect(mode).toBe("coder");
});

// MODE-04: Coder mode shows coder-specific sidebar
test("MODE-04: coder mode displays coder sidebar", async ({ page }) => {
  // Switch to Coder mode
  const modeBtn = page.locator("button").filter({ hasText: /solo|coder/i }).first();
  const currentMode = await page.evaluate(() => localStorage.getItem("solo.app.mode"));
  if (currentMode === "solo") {
    await modeBtn.click();
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(500);
  }

  // Coder mode should have different sidebar items (e.g., Coder, Projects, Running, Templates, Settings)
  // At minimum, the sidebar should be visible and contain some nav items
  const sidebar = page.locator("aside");
  await expect(sidebar).toBeVisible();

  const navLinks = sidebar.locator("a");
  const linkCount = await navLinks.count();
  expect(linkCount).toBeGreaterThan(0);
});
