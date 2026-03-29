# Model Hub

The Model Hub lets you configure which AI models are available in ContextuAI Solo. You can use cloud providers (requires API keys) or download free local models that run entirely on your machine.

![Model Hub](../screenshots/002-ModelHub-Selection.png)

---

## Getting Started

1. Navigate to **Settings > AI Providers**.
2. Choose a provider and expand its card.
3. Enter your API key (for cloud providers) or download a model (for local AI).
4. Test the connection, then head to Chat to start using it.

## Cloud Providers

ContextuAI Solo supports 5 cloud AI providers:

| Provider | Models | Key Required |
|----------|--------|-------------|
| **Anthropic Claude** | Claude Sonnet, Opus, Haiku | Yes |
| **OpenAI** | GPT-4o, GPT-4o mini, GPT-4 Turbo, O1 Preview | Yes |
| **Google Gemini** | Gemini 2.0 Flash/Pro, Gemini 1.5 Flash | Yes |
| **AWS Bedrock** | Claude 3 Sonnet/Haiku, Titan | Yes (AWS credentials) |
| **Ollama** | Any Ollama-hosted model | No (local server) |

### Adding an API Key

1. Expand the provider card.
2. Paste your API key into the input field.
3. Click **Test Connection** to verify it works.
4. A green checkmark confirms the connection is active.

### Getting API Keys

- **Anthropic:** [console.anthropic.com](https://console.anthropic.com)
- **OpenAI:** [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- **Google:** [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

## Local AI Models

Local models run entirely on your CPU — no internet, no API keys, completely private.

![Models Installed](../screenshots/003-ModelsInstalled.png)

### Available Models

| Model | Size | Best For |
|-------|------|----------|
| **Gemma 3 1B** | ~1 GB | Fast responses, simple tasks |
| **Qwen 2.5 1.5B** | ~1.5 GB | Balanced speed and quality |
| **Phi-3 Mini** | ~2 GB | More capable reasoning |

### Downloading a Model

1. Expand the **Local AI (Built-in)** card in AI Providers.
2. Find the model you want and click **Download**.
3. A progress bar shows the download status.
4. Once downloaded, the model appears with a "Downloaded" badge.

Models are stored in `~/.contextuai-solo/models/` as GGUF files.

### After Downloading

After downloading, click **Sync** to register the model in the app. It will then appear in the Chat model dropdown.

## AI Mode Toggle

The sidebar has an **AI Mode** toggle that switches between:

- **Local** (green) — only shows locally downloaded models
- **Cloud** (blue) — only shows cloud provider models

Use the **"All models"** button in Chat to see all models regardless of mode.

## Tips

- **Start with a cloud provider** if you want the best quality — Anthropic Claude or OpenAI GPT-4o are excellent choices.
- **Download a local model** if privacy is your priority or you don't have internet access.
- **Local models are slower** than cloud models but completely free and private.
- **You can use both** — switch between local and cloud models depending on the task.
- **Test your connection** after adding an API key to make sure it's working before starting a chat.
