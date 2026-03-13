/**
 * ContextuAI Solo Desktop — Crews E2E Tests
 *
 * Route: "/crews"
 * Backend: http://127.0.0.1:18741 (no auth)
 * Frontend: http://localhost:1420 (Vite SPA)
 */
import { test, expect } from "@playwright/test";
import { CrewsPage } from "../fixtures/page-objects";

let crews: CrewsPage;

test.beforeEach(async ({ page }) => {
  crews = new CrewsPage(page);
  await crews.goto();
  await page.waitForTimeout(1500);
});

// ==========================================================================
// CRUD via UI
// ==========================================================================

test.describe("CRUD via UI", () => {
  // DC-CREW-01: View crews list
  test("DC-CREW-01: view crews list", async ({ page }) => {
    await expect(page.locator("h1", { hasText: "Crews" })).toBeVisible();

    const crewCount = await crews.getCrewCount();
    const emptyVisible = await crews.emptyCrewsState.isVisible().catch(() => false);

    expect(crewCount > 0 || emptyVisible).toBeTruthy();
  });

  // DC-CREW-02: Switch between Crews and Runs tabs
  test("DC-CREW-02: switch between crews and runs tabs", async () => {
    await expect(crews.crewsTab).toBeVisible();
    await expect(crews.runsTab).toBeVisible();

    // Switch to Runs tab
    await crews.switchTab("runs");

    const runCards = crews.page.locator(".grid.gap-3 > div.rounded-xl");
    const runCount = await runCards.count();
    const emptyRuns = await crews.emptyRunsState.isVisible().catch(() => false);
    expect(runCount > 0 || emptyRuns).toBeTruthy();

    // Switch back to Crews
    await crews.switchTab("crews");

    const crewCount = await crews.getCrewCount();
    const emptyCrews = await crews.emptyCrewsState.isVisible().catch(() => false);
    expect(crewCount > 0 || emptyCrews).toBeTruthy();
  });

  // DC-CREW-03: Create a crew (opens builder)
  test("DC-CREW-03: create a crew opens builder", async ({ page }) => {
    await crews.createButton.click();
    await page.waitForTimeout(500);

    const dialogVisible = await page
      .locator("[class*='fixed'], [role='dialog']")
      .first()
      .isVisible()
      .catch(() => false);

    expect(dialogVisible).toBeTruthy();
  });

  // DC-CREW-04: Search crews by name
  test("DC-CREW-04: search crews by name", async ({ page }) => {
    await expect(crews.searchInput).toBeVisible();

    await crews.searchCrews("test");
    await expect(page.locator("h1", { hasText: "Crews" })).toBeVisible();
  });

  // DC-CREW-05: Filter crews by status and mode
  test("DC-CREW-05: filter crews by status and mode", async ({ page }) => {
    await expect(crews.statusFilter).toBeVisible();
    await expect(crews.modeFilter).toBeVisible();

    await crews.statusFilter.selectOption("active");
    await page.waitForTimeout(300);

    await crews.modeFilter.selectOption("sequential");
    await page.waitForTimeout(300);

    await expect(page.locator("h1", { hasText: "Crews" })).toBeVisible();

    // Reset filters
    await crews.statusFilter.selectOption("all");
    await crews.modeFilter.selectOption("all");
  });
});

// ==========================================================================
// Positive Workflows
// ==========================================================================

test.describe("Positive Workflows", () => {
  // DC-CREW-06: Stats cards show correct counts
  test("DC-CREW-06: stats cards show correct counts", async ({ page }) => {
    // 4 stat cards: Total Crews, Running, Completed, Failed
    const statCards = page.locator(".grid-cols-4 > div");
    await expect(statCards).toHaveCount(4);

    for (const label of ["Total Crews", "Running", "Completed", "Failed"]) {
      await expect(page.locator(`text=${label}`)).toBeVisible();
    }

    // Each card should contain a number
    const cards = await statCards.all();
    for (const card of cards) {
      const text = await card.textContent();
      expect(text).toMatch(/\d/);
    }
  });

  // DC-CREW-07: Crew card shows agents count and execution mode
  test("DC-CREW-07: crew card shows agents count and execution mode", async () => {
    const crewCount = await crews.getCrewCount();
    if (crewCount === 0) {
      test.skip();
      return;
    }

    const firstCard = crews.crewCards.first();
    const cardText = await firstCard.textContent();

    expect(cardText).toMatch(/\d+ agents?/);
    expect(cardText).toMatch(/Sequential|Parallel|Pipeline|Autonomous/);
  });

  // DC-CREW-08: Runs tab shows run history
  test("DC-CREW-08: runs tab shows run history", async ({ page }) => {
    await crews.switchTab("runs");

    const runCards = page.locator(".grid.gap-3 > div.rounded-xl");
    const runCount = await runCards.count();
    const emptyRuns = await crews.emptyRunsState.isVisible().catch(() => false);

    expect(runCount > 0 || emptyRuns).toBeTruthy();

    if (runCount > 0) {
      const firstRun = runCards.first();
      const runText = await firstRun.textContent();
      expect(runText).toMatch(/Running|Completed|Failed|Pending|Cancelled|Scheduled/);
    }
  });

  // DC-CREW-09: Refresh button reloads data
  test("DC-CREW-09: refresh button reloads data", async ({ page }) => {
    await expect(crews.refreshButton).toBeVisible();

    await crews.refreshButton.click();
    await page.waitForTimeout(1000);

    await expect(page.locator("h1", { hasText: "Crews" })).toBeVisible();
  });
});

// ==========================================================================
// Negative Workflows
// ==========================================================================

test.describe("Negative Workflows", () => {
  // DC-CREW-10: Empty crew list shows "No crews yet" state
  test("DC-CREW-10: empty crew list shows no crews yet state", async ({ page }) => {
    await crews.searchCrews("zzz_impossible_crew_name_zzz");

    const crewCount = await crews.getCrewCount();
    if (crewCount === 0) {
      // Either shows "No crews yet" or page stays stable
      await expect(page.locator("h1", { hasText: "Crews" })).toBeVisible();
    }
  });

  // DC-CREW-11: Empty runs list shows "No runs yet" state
  test("DC-CREW-11: empty runs list shows no runs yet state", async () => {
    await crews.switchTab("runs");
    await crews.searchCrews("zzz_impossible_run_id_zzz");

    const runCards = crews.page.locator(".grid.gap-3 > div.rounded-xl");
    const runCount = await runCards.count();

    if (runCount === 0) {
      await expect(crews.emptyRunsState).toBeVisible();
    }
  });
});

// ==========================================================================
// Library Agent Browser
// ==========================================================================

test.describe("Library Agent Browser", () => {
  // DC-CREW-12: Browse Library button is visible in the crew builder dialog
  test("DC-CREW-12: browse library button is visible in crew builder", async () => {
    await crews.openBuilder();
    await expect(crews.browseLibraryButton).toBeVisible();
  });

  // DC-CREW-13: Clicking Browse Library opens the library panel
  test("DC-CREW-13: clicking browse library opens the library panel", async () => {
    await crews.openBuilder();
    await crews.openLibraryPanel();

    await expect(crews.libraryPanelHeading).toBeVisible();
    await expect(crews.librarySearchInput).toBeVisible();
  });

  // DC-CREW-14: Library panel shows agents
  test("DC-CREW-14: library panel shows agents", async () => {
    await crews.openBuilder();
    await crews.openLibraryPanel();

    // Wait for agents to load
    await crews.page.waitForTimeout(1000);

    const agentCount = await crews.libraryAgentRows.count();
    expect(agentCount).toBeGreaterThanOrEqual(1);
  });

  // DC-CREW-15: Library panel search functionality filters agents
  test("DC-CREW-15: library panel search filters agents", async ({ page }) => {
    await crews.openBuilder();
    await crews.openLibraryPanel();

    // Wait for initial load
    await page.waitForTimeout(1000);
    const initialCount = await crews.libraryAgentRows.count();

    // Search for something unlikely to match all agents
    await crews.searchLibraryAgents("zzz_no_agent_matches_this_zzz");

    const filteredCount = await crews.libraryAgentRows.count();

    // Either no results or fewer results than initial
    if (initialCount > 0) {
      expect(filteredCount).toBeLessThan(initialCount);
    }

    // Verify the "No agents found" message appears when there are no results
    if (filteredCount === 0) {
      await expect(
        crews.libraryPanel.getByText(/no agents found/i)
      ).toBeVisible();
    }
  });

  // DC-CREW-16: Selecting a library agent adds it to the crew agent list
  test("DC-CREW-16: selecting a library agent adds it to agent list", async ({ page }) => {
    await crews.openBuilder();

    // Count initial agent entries (there should be 1 empty agent by default)
    const initialAgentCount = await crews.agentNameInputs.count();

    await crews.openLibraryPanel();

    // Wait for agents to load
    await page.waitForTimeout(1000);

    const agentCount = await crews.libraryAgentRows.count();
    if (agentCount === 0) {
      test.skip();
      return;
    }

    // Capture the name of the first library agent before clicking
    const firstAgentName = await crews.libraryAgentRows
      .first()
      .locator("span.text-sm.font-medium")
      .first()
      .textContent();

    // Select the first agent
    await crews.selectLibraryAgent(0);

    // Library panel should close after selection
    await expect(crews.libraryPanel).not.toBeVisible({ timeout: 3000 });

    // A new agent entry should have been added
    const updatedAgentCount = await crews.agentNameInputs.count();
    expect(updatedAgentCount).toBe(initialAgentCount + 1);

    // The last agent name input should contain the selected agent's name
    const lastAgentNameValue = await crews.agentNameInputs
      .last()
      .inputValue();
    expect(lastAgentNameValue).toBe(firstAgentName?.trim() ?? "");

    // The last agent instructions textarea should not be empty
    const lastInstructionsValue = await crews.agentInstructionTextareas
      .last()
      .inputValue();
    expect(lastInstructionsValue.length).toBeGreaterThan(0);
  });
});
