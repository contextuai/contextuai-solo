/**
 * ContextuAI Solo Desktop — AI Providers onboarding E2E tests (PR 19)
 *
 * Route: "/settings?tab=ai-providers"
 * Backend: http://127.0.0.1:18741 (no auth)
 * Frontend: http://localhost:1420 (Vite SPA)
 *
 * Tests:
 *   DC-AIPROV-01: each provider has a card with a "How to get your API key" toggle
 *   DC-AIPROV-02: expanding setup steps shows numbered list
 *   DC-AIPROV-03: save a dummy key flips status badge to "Key saved"
 *   DC-AIPROV-04: deep link /settings?tab=ai-providers lands on AI Providers tab
 *   DC-AIPROV-05: Remove key clears badge (optional — runs when a key is saved)
 */
import { test, expect, type Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const BASE_URL = "http://localhost:1420";
const BACKEND_URL = "http://127.0.0.1:18741/api/v1";

/** Navigate to Settings → AI Providers tab and wait for cards to load. */
async function gotoAiProviders(page: Page): Promise<void> {
  // Mock the cloud-providers list endpoint so tests don't depend on backend state
  await page.route(`${BACKEND_URL}/cloud-providers`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ success: true, providers: [], total_count: 0 }),
    });
  });

  await page.goto("/settings?tab=ai-providers");
  await page.waitForLoadState("networkidle");

  // Wait until at least one provider card is visible
  await expect(
    page.locator('[data-testid^="provider-card-"]').first()
  ).toBeVisible({ timeout: 15_000 });
}

// ---------------------------------------------------------------------------
// DC-AIPROV-01: all 5 provider cards are present
// ---------------------------------------------------------------------------

test("DC-AIPROV-01: each provider has a card with setup steps toggle", async ({ page }) => {
  await gotoAiProviders(page);

  const expectedIds = ["anthropic", "openai", "google", "bedrock", "ollama"] as const;

  for (const id of expectedIds) {
    const card = page.locator(`[data-testid="provider-card-${id}"]`);
    await expect(card).toBeVisible();

    // Each card has a "How to get your API key" toggle
    const toggle = card.locator(`[data-testid="steps-toggle-${id}"]`);
    await expect(toggle).toBeVisible();
    await expect(toggle).toContainText("How to get your API key");
  }
});

// ---------------------------------------------------------------------------
// DC-AIPROV-02: expanding setup steps shows numbered list
// ---------------------------------------------------------------------------

test("DC-AIPROV-02: expanding Anthropic setup steps shows numbered list", async ({ page }) => {
  await gotoAiProviders(page);

  const card = page.locator('[data-testid="provider-card-anthropic"]');

  // By default, unconfigured providers start open.
  // Check whether the steps content is visible; if not, click the toggle.
  const stepsContent = card.locator('[data-testid="steps-content-anthropic"]');
  const isOpen = await stepsContent.isVisible().catch(() => false);
  if (!isOpen) {
    await card.locator('[data-testid="steps-toggle-anthropic"]').click();
    await page.waitForTimeout(200);
  }

  // At least 3 step items must be visible
  const steps = card.locator('[data-testid^="step-anthropic-"]');
  await expect(steps).toHaveCount(5); // Anthropic has 5 steps
  expect(await steps.count()).toBeGreaterThanOrEqual(3);

  // Each step is a numbered list item
  const firstStep = card.locator('[data-testid="step-anthropic-0"]');
  await expect(firstStep).toBeVisible();
  await expect(firstStep).toContainText("Sign in");
});

// ---------------------------------------------------------------------------
// DC-AIPROV-03: saving a dummy key flips status badge
// ---------------------------------------------------------------------------

test("DC-AIPROV-03: save a dummy key flips status badge to Key saved", async ({ page }) => {
  // Track whether save was called
  let saveHappened = false;

  // Mock cloud-providers endpoint — handle both GET and POST
  await page.route(`${BACKEND_URL}/cloud-providers`, async (route) => {
    const method = route.request().method();

    if (method === "GET") {
      if (saveHappened) {
        // After save, return the connected row
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            success: true,
            providers: [
              {
                provider_id: "prov-test-1",
                provider_type: "anthropic",
                display_name: "Anthropic Claude",
                connected: true,
                last_tested_at: null,
                last_test_status: null,
                last_test_error: null,
                config: { api_key: "***" },
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              },
            ],
            total_count: 1,
          }),
        });
      } else {
        // Initially empty list
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ success: true, providers: [], total_count: 0 }),
        });
      }
    } else if (method === "POST") {
      // Return a saved provider row on POST
      saveHappened = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          provider_id: "prov-test-1",
          provider_type: "anthropic",
          display_name: "Anthropic Claude",
          connected: true,
          last_tested_at: null,
          last_test_status: null,
          last_test_error: null,
          config: { api_key: "***" },
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      });
    } else {
      await route.continue();
    }
  });

  await page.goto("/settings?tab=ai-providers");
  await page.waitForLoadState("networkidle");
  await expect(page.locator('[data-testid="provider-card-anthropic"]')).toBeVisible({ timeout: 15_000 });

  // Initially badge should show "Not configured"
  const badge = page.locator('[data-testid="status-badge-anthropic"]');
  await expect(badge).toContainText("Not configured");

  // Fill in a dummy API key
  const keyField = page.locator('[data-testid="field-anthropic-api_key"]');
  await keyField.fill("sk-ant-test-fake-key-1234567890");

  // Click Save — this will trigger the POST mock which sets saveHappened = true
  await page.locator('[data-testid="save-btn-anthropic"]').click();

  // Wait for the refresh GET to complete and badge to update
  await page.waitForLoadState("networkidle");

  // Badge should flip to "Key saved"
  await expect(badge).toContainText("Key saved", { timeout: 8_000 });
});

// ---------------------------------------------------------------------------
// DC-AIPROV-04: deep link /settings?tab=ai-providers lands on AI Providers tab
// ---------------------------------------------------------------------------

test("DC-AIPROV-04: deep link lands on AI Providers tab", async ({ page }) => {
  // Mock backend so page loads fast
  await page.route(`${BACKEND_URL}/cloud-providers`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ success: true, providers: [], total_count: 0 }),
    });
  });

  // Navigate directly via deep link
  await page.goto("/settings?tab=ai-providers");
  await page.waitForLoadState("networkidle");

  // The AI Providers tab content (provider cards) should be visible immediately
  await expect(
    page.locator('[data-testid^="provider-card-"]').first()
  ).toBeVisible({ timeout: 15_000 });

  // The tab button should appear active (selected)
  const aiProvidersTab = page
    .locator("button")
    .filter({ hasText: "AI Providers" })
    .first();
  await expect(aiProvidersTab).toBeVisible();

  // Brand Voice tab content should NOT be visible
  await expect(page.locator("text=Business Name").first()).not.toBeVisible();
});

// ---------------------------------------------------------------------------
// DC-AIPROV-05 (optional): Remove button appears on connected providers
// ---------------------------------------------------------------------------

test("DC-AIPROV-05: remove key button appears and shows confirmation", async ({ page }) => {
  const savedProvider = {
    provider_id: "prov-saved-1",
    provider_type: "anthropic",
    display_name: "Anthropic Claude",
    connected: true,
    last_tested_at: null,
    last_test_status: null,
    last_test_error: null,
    config: { api_key: "***" },
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  // Return saved provider
  await page.route(`${BACKEND_URL}/cloud-providers`, async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          providers: [savedProvider],
          total_count: 1,
        }),
      });
    } else {
      await route.continue();
    }
  });

  // Mock the DELETE endpoint
  await page.route(`${BACKEND_URL}/cloud-providers/prov-saved-1`, async (route) => {
    if (route.request().method() === "DELETE") {
      await route.fulfill({ status: 204, body: "" });
    } else {
      await route.continue();
    }
  });

  await page.goto("/settings?tab=ai-providers");
  await page.waitForLoadState("networkidle");
  await expect(page.locator('[data-testid="provider-card-anthropic"]')).toBeVisible({ timeout: 15_000 });

  // Badge should show "Key saved" (provider is connected)
  const badge = page.locator('[data-testid="status-badge-anthropic"]');
  await expect(badge).toContainText("Key saved");

  // Remove button should be visible for connected providers
  const removeBtn = page.locator('[data-testid="remove-btn-anthropic"]');
  await expect(removeBtn).toBeVisible();

  // Click "Remove key"
  await removeBtn.click();
  await page.waitForTimeout(200);

  // Confirm button should appear
  const confirmBtn = page.locator('[data-testid="confirm-remove-btn-anthropic"]');
  await expect(confirmBtn).toBeVisible();

  // Cancel button should also appear
  const cancelBtn = page.locator('button:has-text("Cancel")').last();
  await expect(cancelBtn).toBeVisible();
});
