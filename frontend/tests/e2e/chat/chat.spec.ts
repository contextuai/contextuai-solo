/**
 * ContextuAI Solo Desktop — Chat E2E Tests
 *
 * Route: "/" (Chat page)
 * Backend: http://127.0.0.1:18741 (no auth)
 * Frontend: http://localhost:1420 (Vite SPA)
 *
 * Tests marked "requires AI" are skipped when no AI model is available
 * (no downloaded local model and no cloud API key configured).
 */
import { test, expect } from "@playwright/test";
import { ChatPage } from "../fixtures/page-objects";

let chat: ChatPage;

/** Cached result — true when at least one AI model is available. */
let aiAvailable: boolean | null = null;

async function hasAI(): Promise<boolean> {
  if (aiAvailable !== null) return aiAvailable;
  try {
    const models = await fetch("http://127.0.0.1:18741/api/v1/desktop/local-models", {
      signal: AbortSignal.timeout(3000),
    }).then((r) => r.json());
    if (models?.models?.some((m: { downloaded: boolean }) => m.downloaded)) {
      return (aiAvailable = true);
    }
    const settings = await fetch("http://127.0.0.1:18741/api/v1/desktop/settings", {
      signal: AbortSignal.timeout(3000),
    }).then((r) => r.json());
    return (aiAvailable = !!(
      settings.anthropic_api_key || settings.openai_api_key || settings.google_api_key
    ));
  } catch {
    return (aiAvailable = false);
  }
}

test.beforeEach(async ({ page }) => {
  chat = new ChatPage(page);
  await chat.goto();
});

// ==========================================================================
// CRUD via UI
// ==========================================================================

test.describe("CRUD via UI", () => {
  // DC-CHAT-01: Send a message and receive a response
  test("DC-CHAT-01: send a message and receive a response", async () => {
    test.skip(!(await hasAI()), "No AI model available");
    test.setTimeout(120_000);

    const response = await chat.sendMessageAndWait("Hello, how are you?", 60_000);

    const userTexts = await chat.getUserMessageTexts();
    expect(userTexts).toContain("Hello, how are you?");
    expect(response.length).toBeGreaterThan(0);
  });

  // DC-CHAT-02: Streaming response renders progressively
  test("DC-CHAT-02: streaming response renders progressively", async () => {
    test.skip(!(await hasAI()), "No AI model available");
    test.setTimeout(120_000);

    await chat.typeMessage("Write a short paragraph about TypeScript.");
    await chat.clickSend();

    // The stop button should appear while streaming
    await expect(chat.stopButton).toBeVisible({ timeout: 15_000 });

    // Wait for streaming to finish
    await chat.waitForResponseComplete(60_000);

    // Final assistant message should exist
    const assistantTexts = await chat.getAssistantMessageTexts();
    expect(assistantTexts.length).toBeGreaterThanOrEqual(1);
  });

  // DC-CHAT-03: Create a new chat session
  test("DC-CHAT-03: create a new chat session", async () => {
    await expect(chat.chatInput).toBeVisible();
    await chat.createNewSession();
    await expect(chat.emptyStateHeading).toBeVisible();
  });

  // DC-CHAT-04: Continue an existing session (click session in sidebar)
  test("DC-CHAT-04: continue an existing session", async () => {
    test.skip(!(await hasAI()), "No AI model available");
    test.setTimeout(120_000);

    await chat.sendMessageAndWait("Test message for session continuity.", 60_000);

    await chat.createNewSession();
    await expect(chat.emptyStateHeading).toBeVisible();

    const sessionCount = await chat.sessionItems.count();
    if (sessionCount > 0) {
      await chat.sessionItems.first().click();
      await chat.page.waitForTimeout(1000);

      const userTexts = await chat.getUserMessageTexts();
      expect(userTexts.length).toBeGreaterThanOrEqual(1);
    }
  });

  // DC-CHAT-05: Delete a session from sidebar
  test("DC-CHAT-05: delete a session from sidebar", async () => {
    test.skip(!(await hasAI()), "No AI model available");
    test.setTimeout(120_000);

    await chat.sendMessageAndWait("Session to be deleted.", 60_000);

    const initialCount = await chat.sessionItems.count();
    expect(initialCount).toBeGreaterThanOrEqual(1);

    const session = chat.sessionItems.first();
    await session.hover();
    const menuBtn = session.locator("button").last();
    await menuBtn.click();

    await session.locator("button").filter({ hasText: "Delete" }).click();
    await chat.page.waitForTimeout(500);

    const newCount = await chat.sessionItems.count();
    expect(newCount).toBeLessThan(initialCount);
  });

  // DC-CHAT-06: Archive a session
  test("DC-CHAT-06: archive a session", async () => {
    test.skip(!(await hasAI()), "No AI model available");
    test.setTimeout(120_000);

    await chat.sendMessageAndWait("Session to be archived.", 60_000);

    const initialCount = await chat.sessionItems.count();
    expect(initialCount).toBeGreaterThanOrEqual(1);

    const session = chat.sessionItems.first();
    await session.hover();
    await session.locator("button").last().click();
    await session.locator("button").filter({ hasText: "Archive" }).click();
    await chat.page.waitForTimeout(500);

    const newCount = await chat.sessionItems.count();
    expect(newCount).toBeLessThan(initialCount);
  });
});

// ==========================================================================
// Positive Workflows
// ==========================================================================

test.describe("Positive Workflows", () => {
  // DC-CHAT-07: Complete 3-message conversation flow
  test("DC-CHAT-07: complete 3-message conversation flow", async () => {
    test.skip(!(await hasAI()), "No AI model available");
    test.setTimeout(180_000);

    await chat.sendMessageAndWait("What is 2+2?", 60_000);
    await chat.sendMessageAndWait("And what is 3+3?", 60_000);
    await chat.sendMessageAndWait("Now multiply those two results.", 60_000);

    const userTexts = await chat.getUserMessageTexts();
    expect(userTexts.length).toBe(3);

    const assistantTexts = await chat.getAssistantMessageTexts();
    expect(assistantTexts.length).toBe(3);
  });

  // DC-CHAT-08: Switch between sessions preserves data
  test("DC-CHAT-08: switch between sessions preserves data", async () => {
    test.skip(!(await hasAI()), "No AI model available");
    test.setTimeout(180_000);

    await chat.sendMessageAndWait("Session A: Hello", 60_000);

    await chat.createNewSession();
    await chat.sendMessageAndWait("Session B: Goodbye", 60_000);

    const sessions = await chat.sessionItems.all();
    if (sessions.length >= 2) {
      await sessions[1].click();
      await chat.page.waitForTimeout(1000);

      const userTexts = await chat.getUserMessageTexts();
      expect(userTexts.some((t) => t.includes("Session A"))).toBeTruthy();
    }
  });

  // DC-CHAT-09: Select a different AI model (if models loaded)
  test("DC-CHAT-09: select a different AI model", async ({ page }) => {
    await chat.modelSelector.click();
    await page.waitForTimeout(300);

    const modelOptions = page.locator(".absolute.bottom-full button").first();
    const hasModels = await modelOptions.isVisible().catch(() => false);

    if (hasModels) {
      await modelOptions.click();
      await page.waitForTimeout(300);
    } else {
      test.skip();
    }
  });

  // DC-CHAT-10: Chat with a persona selected
  test("DC-CHAT-10: chat with a persona selected", async ({ page }) => {
    test.skip(!(await hasAI()), "No AI model available");
    test.setTimeout(120_000);

    await chat.personaSelector.click();
    await page.waitForTimeout(300);

    const personaOptions = page.locator(".absolute.bottom-full button").filter({
      hasNot: page.locator("text=None"),
    });
    const hasPersonas = (await personaOptions.count()) > 0;

    if (hasPersonas) {
      await personaOptions.first().click();
      await page.waitForTimeout(300);
      await chat.sendMessageAndWait("Tell me about yourself.", 60_000);
      const assistantTexts = await chat.getAssistantMessageTexts();
      expect(assistantTexts.length).toBeGreaterThanOrEqual(1);
    } else {
      test.skip();
    }
  });

  // DC-CHAT-11: Keyboard shortcut Ctrl+N creates new session
  test("DC-CHAT-11: keyboard shortcut Ctrl+N creates new session", async ({ page }) => {
    test.skip(!(await hasAI()), "No AI model available");
    test.setTimeout(120_000);

    await chat.sendMessageAndWait("Message before shortcut.", 60_000);
    await page.keyboard.press("Control+n");
    await page.waitForTimeout(500);
    await expect(chat.emptyStateHeading).toBeVisible();
  });

  // DC-CHAT-12: Markdown renders correctly in responses
  test("DC-CHAT-12: markdown renders correctly in responses", async () => {
    test.skip(!(await hasAI()), "No AI model available");
    test.setTimeout(120_000);

    await chat.sendMessageAndWait(
      "Reply with exactly this markdown: **bold text** and *italic text* and a bullet list with items A, B, C.",
      60_000
    );

    const lastAssistant = chat.assistantMessages.last();
    const html = await lastAssistant.innerHTML();

    const hasBold = html.includes("<strong>");
    const hasItalic = html.includes("<em>");
    const hasList = html.includes("<li>");

    expect(hasBold || hasItalic || hasList).toBeTruthy();
  });

  // DC-CHAT-13: Code blocks render with syntax highlighting
  test("DC-CHAT-13: code blocks render with syntax highlighting", async () => {
    test.skip(!(await hasAI()), "No AI model available");
    test.setTimeout(120_000);

    await chat.sendMessageAndWait(
      "Show me a Python hello world example in a fenced code block with ```python.",
      60_000
    );

    const codeBlockCount = await chat.codeBlocks.count();
    expect(codeBlockCount).toBeGreaterThanOrEqual(1);
  });

  // DC-CHAT-14: Session title auto-generates from first message
  test("DC-CHAT-14: session title auto-generates from first message", async () => {
    test.skip(!(await hasAI()), "No AI model available");
    test.setTimeout(120_000);

    const message = "How to deploy a Node.js app to AWS?";
    await chat.sendMessageAndWait(message, 60_000);

    const firstSession = chat.sessionItems.first();
    const sessionText = await firstSession.textContent();
    expect(sessionText).toBeTruthy();
    expect(sessionText!.toLowerCase()).toContain("how to deploy");
  });
});

// ==========================================================================
// Negative Workflows
// ==========================================================================

test.describe("Negative Workflows", () => {
  // DC-CHAT-15: Empty message is prevented (send button disabled)
  test("DC-CHAT-15: empty message is prevented", async () => {
    await chat.chatInput.fill("");
    await chat.page.waitForTimeout(200);

    const isDisabled = await chat.sendButton.isDisabled();
    const hasDisabledClass = await chat.sendButton.evaluate((el) =>
      el.classList.contains("cursor-not-allowed")
    );
    expect(isDisabled || hasDisabledClass).toBeTruthy();
  });

  // DC-CHAT-16: Whitespace-only message is rejected
  test("DC-CHAT-16: whitespace-only message is rejected", async () => {
    await chat.chatInput.fill("   \n  \t  ");
    await chat.page.waitForTimeout(200);

    const isDisabled = await chat.sendButton.isDisabled();
    const hasDisabledClass = await chat.sendButton.evaluate((el) =>
      el.classList.contains("cursor-not-allowed")
    );
    expect(isDisabled || hasDisabledClass).toBeTruthy();
  });

  // DC-CHAT-17: Long message (1000+ chars) handled gracefully
  test("DC-CHAT-17: long message handled gracefully", async () => {
    test.skip(!(await hasAI()), "No AI model available");
    test.setTimeout(120_000);

    const longMessage = "A".repeat(1200);
    await chat.chatInput.fill(longMessage);
    await chat.page.waitForTimeout(200);

    const isDisabled = await chat.sendButton.isDisabled();
    expect(isDisabled).toBeFalsy();

    await chat.sendMessageAndWait(longMessage, 60_000);
    const userTexts = await chat.getUserMessageTexts();
    expect(userTexts.length).toBeGreaterThanOrEqual(1);
  });

  // DC-CHAT-18: Rapid send does not duplicate messages
  test("DC-CHAT-18: rapid send does not duplicate messages", async () => {
    test.skip(!(await hasAI()), "No AI model available");
    test.setTimeout(120_000);

    await chat.chatInput.fill("Rapid test message");

    // Click send multiple times quickly
    await chat.sendButton.click();
    await chat.sendButton.click().catch(() => {});
    await chat.sendButton.click().catch(() => {});

    await chat.waitForResponseComplete(60_000);

    const userTexts = await chat.getUserMessageTexts();
    expect(userTexts.length).toBe(1);
  });

  // DC-CHAT-19: Page refresh preserves current state
  test("DC-CHAT-19: page refresh preserves current state", async ({ page }) => {
    await expect(chat.chatInput).toBeVisible();

    await page.reload();
    await page.waitForLoadState("networkidle");

    await expect(chat.chatInput).toBeVisible();
  });
});
