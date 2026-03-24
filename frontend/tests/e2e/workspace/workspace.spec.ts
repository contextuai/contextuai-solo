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
  test("DC-WORKSPACE-02: create a new project opens wizard", async ({ page }) => {
    await workspace.openWizard();

    const dialogVisible = await workspace.wizardDialog.isVisible().catch(() => false);
    expect(dialogVisible).toBeTruthy();

    // Should show step 1 with project name input
    await expect(workspace.projectNameInput).toBeVisible();
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
// Wizard Flow
// ==========================================================================

test.describe("Wizard Flow", () => {
  // DC-WORKSPACE-WIZ-01: Wizard shows step indicator with 3 steps
  test("DC-WORKSPACE-WIZ-01: wizard shows step indicator", async () => {
    await workspace.openWizard();

    const indicators = workspace.stepIndicators;
    const count = await indicators.count();
    expect(count).toBe(3);
  });

  // DC-WORKSPACE-WIZ-02: Step 1 shows project details form
  test("DC-WORKSPACE-WIZ-02: step 1 shows project details", async () => {
    await workspace.openWizard();

    await expect(workspace.projectNameInput).toBeVisible();
    await expect(workspace.descriptionInput).toBeVisible();
    await expect(workspace.useBlueprintButton).toBeVisible();
  });

  // DC-WORKSPACE-WIZ-03: Next button requires name on step 1
  test("DC-WORKSPACE-WIZ-03: next button requires name", async () => {
    await workspace.openWizard();

    // Next should be disabled without a name
    await expect(workspace.nextButton).toBeDisabled();

    // Fill name
    await workspace.projectNameInput.fill("Test Project");
    await expect(workspace.nextButton).toBeEnabled();
  });

  // DC-WORKSPACE-WIZ-04: Navigate to step 2 shows agent selection with search
  test("DC-WORKSPACE-WIZ-04: step 2 shows agent selection with search", async ({ page }) => {
    await workspace.openWizard();

    // Fill name and go to step 2
    await workspace.projectNameInput.fill("Agent Test");
    await workspace.nextButton.click();
    await page.waitForTimeout(300);

    // Should show agent search input
    await expect(workspace.agentSearchInput).toBeVisible();

    // Should show "Select Agents" label
    await expect(page.locator("text=Select Agents").first()).toBeVisible();

    // Should have agent items to select
    const agentCount = await workspace.agentItems.count();
    expect(agentCount).toBeGreaterThanOrEqual(1);
  });

  // DC-WORKSPACE-WIZ-05: Agent search filters the list
  test("DC-WORKSPACE-WIZ-05: agent search filters the list", async ({ page }) => {
    await workspace.openWizard();
    await workspace.goToStep(2);

    // Wait for agents to load
    await page.waitForTimeout(500);
    const initialCount = await workspace.agentItems.count();

    // Search for something that won't match
    await workspace.searchAgents("zzz_no_agent_matches_this_zzz");
    await page.waitForTimeout(300);

    const filteredCount = await workspace.agentItems.count();

    if (initialCount > 0) {
      expect(filteredCount).toBeLessThan(initialCount);
    }

    // Should show "No agents match" message
    if (filteredCount === 0) {
      await expect(page.getByText(/no agents match/i)).toBeVisible();
    }
  });

  // DC-WORKSPACE-WIZ-06: Next button on step 2 requires agent selection
  test("DC-WORKSPACE-WIZ-06: next requires agent selection on step 2", async ({ page }) => {
    await workspace.openWizard();

    // Go to step 2
    await workspace.projectNameInput.fill("Validation Test");
    await workspace.nextButton.click();
    await page.waitForTimeout(300);

    // Next should be disabled without selecting an agent
    await expect(workspace.nextButton).toBeDisabled();

    // Select an agent
    const agentCount = await workspace.agentItems.count();
    if (agentCount > 0) {
      await workspace.agentItems.first().click();
      await page.waitForTimeout(200);
      await expect(workspace.nextButton).toBeEnabled();
    }
  });

  // DC-WORKSPACE-WIZ-07: Navigate through all wizard steps to review
  test("DC-WORKSPACE-WIZ-07: navigate through all steps to review", async ({ page }) => {
    await workspace.openWizard();

    // Step 1: Fill details
    await workspace.projectNameInput.fill("Full Flow Test");
    await workspace.descriptionInput.fill("Testing the full wizard flow");
    await workspace.nextButton.click();
    await page.waitForTimeout(300);

    // Step 2: Select an agent
    await expect(workspace.agentSearchInput).toBeVisible();
    const agentCount = await workspace.agentItems.count();
    if (agentCount > 0) {
      await workspace.agentItems.first().click();
      await page.waitForTimeout(200);
    }
    await workspace.nextButton.click();
    await page.waitForTimeout(300);

    // Step 3: Review — should show project name and agents
    await expect(page.getByText("Full Flow Test")).toBeVisible();
    await expect(page.getByText("Testing the full wizard flow")).toBeVisible();
    await expect(workspace.submitButton).toBeVisible();
  });

  // DC-WORKSPACE-WIZ-08: Back button navigates backwards and preserves state
  test("DC-WORKSPACE-WIZ-08: back button navigates backwards", async ({ page }) => {
    await workspace.openWizard();

    // Go to step 2
    await workspace.projectNameInput.fill("Back Test");
    await workspace.nextButton.click();
    await page.waitForTimeout(300);

    // Verify on step 2
    await expect(workspace.agentSearchInput).toBeVisible();

    // Go back to step 1
    await workspace.backButton.click();
    await page.waitForTimeout(300);

    // Should see project name input with preserved value
    await expect(workspace.projectNameInput).toBeVisible();
    const nameValue = await workspace.projectNameInput.inputValue();
    expect(nameValue).toBe("Back Test");
  });

  // DC-WORKSPACE-WIZ-09: Cancel button closes the wizard
  test("DC-WORKSPACE-WIZ-09: cancel button closes wizard", async ({ page }) => {
    await workspace.openWizard();
    await expect(workspace.wizardDialog).toBeVisible();

    await workspace.cancelButton.click();

    // Wait for exit animation to complete
    await expect(workspace.wizardDialog).not.toBeVisible({ timeout: 3000 });
  });

  // DC-WORKSPACE-WIZ-10: Selected agents count badge updates
  test("DC-WORKSPACE-WIZ-10: selected agents count badge updates", async ({ page }) => {
    await workspace.openWizard();
    await workspace.goToStep(2);

    const agentCount = await workspace.agentItems.count();
    if (agentCount === 0) {
      test.skip();
      return;
    }

    // Select first agent
    await workspace.agentItems.first().click();
    await page.waitForTimeout(200);

    // Should show "(1 selected)"
    await expect(page.getByText("1 selected")).toBeVisible();

    // Select second agent if available
    if (agentCount >= 2) {
      await workspace.agentItems.nth(1).click();
      await page.waitForTimeout(200);
      await expect(page.getByText("2 selected")).toBeVisible();
    }
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
      const emptyStateBtn = page.locator("button").filter({ hasText: "New Brainstorm" }).first();
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

  // DC-WORKSPACE-07: New Brainstorm button opens wizard
  test("DC-WORKSPACE-07: new brainstorm button opens wizard", async ({ page }) => {
    const btn = page.locator("button", { hasText: "New Brainstorm" }).first();
    await expect(btn).toBeVisible();

    await btn.click();
    await page.waitForTimeout(500);

    // Should open wizard with step 1
    await expect(workspace.projectNameInput).toBeVisible();
    await expect(workspace.stepIndicators.first()).toBeVisible();
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
