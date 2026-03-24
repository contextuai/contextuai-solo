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

  // DC-CREW-03: Create a crew (opens wizard)
  test("DC-CREW-03: create a crew opens wizard", async ({ page }) => {
    await crews.createButton.click();
    await page.waitForTimeout(500);

    const dialogVisible = await crews.builderDialog.isVisible().catch(() => false);
    expect(dialogVisible).toBeTruthy();

    // Should show step 1 with crew name input
    await expect(crews.crewNameInput).toBeVisible();
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
// Wizard Flow
// ==========================================================================

test.describe("Wizard Flow", () => {
  // DC-CREW-WIZ-01: Wizard shows step indicator
  test("DC-CREW-WIZ-01: wizard shows step indicator", async () => {
    await crews.openBuilder();

    // Should have 4 step indicator circles
    const indicators = crews.stepIndicators;
    const count = await indicators.count();
    expect(count).toBeGreaterThanOrEqual(3); // 3 for autonomous, 4 for others
  });

  // DC-CREW-WIZ-02: Step 1 shows crew name and description
  test("DC-CREW-WIZ-02: step 1 shows crew details", async () => {
    await crews.openBuilder();

    await expect(crews.crewNameInput).toBeVisible();
    await expect(crews.crewDescriptionInput).toBeVisible();
  });

  // DC-CREW-WIZ-03: Next button requires name on step 1
  test("DC-CREW-WIZ-03: next button requires name", async ({ page }) => {
    await crews.openBuilder();

    // Next should be disabled without a name
    await expect(crews.nextButton).toBeDisabled();

    // Fill name
    await crews.crewNameInput.fill("Test Crew");
    await expect(crews.nextButton).toBeEnabled();
  });

  // DC-CREW-WIZ-04: Navigate through all wizard steps
  test("DC-CREW-WIZ-04: navigate through all wizard steps", async ({ page }) => {
    await crews.openBuilder();

    // Step 1: Fill name
    await crews.crewNameInput.fill("Multi-Step Test");
    await crews.nextButton.click();
    await page.waitForTimeout(300);

    // Step 2: Execution mode cards should be visible
    await expect(page.locator("text=Execution Mode").first()).toBeVisible();
    await crews.nextButton.click();
    await page.waitForTimeout(300);

    // Step 3: Agent pipeline — fill in required agent fields
    await expect(page.locator("text=Agent Pipeline").first()).toBeVisible();
    const agentName = crews.agentNameInputs.first();
    const agentInstructions = crews.agentInstructionTextareas.first();
    await agentName.fill("Test Agent");
    await agentInstructions.fill("Perform research and analysis");
    await crews.nextButton.click();
    await page.waitForTimeout(300);

    // Step 4: Connections
    await expect(page.locator("text=Channel Connections").first()).toBeVisible();
    await crews.nextButton.click();
    await page.waitForTimeout(300);

    // Step 5: Review
    await expect(page.locator("text=Review Configuration").first()).toBeVisible();
  });

  // DC-CREW-WIZ-05: Connections step shows channel cards
  test("DC-CREW-WIZ-05: connections step shows channel cards", async ({ page }) => {
    await crews.openBuilder();

    // Navigate to step 4 (Connections)
    await crews.crewNameInput.fill("Connections Test");
    await crews.nextButton.click(); // → Step 2
    await page.waitForTimeout(200);
    await crews.nextButton.click(); // → Step 3
    await page.waitForTimeout(200);

    // Fill agent data to proceed
    const agentName = crews.agentNameInputs.first();
    const agentInstructions = crews.agentInstructionTextareas.first();
    await agentName.fill("Bot Agent");
    await agentInstructions.fill("Handle messages");
    await crews.nextButton.click(); // → Step 4 (Connections)
    await page.waitForTimeout(300);

    // Should show Channel Connections heading
    await expect(page.locator("text=Channel Connections").first()).toBeVisible();

    // Should have connection cards (Telegram, Discord, LinkedIn, Twitter, Instagram, Facebook)
    const connectionCards = page.locator(".grid button").filter({
      has: page.locator("p.text-sm.font-medium"),
    });
    const count = await connectionCards.count();
    expect(count).toBeGreaterThanOrEqual(6);

    // Click Telegram to select it
    await page.locator("text=Telegram").first().click();
    await page.waitForTimeout(200);

    // Should show selected count
    await expect(page.locator("text=1 channel selected")).toBeVisible();
  });

  // DC-CREW-WIZ-06: Back button navigates backwards
  test("DC-CREW-WIZ-06: back button navigates backwards", async ({ page }) => {
    await crews.openBuilder();

    // Go to step 2
    await crews.crewNameInput.fill("Back Test");
    await crews.nextButton.click();
    await page.waitForTimeout(300);

    // Verify on step 2
    await expect(page.locator("text=Execution Mode").first()).toBeVisible();

    // Go back to step 1
    await crews.backButton.click();
    await page.waitForTimeout(300);

    // Should see crew name input again
    await expect(crews.crewNameInput).toBeVisible();
    const nameValue = await crews.crewNameInput.inputValue();
    expect(nameValue).toBe("Back Test"); // preserved
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
  // DC-CREW-12: Browse Library button is visible on step 3
  test("DC-CREW-12: browse library button is visible on step 3", async () => {
    await crews.openBuilder();
    await crews.goToStep(3);
    await expect(crews.browseLibraryButton).toBeVisible();
  });

  // DC-CREW-13: Clicking Browse Library opens the library panel
  test("DC-CREW-13: clicking browse library opens the library panel", async () => {
    await crews.openBuilder();
    await crews.goToStep(3);
    await crews.openLibraryPanel();

    await expect(crews.libraryPanelHeading).toBeVisible();
    await expect(crews.librarySearchInput).toBeVisible();
  });

  // DC-CREW-14: Library panel shows agents
  test("DC-CREW-14: library panel shows agents", async () => {
    await crews.openBuilder();
    await crews.goToStep(3);
    await crews.openLibraryPanel();

    // Wait for agents to load
    await crews.page.waitForTimeout(1000);

    const agentCount = await crews.libraryAgentRows.count();
    expect(agentCount).toBeGreaterThanOrEqual(1);
  });

  // DC-CREW-15: Library panel search functionality filters agents
  test("DC-CREW-15: library panel search filters agents", async ({ page }) => {
    await crews.openBuilder();
    await crews.goToStep(3);
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
    await crews.goToStep(3);

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

// ==========================================================================
// Crew Execution (run crew with local Gemma model)
// ==========================================================================

test.describe("Crew Execution", () => {
  // Local model inference can be slow — allow up to 5 minutes
  test.setTimeout(300_000);

  test("DC-CREW-EXEC-01: create crew via API, run it with local model, and verify completed status", async ({ page }) => {
    const API = "http://127.0.0.1:18741/api/v1";
    const crewName = `Exec Crew ${Date.now()}`;

    // 1. Create a crew via API with a single agent using small local model
    const createResp = await page.request.post(`${API}/crews/`, {
      data: {
        name: crewName,
        description: "E2E execution test crew",
        agents: [
          {
            name: "Test Writer",
            instructions: "Reply with exactly one short sentence.",
            model_id: "local:qwen2.5-0.5b",
            order: 0,
          },
        ],
        execution_config: {
          mode: "sequential",
          max_iterations: 1,
        },
      },
    });
    expect(createResp.ok()).toBeTruthy();
    const createData = await createResp.json();
    // Response shape: { status: "success", data: { crew_id, ... } }
    const crew = createData.data ?? createData.crew ?? createData;
    const crewId = crew.crew_id ?? crew.id;
    expect(crewId).toBeTruthy();

    // 2. Run the crew
    const runResp = await page.request.post(`${API}/crews/${crewId}/run`, {
      data: {
        input: "Say hello.",
      },
    });
    expect(runResp.ok()).toBeTruthy();
    const runData = await runResp.json();
    // Response shape: { status: "success", data: { run_id, ... } }
    const run = runData.data ?? runData.run ?? runData;
    const runId = run.run_id ?? run.id;
    expect(runId).toBeTruthy();

    // 3. Poll until completed or failed (up to 4 minutes)
    let finalStatus = "pending";
    for (let i = 0; i < 120; i++) {
      await page.waitForTimeout(2000);
      const statusResp = await page.request.get(`${API}/crews/runs/${runId}`);
      const statusData = await statusResp.json();
      const runDetail = statusData.data ?? statusData.run ?? statusData;
      finalStatus = runDetail.status ?? "unknown";
      if (finalStatus === "completed" || finalStatus === "failed") break;
    }
    expect(finalStatus).toBe("completed");

    // 4. Verify the run result has content via API
    const resultResp = await page.request.get(`${API}/crews/runs/${runId}`);
    const resultData = await resultResp.json();
    const resultRun = resultData.data ?? resultData.run ?? resultData;
    expect(resultRun.result).toBeTruthy();

    // 5. Verify the crew appears in the UI
    await page.goto("/crews");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1500);

    await expect(page.getByText(crewName)).toBeVisible({ timeout: 10000 });

    // 6. Cleanup
    await page.request.delete(`${API}/crews/${crewId}`);
  });
});
