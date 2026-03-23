/**
 * ContextuAI Solo Desktop — Personas E2E Tests
 *
 * Route: "/personas"
 * Backend: http://127.0.0.1:18741 (no auth)
 * Frontend: http://localhost:1420 (Vite SPA)
 */
import { test, expect } from "@playwright/test";
import { PersonasPage } from "../fixtures/page-objects";

let personas: PersonasPage;

test.beforeEach(async ({ page }) => {
  personas = new PersonasPage(page);
  await personas.goto();
  await page.waitForTimeout(1500);
});

// ==========================================================================
// CRUD via UI
// ==========================================================================

test.describe("CRUD via UI", () => {
  test("DC-PERSONA-01: view all personas", async ({ page }) => {
    const cardCount = await personas.personaCards.count();
    const emptyVisible = await page.locator("text=No personas yet").isVisible().catch(() => false);
    expect(cardCount > 0 || emptyVisible).toBeTruthy();
  });

  test("DC-PERSONA-02: create a new persona with all fields", async () => {
    const testName = `E2E Test Persona ${Date.now()}`;
    await personas.createPersona({
      name: testName,
      description: "An E2E test persona for automated testing",
      category: "Technical",
      systemPrompt: "You are a helpful test assistant.",
    });
    await personas.page.waitForTimeout(1000);
    const names = await personas.getPersonaNames();
    expect(names).toContain(testName);
  });

  test("DC-PERSONA-03: edit an existing persona", async ({ page }) => {
    const originalName = `Edit Test ${Date.now()}`;
    await personas.createPersona({ name: originalName });
    await page.waitForTimeout(1000);

    await personas.editPersona(originalName, {
      description: "Updated description via E2E test",
    });
    await page.waitForTimeout(500);

    await personas.goto();
    await page.waitForTimeout(1000);

    const card = personas.personaCards.filter({ hasText: originalName });
    const cardText = await card.textContent();
    expect(cardText).toContain("Updated description");
  });

  test("DC-PERSONA-04: delete a persona with confirmation", async ({ page }) => {
    const deleteName = `Delete Test ${Date.now()}`;
    await personas.createPersona({ name: deleteName });
    await page.waitForTimeout(1000);

    const initialNames = await personas.getPersonaNames();
    expect(initialNames).toContain(deleteName);

    await personas.deletePersona(deleteName);
    await page.waitForTimeout(1000);

    const afterNames = await personas.getPersonaNames();
    expect(afterNames).not.toContain(deleteName);
  });

  test("DC-PERSONA-05: search personas by name", async ({ page }) => {
    const uniqueName = `SearchTest${Date.now()}`;
    await personas.createPersona({ name: uniqueName });

    await personas.goto();
    await page.waitForTimeout(1000);

    await personas.searchPersonas(uniqueName);
    await page.waitForTimeout(500);

    const names = await personas.getPersonaNames();
    expect(names.length).toBeGreaterThanOrEqual(1);
    expect(names).toContain(uniqueName);

    await personas.searchPersonas("");
    await page.waitForTimeout(500);
    const allCount = await personas.personaCards.count();
    expect(allCount).toBeGreaterThan(1);
  });
});

// ==========================================================================
// Wizard Flow
// ==========================================================================

test.describe("Wizard Flow", () => {
  test("DC-PERSONA-WIZ-01: wizard shows step indicator", async ({ page }) => {
    await personas.createButton.click();
    await expect(personas.typeSearchInput).toBeVisible({ timeout: 5_000 });

    const stepIndicators = page.locator(".fixed.inset-0 .rounded-full.w-7.h-7");
    await expect(stepIndicators).toHaveCount(2);
  });

  test("DC-PERSONA-WIZ-02: step 1 shows type selection grid", async ({ page }) => {
    await personas.createButton.click();
    await expect(personas.typeSearchInput).toBeVisible({ timeout: 5_000 });

    await expect(page.locator("text=Select Persona Type")).toBeVisible();

    const typeCards = page.locator(".fixed.inset-0 .grid button");
    const count = await typeCards.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test("DC-PERSONA-WIZ-03: clicking type card goes to step 2", async ({ page }) => {
    await personas.createButton.click();
    await expect(personas.typeSearchInput).toBeVisible({ timeout: 5_000 });

    const typeCards = page.locator(".fixed.inset-0 .grid button");
    const count = await typeCards.count();
    if (count > 0) {
      await typeCards.first().click();
      await page.waitForTimeout(300);
      await expect(personas.formName).toBeVisible({ timeout: 3_000 });
    }
  });

  test("DC-PERSONA-WIZ-04: next button goes to step 2", async ({ page }) => {
    await personas.createButton.click();
    await expect(personas.typeSearchInput).toBeVisible({ timeout: 5_000 });

    await personas.nextButton.click();
    await page.waitForTimeout(300);
    await expect(personas.formName).toBeVisible({ timeout: 3_000 });
  });

  test("DC-PERSONA-WIZ-05: back button returns to step 1", async ({ page }) => {
    await personas.createButton.click();
    await expect(personas.typeSearchInput).toBeVisible({ timeout: 5_000 });

    await personas.nextButton.click();
    await expect(personas.formName).toBeVisible({ timeout: 3_000 });

    await personas.backButton.click();
    await page.waitForTimeout(300);
    await expect(personas.typeSearchInput).toBeVisible({ timeout: 3_000 });
  });

  test("DC-PERSONA-WIZ-06: type search filters type cards", async ({ page }) => {
    await personas.createButton.click();
    await expect(personas.typeSearchInput).toBeVisible({ timeout: 5_000 });

    const typeCards = page.locator(".fixed.inset-0 .grid button");
    const initialCount = await typeCards.count();

    await personas.typeSearchInput.fill("zzz_no_match_zzz");
    await page.waitForTimeout(300);

    const filteredCount = await typeCards.count();
    expect(filteredCount).toBeLessThan(initialCount);
  });
});

// ==========================================================================
// Positive Workflows
// ==========================================================================

test.describe("Positive Workflows", () => {
  test("DC-PERSONA-06: create persona with system prompt", async ({ page }) => {
    const name = `Prompt Test ${Date.now()}`;
    await personas.createPersona({
      name,
      description: "TypeScript expert persona",
      systemPrompt: "You are an expert TypeScript developer.",
    });
    await page.waitForTimeout(1000);

    const card = personas.personaCards.filter({ hasText: name });
    const cardContent = await card.textContent();
    expect(cardContent).toContain("TypeScript expert persona");
  });

  test("DC-PERSONA-07: filter personas by category", async ({ page }) => {
    await personas.createPersona({ name: `Tech ${Date.now()}`, category: "Technical" });
    await page.waitForTimeout(500);
    await personas.createPersona({ name: `Biz ${Date.now()}`, category: "Business" });
    await page.waitForTimeout(1000);

    await personas.filterByCategory("Technical");
    const techCount = await personas.personaCards.count();

    await personas.filterByCategory("All");
    const totalCount = await personas.personaCards.count();
    expect(totalCount).toBeGreaterThanOrEqual(techCount);
  });

  test("DC-PERSONA-08: wizard step 1 loads persona types from backend", async ({ page }) => {
    await personas.createButton.click();
    await expect(personas.typeSearchInput).toBeVisible({ timeout: 5_000 });

    const typeCards = page.locator(".fixed.inset-0 .grid button");
    const count = await typeCards.count();
    expect(count).toBeGreaterThanOrEqual(6);
  });

  test("DC-PERSONA-09: created persona appears in chat persona selector", async ({ page }) => {
    const name = `ChatVisible ${Date.now()}`;
    await personas.createPersona({ name });
    await page.waitForTimeout(1000);

    await page.goto("/");
    await page.waitForLoadState("networkidle");

    const personaSelector = page.locator("button").filter({ hasText: /persona/i }).first();
    await personaSelector.click();
    await page.waitForTimeout(500);

    const dropdown = page.locator(".absolute.bottom-full");
    await expect(dropdown.locator("button").filter({ hasText: name })).toBeVisible();
  });

  test("DC-PERSONA-10: persona card shows description and type", async ({ page }) => {
    const name = `Detailed ${Date.now()}`;
    await personas.createPersona({
      name,
      description: "This is a detailed test description",
      category: "Creative",
    });
    await page.waitForTimeout(1000);

    const card = personas.personaCards.filter({ hasText: name });
    const cardText = await card.textContent();
    expect(cardText).toContain("This is a detailed test description");
    expect(cardText).toMatch(/Creative|generic/i);
  });
});

// ==========================================================================
// Negative Workflows
// ==========================================================================

test.describe("Negative Workflows", () => {
  test("DC-PERSONA-11: cannot create persona without name", async ({ page }) => {
    await personas.createButton.click();
    await expect(personas.typeSearchInput).toBeVisible({ timeout: 5_000 });

    await personas.nextButton.click();
    await expect(personas.formName).toBeVisible({ timeout: 5_000 });

    const nameValue = await personas.formName.inputValue();
    expect(nameValue).toBe("");
    await expect(personas.formSaveButton).toBeDisabled();

    await personas.formDescription.fill("Description without name");
    await expect(personas.formSaveButton).toBeDisabled();
  });

  test("DC-PERSONA-12: cancel create wizard discards changes", async ({ page }) => {
    const beforeCount = await personas.personaCards.count();

    await personas.createButton.click();
    await expect(personas.typeSearchInput).toBeVisible({ timeout: 5_000 });

    await personas.nextButton.click();
    await expect(personas.formName).toBeVisible({ timeout: 5_000 });
    await personas.formName.fill("Should Not Be Created");

    await personas.formCancelButton.click();
    await expect(personas.formName).toBeHidden();

    const afterCount = await personas.personaCards.count();
    expect(afterCount).toBe(beforeCount);
  });

  test("DC-PERSONA-13: cancel delete dialog keeps persona", async ({ page }) => {
    const name = `KeepMe ${Date.now()}`;
    await personas.createPersona({ name });
    await page.waitForTimeout(1000);

    const beforeCount = await personas.personaCards.count();

    const card = personas.personaCards.filter({ hasText: name }).first();
    await card.scrollIntoViewIfNeeded();
    const deleteBtn = card.locator("button").last();
    await deleteBtn.click({ force: true });

    await expect(personas.deleteDialog).toBeVisible();
    await personas.deleteDialog.getByRole("button", { name: "Cancel" }).click();
    await page.waitForTimeout(500);

    const afterCount = await personas.personaCards.count();
    expect(afterCount).toBe(beforeCount);
  });
});
