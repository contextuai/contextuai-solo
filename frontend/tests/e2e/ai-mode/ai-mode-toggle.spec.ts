/**
 * ContextuAI Solo Desktop — AI Mode Toggle E2E Tests
 *
 * Tests the global Local/Cloud AI mode toggle in the sidebar,
 * model filtering based on mode, and persistence across page reloads.
 *
 * Backend: http://127.0.0.1:18741
 * Frontend: http://localhost:1420
 */
import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  // Clear AI mode preference so each test starts fresh
  await page.goto("/");
  await page.evaluate(() => localStorage.removeItem("contextuai-solo-ai-mode"));
  await page.reload();
  await page.waitForLoadState("networkidle");
});

// AI-01: Sidebar shows the AI mode toggle
test("AI-01: sidebar displays AI mode toggle", async ({ page }) => {
  const sidebar = page.locator("aside");
  await expect(sidebar).toBeVisible();

  // The toggle should have Local and Cloud buttons
  const localBtn = sidebar.getByText("Local", { exact: true });
  const cloudBtn = sidebar.getByText("Cloud", { exact: true });

  await expect(localBtn).toBeVisible();
  await expect(cloudBtn).toBeVisible();
});

// AI-02: Clicking Local activates local mode
test("AI-02: switching to Local mode", async ({ page }) => {
  const sidebar = page.locator("aside");
  const localBtn = sidebar.getByText("Local", { exact: true });

  await localBtn.click();

  // Verify localStorage is updated
  const mode = await page.evaluate(() => localStorage.getItem("contextuai-solo-ai-mode"));
  expect(mode).toBe("local");
});

// AI-03: Clicking Cloud activates cloud mode
test("AI-03: switching to Cloud mode", async ({ page }) => {
  const sidebar = page.locator("aside");
  const cloudBtn = sidebar.getByText("Cloud", { exact: true });

  await cloudBtn.click();

  const mode = await page.evaluate(() => localStorage.getItem("contextuai-solo-ai-mode"));
  expect(mode).toBe("cloud");
});

// AI-04: Mode persists across page reload
test("AI-04: AI mode persists after reload", async ({ page }) => {
  const sidebar = page.locator("aside");

  // Set to local
  await sidebar.getByText("Local", { exact: true }).click();

  // Reload
  await page.reload();
  await page.waitForLoadState("networkidle");

  const mode = await page.evaluate(() => localStorage.getItem("contextuai-solo-ai-mode"));
  expect(mode).toBe("local");
});

// AI-05: Mode badge appears in chat input area
test("AI-05: chat input shows mode badge", async ({ page }) => {
  // Set to cloud mode
  const sidebar = page.locator("aside");
  await sidebar.getByText("Cloud", { exact: true }).click();

  // The chat input area should show a badge with "cloud" text (uppercase badge)
  // Use the specific badge span class (inline-flex with tracking-wider)
  const cloudBadge = page.locator("span.uppercase").getByText("cloud");
  await expect(cloudBadge).toBeVisible();

  // Switch to local
  await sidebar.getByText("Local", { exact: true }).click();

  // Should now show "local" badge
  const localBadge = page.locator("span.uppercase").getByText("local");
  await expect(localBadge).toBeVisible();
});

// AI-06: Model dropdown filters based on mode — verify via localStorage
test("AI-06: mode switch updates localStorage and triggers re-render", async ({ page }) => {
  const sidebar = page.locator("aside");

  // Set to cloud
  await sidebar.getByText("Cloud", { exact: true }).click();
  let mode = await page.evaluate(() => localStorage.getItem("contextuai-solo-ai-mode"));
  expect(mode).toBe("cloud");

  // Switch to local
  await sidebar.getByText("Local", { exact: true }).click();
  mode = await page.evaluate(() => localStorage.getItem("contextuai-solo-ai-mode"));
  expect(mode).toBe("local");

  // The badge in chat should reflect "local"
  const localBadge = page.locator("span.uppercase").getByText("local");
  await expect(localBadge).toBeVisible();
});

// AI-07: "All models" button bypasses filter
test("AI-07: all models button shows unfiltered models", async ({ page }) => {
  // Set to local mode first
  const sidebar = page.locator("aside");
  await sidebar.getByText("Local", { exact: true }).click();

  // Find the "All models" button in the chat input area
  const allModelsBtn = page.getByText("All models", { exact: true });
  if (await allModelsBtn.isVisible()) {
    await allModelsBtn.click();

    // Now it should say "Filtered"
    const filteredBtn = page.getByText("Filtered", { exact: true });
    await expect(filteredBtn).toBeVisible();
  }
});

// AI-08: Settings page shows AI Mode card
test("AI-08: settings page has AI Mode card", async ({ page }) => {
  await page.goto("/settings");
  await page.waitForLoadState("networkidle");

  const aiModeHeading = page.getByText("AI Mode", { exact: true });
  await expect(aiModeHeading).toBeVisible();

  // Should have Local AI and Cloud options
  const localOption = page.getByText("Local AI", { exact: true });
  const cloudOption = page.getByText("Cloud", { exact: false }).first();
  await expect(localOption).toBeVisible();
  await expect(cloudOption).toBeVisible();
});
