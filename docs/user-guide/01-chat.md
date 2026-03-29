# Chat

The Chat module is the heart of ContextuAI Solo. It's where you have conversations with AI models — either cloud-based (Anthropic, OpenAI, Google) or local models running on your machine.

![Chat](../screenshots/001-dashboard-chat.png)

---

## Getting Started

1. Open the app — you land on the Chat page by default.
2. Select an AI model from the dropdown in the input area.
3. Type your message and press **Enter** to send.
4. The AI responds in real-time with streaming text.

## Sending Messages

- **Enter** sends your message.
- **Shift + Enter** adds a new line without sending.
- The send button is disabled when the input is empty or whitespace-only.
- Long messages (1000+ characters) are handled gracefully.

## AI Model Selection

The model dropdown in the input area lets you choose which AI model to use. You'll see:

- **Model name** (e.g., Claude Sonnet, GPT-4o, Gemma 3 1B)
- **Provider** (Anthropic, OpenAI, Google, Local)
- **AI Mode badge** — shows whether you're in **Local** (green) or **Cloud** (blue) mode

Use the **"All models"** toggle to see models from all providers, regardless of your current AI mode.

## Personas

Personas customize how the AI behaves. Select one from the persona dropdown in the input area.

- Each persona has a name and description to help you choose.
- Select **"None (default)"** to use the AI without a persona.
- Persona selection persists with each session.

See the [Personas guide](03-personas.md) for creating your own.

## Chat Sessions

### Creating Sessions

- Click **New Chat** in the sidebar, or press **Ctrl + N** (Cmd + N on Mac).
- A session is automatically created when you send your first message.
- The session title is auto-generated from your first message.

### Switching Sessions

- Click any session in the sidebar to load it.
- Your messages and conversation history are preserved when switching.
- The active session is highlighted in the sidebar.

### Session Sidebar

Each session entry shows:

- **Title** (auto-generated or manually renamed)
- **Last message date** (Today, Yesterday, 3d ago, etc.)
- **Message count** (e.g., "3 msgs")

### Renaming Sessions

Click the session title in the chat header to enter edit mode. Press **Enter** to save or **Escape** to cancel.

### Archiving and Deleting

Hover over a session in the sidebar to reveal the menu (three dots):

- **Archive** — removes the session from the active list but keeps the data.
- **Delete** — permanently removes the session.

### Searching Sessions

Use the search box at the top of the sidebar to filter sessions by title.

## Streaming Responses

AI responses stream in real-time — you see the text appear word by word as the model generates it.

- A **stop button** (red square) appears during generation. Click it to cancel.
- A **"Thinking..."** indicator shows while the AI processes your request.

## Markdown and Code

AI responses support rich formatting:

- **Bold**, *italic*, ~~strikethrough~~, headers, lists, blockquotes, links
- Code blocks with **syntax highlighting** and a **copy button**
- If the model supports it, a collapsible **"Thinking"** section shows the AI's reasoning process.

## Dark / Light Mode

Toggle between dark and light themes using the sun/moon icon in the chat header. Your preference persists across sessions.

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Enter | Send message |
| Shift + Enter | New line |
| Ctrl + N | New chat session |

## Tips

- **Start with a clear first message** — it becomes the session title and sets the context for the conversation.
- **Use personas** for specialized tasks — a "Financial Analyst" persona will give more structured financial advice than the default.
- **Switch models mid-conversation** if you want a different perspective — your history stays intact.
- **Archive old sessions** instead of deleting them, in case you need to reference them later.
