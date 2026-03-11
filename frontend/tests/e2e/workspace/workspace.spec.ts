/**
 * ContextuAI Solo Desktop — Workspace E2E Tests
 *
 * Route: "/workspace" (Workshop page)
 * Backend: http://127.0.0.1:18741 (no auth)
 * Frontend: http://localhost:1420 (Vite SPA)
 */
import { test, expect } from "@playwright/test";
import { WorkspacePage } from "../fixtures/page-objects";

let workspace: WorkspacePage;

test.beforeEach(async ({ page }) => {
  workspace = new WorkspacePage(page);
  await workspace.goto();
  await page.waitForTimeout(1500);
});

// ==========================================================================
// CRUD via UI
// ==========================================================================

test.describe("CRUD via UI", () => {
  // DC-WORKSPACE-01: View workspace projects list
  test("DC-WORKSPACE-01: view workspace projects list", async ({ page }) => {
    await expect(page.locator("h1", { hasText: "Workshop" })).toBeVisible();

    const projectCount = await workspace.getProjectCount();
    const emptyVisible = await workspace.emptyState.isVisible().catch(() => false);

    expect(projectCount > 0 || emptyVisible).toBeTruthy();
  });

  // DC-WORKSPACE-02: Create a new project (open dialog)
  test("DC-WORKSPACE-02: create a new project opens dialog", async ({ page }) => {
    await workspace.newProjectButton.click();
    await page.waitForTimeout(500);

    const dialogVisible = await page
      .locator("[class*='fixed'], [role='dialog']")
      .first()
      .isVisible()
      .catch(() => false);

    expect(dialogVisible).toBeTruthy();
  });

  // DC-WORKSPACE-03: Filter projects by status
  test("DC-WORKSPACE-03: filter projects by status", async ({ page }) => {
    const filters = await workspace.statusFilters.all();
    expect(filters.length).toBeGreaterThanOrEqual(2);

    for (const filter of filters) {
      await filter.click();
      await page.waitForTimeout(300);
      await expect(page.locator("h1", { hasText: "Workshop" })).toBeVisible();
    }
  });

  // DC-WORKSPACE-04: Refresh projects list
  test("DC-WORKSPACE-04: refresh projects list", async ({ page }) => {
    await expect(workspace.refreshButton).toBeVisible();

    await workspace.refreshButton.click();
    await page.waitForTimeout(1000);

    await expect(page.locator("h1", { hasText: "Workshop" })).toBeVisible();
  });
});

// ==========================================================================
// Positive Workflows
// ==========================================================================

test.describe("Positive Workflows", () => {
  // DC-WORKSPACE-05: Empty state shows "Start your first workshop"
  test("DC-WORKSPACE-05: empty state shows start your first workshop", async ({ page }) => {
    const projectCount = await workspace.getProjectCount();

    if (projectCount === 0) {
      await expect(workspace.emptyState).toBeVisible();

      // Empty state should also have a "New Brainstorm" button
      const emptyStateBtn = page.locator("button", { hasText: "New Brainstorm" });
      await expect(emptyStateBtn).toBeVisible();
    } else {
      expect(projectCount).toBeGreaterThan(0);
    }
  });

  // DC-WORKSPACE-06: Status filter pills are interactive
  test("DC-WORKSPACE-06: status filter pills are interactive", async ({ page }) => {
    const filters = await workspace.statusFilters.all();

    for (const filter of filters) {
      await filter.click();
      await page.waitForTimeout(200);
      await expect(page.locator("h1", { hasText: "Workshop" })).toBeVisible();
    }
  });

  // DC-WORKSPACE-07: New Brainstorm button opens dialog
  test("DC-WORKSPACE-07: new brainstorm button opens dialog", async ({ page }) => {
    const btn = page.locator("button", { hasText: "New Brainstorm" }).first();
    await expect(btn).toBeVisible();

    await btn.click();
    await page.waitForTimeout(500);

    const dialogVisible = await page
      .locator("[class*='fixed'], [role='dialog']")
      .first()
      .isVisible()
      .catch(() => false);

    expect(dialogVisible).toBeTruthy();
  });
});

// ==========================================================================
// Negative Workflows
// ==========================================================================

test.describe("Negative Workflows", () => {
  // DC-WORKSPACE-08: Filter with no results shows appropriate state
  test("DC-WORKSPACE-08: filter with no results shows appropriate state", async ({ page }) => {
    await workspace.filterByStatus("Failed");

    const projectCount = await workspace.getProjectCount();

    // Page should not crash regardless of results
    await expect(page.locator("h1", { hasText: "Workshop" })).toBeVisible();
  });
});
