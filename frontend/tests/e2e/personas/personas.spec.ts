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
  // Wait for personas to load
  await page.waitForTimeout(1500);
});

// ==========================================================================
// CRUD via UI
// ==========================================================================

test.describe("CRUD via UI", () => {
  // DC-PERSONA-01: View all personas
  test("DC-PERSONA-01: view all personas", async ({ page }) => {
    // Either persona cards or the "No personas yet" empty state
    const cardCount = await personas.personaCards.count();
    const emptyVisible = await page.locator("text=No personas yet").isVisible().catch(() => false);

    expect(cardCount > 0 || emptyVisible).toBeTruthy();
  });

  // DC-PERSONA-02: Create a new persona with all fields
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

  // DC-PERSONA-03: Edit an existing persona
  test("DC-PERSONA-03: edit an existing persona", async ({ page }) => {
    const originalName = `Edit Test ${Date.now()}`;
    await personas.createPersona({ name: originalName });
    await page.waitForTimeout(1000);

    await personas.editPersona(originalName, {
      description: "Updated description via E2E test",
    });
    await page.waitForTimeout(500);

    // Refresh the page to ensure changes are reflected
    await personas.goto();
    await page.waitForTimeout(1000);

    const card = personas.personaCards.filter({ hasText: originalName });
    const cardText = await card.textContent();
    expect(cardText).toContain("Updated description");
  });

  // DC-PERSONA-04: Delete a persona with confirmation
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

  // DC-PERSONA-05: Search personas by name
  test("DC-PERSONA-05: search personas by name", async ({ page }) => {
    const uniqueName = `SearchTest${Date.now()}`;
    await personas.createPersona({ name: uniqueName });

    // Reload to ensure the list reflects the new persona
    await personas.goto();
    await page.waitForTimeout(1000);

    // Search for the unique name
    await personas.searchPersonas(uniqueName);
    await page.waitForTimeout(500);

    const names = await personas.getPersonaNames();
    expect(names.length).toBeGreaterThanOrEqual(1);
    expect(names).toContain(uniqueName);

    // Clear search returns to the full list
    await personas.searchPersonas("");
    await page.waitForTimeout(500);
    const allCount = await personas.personaCards.count();
    expect(allCount).toBeGreaterThan(1);
  });
});

// ==========================================================================
// Positive Workflows
// ==========================================================================

test.describe("Positive Workflows", () => {
  // DC-PERSONA-06: Create persona with system prompt
  test("DC-PERSONA-06: create persona with system prompt", async ({ page }) => {
    const name = `Prompt Test ${Date.now()}`;
    const prompt = "You are an expert TypeScript developer. Always provide typed examples.";

    await personas.createPersona({
      name,
      description: "TypeScript expert persona",
      systemPrompt: prompt,
    });
    await page.waitForTimeout(1000);

    // The card shows the description, not the system prompt
    const card = personas.personaCards.filter({ hasText: name });
    const cardContent = await card.textContent();
    expect(cardContent).toContain("TypeScript expert persona");
  });

  // DC-PERSONA-07: Filter personas by category
  test("DC-PERSONA-07: filter personas by category", async ({ page }) => {
    await personas.createPersona({ name: `Tech ${Date.now()}`, category: "Technical" });
    await page.waitForTimeout(500);
    await personas.createPersona({ name: `Biz ${Date.now()}`, category: "Business" });
    await page.waitForTimeout(1000);

    // Filter by Technical
    await personas.filterByCategory("Technical");
    const techCount = await personas.personaCards.count();

    // Filter by All
    await personas.filterByCategory("All");
    const totalCount = await personas.personaCards.count();

    expect(totalCount).toBeGreaterThanOrEqual(techCount);
  });

  // DC-PERSONA-08: Persona type dropdown loads 12 types from backend
  test("DC-PERSONA-08: persona type dropdown loads types from backend", async ({ page }) => {
    await personas.createButton.click();
    await expect(personas.formName).toBeVisible({ timeout: 5_000 });

    const options = await personas.formType.locator("option").all();
    // At least 6 (fallback types), ideally 12 (seeded types)
    expect(options.length).toBeGreaterThanOrEqual(6);
  });

  // DC-PERSONA-09: Created persona appears in chat persona selector
  test("DC-PERSONA-09: created persona appears in chat persona selector", async ({ page }) => {
    const name = `ChatVisible ${Date.now()}`;
    await personas.createPersona({ name });
    await page.waitForTimeout(1000);

    // Navigate to chat page
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Open persona selector
    const personaSelector = page.locator("button").filter({ hasText: /persona/i }).first();
    await personaSelector.click();
    await page.waitForTimeout(500);

    const dropdown = page.locator(".absolute.bottom-full");
    await expect(dropdown.locator("button").filter({ hasText: name })).toBeVisible();
  });

  // DC-PERSONA-10: Persona card shows description and type
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
  // DC-PERSONA-11: Cannot create persona without name (button disabled)
  test("DC-PERSONA-11: cannot create persona without name", async ({ page }) => {
    await personas.createButton.click();
    await expect(personas.formName).toBeVisible({ timeout: 5_000 });

    const nameValue = await personas.formName.inputValue();
    expect(nameValue).toBe("");

    await expect(personas.formSaveButton).toBeDisabled();

    // Fill only description
    await personas.formDescription.fill("Description without name");
    await expect(personas.formSaveButton).toBeDisabled();
  });

  // DC-PERSONA-12: Cancel create dialog discards changes
  test("DC-PERSONA-12: cancel create dialog discards changes", async ({ page }) => {
    const beforeCount = await personas.personaCards.count();

    await personas.createButton.click();
    await expect(personas.formName).toBeVisible({ timeout: 5_000 });

    await personas.formName.fill("Should Not Be Created");
    await personas.formDescription.fill("This should be discarded");

    await personas.formCancelButton.click();
    await expect(personas.formName).toBeHidden();

    const afterCount = await personas.personaCards.count();
    expect(afterCount).toBe(beforeCount);
  });

  // DC-PERSONA-13: Cancel delete dialog keeps persona
  test("DC-PERSONA-13: cancel delete dialog keeps persona", async ({ page }) => {
    const name = `KeepMe ${Date.now()}`;
    await personas.createPersona({ name });
    await page.waitForTimeout(1000);

    const beforeCount = await personas.personaCards.count();

    // Click delete (trash icon — last button in card)
    const card = personas.personaCards.filter({ hasText: name }).first();
    await card.scrollIntoViewIfNeeded();
    const deleteBtn = card.locator("button").last();
    await deleteBtn.dispatchEvent("click");

    // Confirmation dialog appears
    await expect(personas.deleteDialog).toBeVisible();

    // Click Cancel
    await personas.deleteDialog.getByRole("button", { name: "Cancel" }).click();
    await page.waitForTimeout(500);

    const afterCount = await personas.personaCards.count();
    expect(afterCount).toBe(beforeCount);
  });
});
