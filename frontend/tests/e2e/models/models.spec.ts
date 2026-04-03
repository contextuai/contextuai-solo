/**
 * ContextuAI Solo Desktop — Model Hub E2E Tests
 *
 * Route: "/models" (Model Hub)
 * Backend: http://127.0.0.1:18741 (no auth)
 * Frontend: http://localhost:1420 (Vite SPA)
 */
import { test, expect } from "@playwright/test";
import { ModelsPage } from "../fixtures/page-objects";

let models: ModelsPage;

test.beforeEach(async ({ page }) => {
  models = new ModelsPage(page);
  await models.goto();
  await page.waitForTimeout(2000);
});

// ==========================================================================
// Model Hub — Catalog & Recommended
// ==========================================================================

test.describe("Model Hub catalog", () => {
  // DC-MODEL-01: Model Hub page loads with heading and models
  test("DC-MODEL-01: page loads with heading and catalog models", async () => {
    await expect(models.heading).toBeVisible();
    const names = await models.getModelNames();
    expect(names.length).toBeGreaterThan(0);
  });

  // DC-MODEL-02: Recommended section shows recommended models
  test("DC-MODEL-02: recommended section shows recommended models", async () => {
    await expect(models.recommendedSection).toBeVisible();
    const recommended = await models.getRecommendedModelNames();
    expect(recommended.length).toBeGreaterThanOrEqual(1);
  });

  // DC-MODEL-03: Search filters models
  test("DC-MODEL-03: search filters models", async ({ page }) => {
    await models.searchFor("gemma");
    const names = await models.getModelNames();
    expect(names.length).toBeGreaterThan(0);
    for (const name of names) {
      expect(name.toLowerCase()).toContain("gemma");
    }
  });

  // DC-MODEL-04: Vision category filter shows multimodal models
  test("DC-MODEL-04: vision filter shows multimodal models", async ({ page }) => {
    await models.clickCategory("Vision");
    const names = await models.getModelNames();
    expect(names.length).toBeGreaterThan(0);
    // Qwen 3.5 models support vision
    const hasVisionModel = names.some((n) => n.includes("Qwen 3.5"));
    expect(hasVisionModel).toBe(true);
  });

  // DC-MODEL-05: Category filter hides recommended section
  test("DC-MODEL-05: category filter hides recommended section", async () => {
    await models.clickCategory("Coding");
    await expect(models.recommendedSection).not.toBeVisible();
  });
});
