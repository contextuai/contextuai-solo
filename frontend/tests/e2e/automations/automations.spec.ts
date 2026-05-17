/**
 * ContextuAI Solo Desktop — Automations E2E Tests
 *
 * Route: "/automations"
 * Backend: http://127.0.0.1:18741 (no auth)
 * Frontend: http://localhost:1420 (Vite SPA)
 *
 * Smoke tests for the new Automations page (Phase 4 addition).
 */
import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/automations");
  await page.waitForLoadState("networkidle");
});

// DC-AUTO-01: Automations page loads with correct heading
test("DC-AUTO-01: automations page loads with correct heading", async ({ page }) => {
  await expect(page.locator("h2", { hasText: "Automations" })).toBeVisible();
});

// DC-AUTO-02: Empty state or list is visible
test("DC-AUTO-02: automations list or empty state visible", async ({ page }) => {
  const emptyState = page.locator("text=/no automations|create your first/i").isVisible().catch(() => false);
  const listVisible = page.locator(".grid.gap-3 > div").count().then((c) => c > 0);

  const hasContent = (await emptyState) || (await listVisible);
  expect(hasContent).toBeTruthy();
});

// DC-AUTO-03: Create button is visible
test("DC-AUTO-03: create button is visible", async ({ page }) => {
  const createBtn = page.getByRole("button", { name: /new/i }).filter({ hasText: "New" }).first();
  await expect(createBtn).toBeVisible();
});
