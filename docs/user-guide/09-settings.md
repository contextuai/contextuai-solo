# Settings

Settings is where you configure AI providers, customize your brand voice, adjust the app appearance, and manage your data.

![Settings](../screenshots/014-Settings.png)

---

## Getting Started

Navigate to **Settings** from the sidebar. The page has 5 tabs.

## Tab 1: AI Providers

Configure the AI models available throughout the app. See the [Model Hub guide](02-model-hub.md) for detailed setup instructions.

**6 provider cards:**

| Provider | Key Required | Notes |
|----------|-------------|-------|
| Local AI (Built-in) | No | Free GGUF models on your CPU |
| Anthropic Claude | Yes | Claude Sonnet, Opus, Haiku |
| OpenAI | Yes | GPT-4o, GPT-4o mini, O1 |
| Google Gemini | Yes | Gemini 2.0 Flash/Pro |
| AWS Bedrock | Yes | Claude 3 via AWS |
| Ollama | No | Local models via Ollama server |

For each cloud provider:
1. Expand the card.
2. Paste your API key.
3. Click **Test Connection** to verify.

### Local AI Models

Expand the **Local AI** card to see downloadable models:

| Model | Size | RAM Needed |
|-------|------|-----------|
| Gemma 3 1B | ~1 GB | ~2 GB |
| Qwen 2.5 1.5B | ~1.5 GB | ~3 GB |
| Phi-3 Mini | ~2 GB | ~4 GB |

Click **Download** next to a model. Progress is shown in real-time. After downloading, click **Sync** to make the model available in Chat.

## Tab 2: Brand Voice

Define your business identity so the AI can write in your brand's tone and style.

**Fields:**

- **Business Name** — your company or brand name
- **Industry** — select from 12 options (Tech, Marketing, Finance, Healthcare, Education, E-commerce, Creative, Consulting, Legal, Real Estate, Manufacturing, Other)
- **Brand Description** — what your business does and what makes it unique
- **Target Audience** — who you're writing for
- **Content Topics** — subjects you frequently cover

A **Brand Voice Preview** updates dynamically as you type, showing how the AI interprets your brand voice settings.

Click **Save Brand Voice** to apply. The brand voice influences AI responses across Chat, Crews, and Workspace.

## Tab 3: Appearance

Customize how the app looks.

### Theme

Choose from:
- **Light** — white backgrounds, dark text
- **Dark** — dark backgrounds, light text (easier on the eyes)
- **System** — follows your OS setting

### Font Size

- **Small** — compact layout
- **Medium** — default
- **Large** — easier to read

Changes apply immediately.

## Tab 4: Data & Export

Manage your local data.

### Export Data

Click **Export Data** to download a JSON backup of all your data (conversations, personas, agents, crews, settings). The file is saved to your Downloads folder with a timestamp in the filename.

### Clear All Data

Click **Clear All Data** to permanently delete everything. A confirmation dialog appears — this action cannot be undone.

This resets:
- All chat sessions and messages
- All personas, agents, and crews
- All workspace projects
- All connections and settings

## Tab 5: About

View app information:

- **App name and version** — current installed version
- **Check for Updates** — checks if a newer version is available
- **Built with** — shows the technology stack (React, Tauri, FastAPI) with links to documentation

## Tips

- **Set up at least one AI provider first** — nothing else works without a model.
- **Fill in your Brand Voice early** — it improves the quality and consistency of all AI outputs.
- **Export your data regularly** as a backup, especially before clearing data or updating the app.
- **Dark mode** is recommended for extended use — it reduces eye strain.
- **Test connections after entering API keys** — a typo in the key will cause all AI features to fail silently.
