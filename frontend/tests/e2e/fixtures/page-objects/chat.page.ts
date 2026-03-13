import { type Page, type Locator, expect } from "@playwright/test";

/**
 * Page object for the Desktop Chat route ("/").
 *
 * The chat page contains:
 * - ChatSidebar: session list, new chat button, collapse toggle
 * - ChatHeader:  model selector, persona selector, session title
 * - MessageList: user and assistant message bubbles
 * - ChatInput:   textarea + send/stop button
 */
export class ChatPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  // ── Locators ────────────────────────────────────────────────────

  /** The main chat textarea input. */
  get chatInput(): Locator {
    return this.page.locator('textarea[placeholder="Ask me anything..."]');
  }

  /** Send button (arrow-up icon, visible when not streaming). */
  get sendButton(): Locator {
    return this.page.locator('button[title="Send message"]');
  }

  /** Stop button (square icon, visible while streaming). */
  get stopButton(): Locator {
    return this.page.locator('button[title="Stop generating"]');
  }

  /** All user message bubbles (right-aligned, primary background). */
  get userMessages(): Locator {
    return this.page.locator(".flex-row-reverse .whitespace-pre-wrap");
  }

  /** All assistant message bubbles (left-aligned, neutral background). */
  get assistantMessages(): Locator {
    return this.page.locator(
      '.mr-auto .prose'
    );
  }

  /** The streaming indicator bubble (typing dots or partial response). */
  get streamingBubble(): Locator {
    return this.page.locator(".animate-bounce").first();
  }

  /** Code blocks inside assistant messages. */
  get codeBlocks(): Locator {
    return this.page.locator(".mr-auto pre code");
  }

  /** New Chat button in the sidebar. */
  get newChatButton(): Locator {
    // Sidebar expanded: button with text "New"; collapsed: button with title "New chat"
    return this.page.locator('button:has(svg.lucide-plus)').first();
  }

  /** Session items in the sidebar. */
  get sessionItems(): Locator {
    return this.page.locator(
      '[class*="cursor-pointer"][class*="rounded"]'
    ).filter({ has: this.page.locator("svg.lucide-message-square") });
  }

  /** Model selector dropdown trigger. */
  get modelSelector(): Locator {
    // Model selector — shows "Select model" or selected model name (e.g. "Gemma 3 1B")
    // Identified by the Cpu icon from lucide-react
    return this.page.locator("button:has(svg.lucide-cpu)").first();
  }

  /** Persona selector dropdown trigger. */
  get personaSelector(): Locator {
    // Persona selector — identified by the Sparkles icon from lucide-react
    return this.page.locator("button:has(svg.lucide-sparkles)").first();
  }

  /** The empty state heading shown when no messages exist. */
  get emptyStateHeading(): Locator {
    return this.page.getByText("Start a conversation");
  }

  // ── Actions ─────────────────────────────────────────────────────

  /** Navigate to the chat page. */
  async goto(): Promise<void> {
    await this.page.goto("/");
    await this.page.waitForLoadState("networkidle");
  }

  /** Type a message into the chat input without sending. */
  async typeMessage(text: string): Promise<void> {
    await this.chatInput.click();
    await this.chatInput.fill(text);
  }

  /** Click the send button. */
  async clickSend(): Promise<void> {
    await this.sendButton.click();
  }

  /**
   * Type and send a message (fills textarea then presses Enter).
   * Does NOT wait for the response to complete.
   */
  async sendMessage(text: string): Promise<void> {
    await this.chatInput.click();
    await this.chatInput.fill(text);
    await this.chatInput.press("Enter");
  }

  /**
   * Send a message and wait for the assistant response to finish streaming.
   * Returns the text of the last assistant message.
   */
  async sendMessageAndWait(text: string, timeout = 30_000): Promise<string> {
    const currentCount = await this.assistantMessages.count();

    await this.sendMessage(text);

    // Wait for user message to appear
    await expect(this.userMessages.last()).toContainText(text, { timeout: 5_000 });

    // Wait for streaming to complete: a new assistant message appears
    await expect(this.assistantMessages).toHaveCount(currentCount + 1, {
      timeout,
    });

    // Ensure stop button is gone (streaming finished)
    await this.waitForResponseComplete(timeout);

    return (await this.assistantMessages.last().textContent()) ?? "";
  }

  /** Wait until streaming finishes (stop button disappears). */
  async waitForResponseComplete(timeout = 60_000): Promise<void> {
    await expect(this.stopButton).toBeHidden({ timeout });
  }

  /** Click the "New Chat" button in the sidebar. */
  async createNewSession(): Promise<void> {
    await this.newChatButton.click();
    await expect(this.emptyStateHeading).toBeVisible({ timeout: 5_000 });
  }

  /** Get all assistant message text contents as an array. */
  async getAssistantMessageTexts(): Promise<string[]> {
    const count = await this.assistantMessages.count();
    const texts: string[] = [];
    for (let i = 0; i < count; i++) {
      texts.push((await this.assistantMessages.nth(i).textContent()) ?? "");
    }
    return texts;
  }

  /** Get all user message text contents as an array. */
  async getUserMessageTexts(): Promise<string[]> {
    const count = await this.userMessages.count();
    const texts: string[] = [];
    for (let i = 0; i < count; i++) {
      texts.push((await this.userMessages.nth(i).textContent()) ?? "");
    }
    return texts;
  }
}
