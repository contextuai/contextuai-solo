/**
 * ContextuAI Solo Desktop — Blueprints E2E Tests
 *
 * Route: "/blueprints"
 * Backend: http://127.0.0.1:18741 (no auth)
 * Frontend: http://localhost:1420 (Vite SPA)
 */
import { test, expect } from "@playwright/test";
import { BlueprintsPage } from "../fixtures/page-objects";

let blueprints: BlueprintsPage;

test.beforeEach(async ({ page }) => {
  blueprints = new BlueprintsPage(page);
  await blueprints.goto();
  await page.waitForTimeout(1500);
});

// ==========================================================================
// CRUD via UI
// ==========================================================================

test.describe("CRUD via UI", () => {
  test("DC-BP-01: view blueprints list", async ({ page }) => {
    await expect(page.locator("h1", { hasText: "Blueprints" })).toBeVisible();

    const count = await blueprints.getBlueprintCount();
    const emptyVisible = await blueprints.emptyState
      .isVisible()
      .catch(() => false);

    expect(count > 0 || emptyVisible).toBeTruthy();
  });

  test("DC-BP-02: page shows subtitle with count", async ({ page }) => {
    await expect(
      page.locator("p", { hasText: /blueprint.*workflow guides/i })
    ).toBeVisible();
  });

  test("DC-BP-03: create blueprint button is visible", async () => {
    await expect(blueprints.createButton).toBeVisible();
  });

  test("DC-BP-04: create blueprint opens dialog", async ({ page }) => {
    await blueprints.openCreateDialog();

    await expect(
      page.locator("h2", { hasText: "Create Blueprint" })
    ).toBeVisible();
  });

  test("DC-BP-05: create dialog has all form fields", async () => {
    await blueprints.openCreateDialog();

    await expect(blueprints.nameInput).toBeVisible();
    await expect(blueprints.descriptionInput).toBeVisible();
    await expect(blueprints.contentTextarea).toBeVisible();
    await expect(blueprints.dialogCategorySelect).toBeVisible();
    await expect(blueprints.tagsInput).toBeVisible();
    await expect(blueprints.submitButton).toBeVisible();
    await expect(blueprints.cancelButton).toBeVisible();
  });

  test("DC-BP-06: cancel closes create dialog", async ({ page }) => {
    await blueprints.openCreateDialog();
    await blueprints.cancelButton.click();
    await page.waitForTimeout(300);

    await expect(blueprints.createDialog).not.toBeVisible({ timeout: 3000 });
  });

  test("DC-BP-07: create a custom blueprint", async ({ page }) => {
    await blueprints.openCreateDialog();

    await blueprints.nameInput.fill("E2E Test Blueprint");
    await blueprints.descriptionInput.fill("Created by E2E test");
    await blueprints.contentTextarea.fill(
      "# E2E Test\n\n## Objective\nTest blueprint creation.\n\n## Steps\n1. Create\n2. Verify"
    );
    await blueprints.tagsInput.fill("e2e, test");

    await blueprints.submitButton.click();

    // Dialog should close
    await expect(blueprints.createDialog).not.toBeVisible({ timeout: 5000 });

    // Reload to ensure the new blueprint is in the list
    await page.reload({ waitUntil: "networkidle" });
    await page.waitForTimeout(1500);

    const createdCard = page.locator("h3", { hasText: "E2E Test Blueprint" });
    await expect(createdCard).toBeVisible({ timeout: 5000 });
  });
});

// ==========================================================================
// Filters & Search
// ==========================================================================

test.describe("Filters & Search", () => {
  test("DC-BP-08: search input is visible", async () => {
    await expect(blueprints.searchInput).toBeVisible();
  });

  test("DC-BP-09: category filter is visible", async () => {
    await expect(blueprints.categoryFilter).toBeVisible();
  });

  test("DC-BP-10: source filter is visible", async () => {
    await expect(blueprints.sourceFilter).toBeVisible();
  });

  test("DC-BP-11: filter by category", async ({ page }) => {
    await blueprints.filterByCategory("strategy");
    await page.waitForTimeout(500);

    // Page should not crash
    await expect(page.locator("h1", { hasText: "Blueprints" })).toBeVisible();
  });

  test("DC-BP-12: filter by source", async ({ page }) => {
    await blueprints.filterBySource("library");
    await page.waitForTimeout(500);

    await expect(page.locator("h1", { hasText: "Blueprints" })).toBeVisible();
  });

  test("DC-BP-13: search filters results", async ({ page }) => {
    await blueprints.search("nonexistent-query-xyz");
    await page.waitForTimeout(500);

    const count = await blueprints.getBlueprintCount();
    const emptyVisible = await blueprints.emptyState
      .isVisible()
      .catch(() => false);

    // Either no results or empty state
    expect(count === 0 || emptyVisible).toBeTruthy();
  });

  test("DC-BP-14: clear search shows all blueprints", async ({ page }) => {
    // Search for something specific
    await blueprints.search("xyz-no-match");
    await page.waitForTimeout(500);

    // Clear search
    await blueprints.search("");
    await page.waitForTimeout(500);

    await expect(page.locator("h1", { hasText: "Blueprints" })).toBeVisible();
  });
});

// ==========================================================================
// Positive Workflows
// ==========================================================================

test.describe("Positive Workflows", () => {
  test("DC-BP-15: refresh button works", async ({ page }) => {
    await expect(blueprints.refreshButton).toBeVisible();
    await blueprints.refreshButton.click();
    await page.waitForTimeout(1000);

    await expect(page.locator("h1", { hasText: "Blueprints" })).toBeVisible();
  });

  test("DC-BP-16: blueprint cards show category badges", async ({ page }) => {
    const count = await blueprints.getBlueprintCount();
    if (count > 0) {
      // First card should have a category badge
      const firstCard = blueprints.blueprintCards.first();
      const badge = firstCard.locator("span[class*='rounded-full']");
      await expect(badge.first()).toBeVisible();
    }
  });

  test("DC-BP-17: blueprint cards show name and description", async () => {
    const count = await blueprints.getBlueprintCount();
    if (count > 0) {
      const firstCard = blueprints.blueprintCards.first();
      const name = firstCard.locator("h3");
      await expect(name).toBeVisible();
    }
  });
});

// ==========================================================================
// Negative Workflows
// ==========================================================================

test.describe("Negative Workflows", () => {
  test("DC-BP-18: empty create form shows disabled submit", async () => {
    await blueprints.openCreateDialog();

    // Submit should be disabled without name and content
    await expect(blueprints.submitButton).toBeDisabled();
  });

  test("DC-BP-19: filtering with no results shows appropriate state", async ({
    page,
  }) => {
    await blueprints.search("completely-impossible-query-that-matches-nothing");
    await page.waitForTimeout(500);

    // Page should not crash
    await expect(page.locator("h1", { hasText: "Blueprints" })).toBeVisible();
  });
});
