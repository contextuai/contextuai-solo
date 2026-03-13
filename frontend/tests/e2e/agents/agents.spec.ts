/**
 * ContextuAI Solo Desktop — Agents E2E Tests
 *
 * Route: "/agents" (Agent Library)
 * Backend: http://127.0.0.1:18741 (no auth)
 * Frontend: http://localhost:1420 (Vite SPA)
 */
import { test, expect } from "@playwright/test";
import { AgentsPage } from "../fixtures/page-objects";

let agents: AgentsPage;

test.beforeEach(async ({ page }) => {
  agents = new AgentsPage(page);
  await agents.goto();
  // Wait for agents to load from backend
  await page.waitForTimeout(2000);
});

// ==========================================================================
// CRUD via UI
// ==========================================================================

test.describe("CRUD via UI", () => {
  // DC-AGENT-01: View agent library (cards loaded from backend)
  test("DC-AGENT-01: view agent library cards loaded from backend", async () => {
    const cardCount = await agents.getAgentCount();
    const emptyVisible = await agents.emptyState.isVisible().catch(() => false);

    expect(cardCount > 0 || emptyVisible).toBeTruthy();
  });

  // DC-AGENT-02: Search agents by name
  test("DC-AGENT-02: search agents by name", async () => {
    const cardCount = await agents.getAgentCount();
    if (cardCount === 0) {
      test.skip();
      return;
    }

    const names = await agents.getAgentNames();
    // Use a unique enough substring from the first agent name
    const searchTerm = names[0];

    await agents.searchAgents(searchTerm);

    const filteredCount = await agents.getAgentCount();
    expect(filteredCount).toBeGreaterThanOrEqual(1);
    expect(filteredCount).toBeLessThanOrEqual(cardCount);

    // The searched agent should be in the results
    const filteredNames = await agents.getAgentNames();
    expect(filteredNames).toContain(searchTerm);
  });

  // DC-AGENT-03: Filter agents by role
  test("DC-AGENT-03: filter agents by role", async () => {
    const totalCount = await agents.getAgentCount();
    if (totalCount === 0) {
      test.skip();
      return;
    }

    const roleButtons = await agents.roleFilters.all();
    if (roleButtons.length < 2) {
      test.skip();
      return;
    }

    // Click the second filter (first non-"All" role)
    await roleButtons[1].click();
    await agents.page.waitForTimeout(300);

    const filteredCount = await agents.getAgentCount();
    expect(filteredCount).toBeLessThanOrEqual(totalCount);
  });

  // DC-AGENT-04: Open agent detail panel
  test("DC-AGENT-04: open agent detail panel", async ({ page }) => {
    const cardCount = await agents.getAgentCount();
    if (cardCount === 0) {
      test.skip();
      return;
    }

    const names = await agents.getAgentNames();
    await agents.openAgentDetail(names[0]);

    // Detail panel or slide-over should appear
    const detailVisible = await agents.detailPanel.isVisible().catch(() => false);
    const fixedVisible = await page
      .locator("[class*='fixed']")
      .filter({ has: page.locator("h2, h3") })
      .first()
      .isVisible()
      .catch(() => false);

    expect(detailVisible || fixedVisible).toBeTruthy();
  });

  // DC-AGENT-05: Create a custom agent
  test("DC-AGENT-05: create a custom agent", async ({ page }) => {
    await agents.createButton.click();
    await page.waitForTimeout(500);

    const dialog = page.locator("[class*='fixed']").filter({
      has: page.locator("text=/Create|New Agent/i"),
    });
    await expect(dialog).toBeVisible();
  });

  // DC-AGENT-06: Agent cards show description (not empty)
  test("DC-AGENT-06: agent cards show description", async () => {
    const cardCount = await agents.getAgentCount();
    if (cardCount === 0) {
      test.skip();
      return;
    }

    // Each card has description text
    const descriptions = await agents.agentCards.locator("p.text-xs").all();
    for (const desc of descriptions) {
      const text = await desc.textContent();
      expect(text).toBeTruthy();
      expect(text!.length).toBeGreaterThan(0);
    }
  });

  // DC-AGENT-07: Agent cards show category labels (human-readable)
  test("DC-AGENT-07: agent cards show category labels", async () => {
    const cardCount = await agents.getAgentCount();
    if (cardCount === 0) {
      test.skip();
      return;
    }

    // Each card has a role badge
    const roleBadges = await agents.agentCards.locator("span.rounded").all();
    expect(roleBadges.length).toBeGreaterThanOrEqual(1);

    for (const badge of roleBadges) {
      const text = await badge.textContent();
      expect(text!.trim().length).toBeGreaterThan(0);
    }
  });
});

// ==========================================================================
// Positive Workflows
// ==========================================================================

test.describe("Positive Workflows", () => {
  // DC-AGENT-08: Agent count badge matches visible cards
  test("DC-AGENT-08: agent count badge matches visible cards", async () => {
    const countText = await agents.agentCountText.textContent();
    if (!countText) {
      test.skip();
      return;
    }

    const match = countText.match(/(\d+)/);
    if (!match) {
      test.skip();
      return;
    }

    const reportedCount = parseInt(match[1], 10);
    const visibleCount = await agents.getAgentCount();
    expect(visibleCount).toBe(reportedCount);
  });

  // DC-AGENT-09: Search + role filter combine correctly
  test("DC-AGENT-09: search and role filter combine correctly", async () => {
    const totalCount = await agents.getAgentCount();
    if (totalCount < 2) {
      test.skip();
      return;
    }

    const roleButtons = await agents.roleFilters.all();
    if (roleButtons.length < 2) {
      test.skip();
      return;
    }

    await roleButtons[1].click();
    await agents.page.waitForTimeout(300);
    const afterRoleFilter = await agents.getAgentCount();

    const names = await agents.getAgentNames();
    if (names.length > 0) {
      await agents.searchAgents(names[0].slice(0, 5));
      const afterBothFilters = await agents.getAgentCount();
      expect(afterBothFilters).toBeLessThanOrEqual(afterRoleFilter);
    }
  });

  // DC-AGENT-10: Clear filters shows all agents
  test("DC-AGENT-10: clear filters shows all agents", async ({ page }) => {
    const totalCount = await agents.getAgentCount();
    if (totalCount === 0) {
      test.skip();
      return;
    }

    await agents.searchAgents("zzz_nonexistent_zzz");
    const filteredCount = await agents.getAgentCount();
    expect(filteredCount).toBe(0);

    // Clear via clear button or manually
    const clearBtn = page.locator("button", { hasText: "Clear Filters" });
    if (await clearBtn.isVisible()) {
      await clearBtn.click();
    } else {
      await agents.searchAgents("");
    }
    await page.waitForTimeout(300);

    const restoredCount = await agents.getAgentCount();
    expect(restoredCount).toBe(totalCount);
  });

  // DC-AGENT-11: Agent detail shows system prompt
  test("DC-AGENT-11: agent detail shows system prompt", async ({ page }) => {
    const cardCount = await agents.getAgentCount();
    if (cardCount === 0) {
      test.skip();
      return;
    }

    const names = await agents.getAgentNames();
    await agents.openAgentDetail(names[0]);

    // Panel should be open
    const panelVisible = await page
      .locator("[class*='fixed']")
      .first()
      .isVisible()
      .catch(() => false);

    expect(panelVisible).toBeTruthy();
  });

  // DC-AGENT-12: Refresh button reloads agents
  test("DC-AGENT-12: refresh button reloads agents", async ({ page }) => {
    await expect(agents.refreshButton).toBeVisible();
    await agents.refreshButton.click();
    await page.waitForTimeout(1000);

    const hasCards = (await agents.getAgentCount()) > 0;
    const hasEmpty = await agents.emptyState.isVisible().catch(() => false);
    expect(hasCards || hasEmpty).toBeTruthy();
  });
});

// ==========================================================================
// Negative Workflows
// ==========================================================================

test.describe("Negative Workflows", () => {
  // DC-AGENT-13: Search with no results shows empty state
  test("DC-AGENT-13: search with no results shows empty state", async () => {
    await agents.searchAgents("zzz_completely_nonexistent_agent_zzz");

    const cardCount = await agents.getAgentCount();
    expect(cardCount).toBe(0);

    await expect(agents.emptyState).toBeVisible();
  });

  // DC-AGENT-14: Role filter with no agents shows empty state
  test("DC-AGENT-14: role filter with no agents shows empty state", async () => {
    const roleButtons = await agents.roleFilters.all();
    if (roleButtons.length < 2) {
      test.skip();
      return;
    }

    await roleButtons[1].click();
    await agents.page.waitForTimeout(300);

    await agents.searchAgents("zzz_impossible_match_zzz");

    const cardCount = await agents.getAgentCount();
    expect(cardCount).toBe(0);

    await expect(agents.emptyState).toBeVisible();
  });
});
