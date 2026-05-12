# Using ContextuAI Solo from VS Code (and other IDEs)

ContextuAI Solo exposes an **OpenAI-compatible HTTP API** on `http://localhost:18741`. Any tool that speaks the OpenAI Chat Completions or legacy Completions protocol can use Solo as its model backend — no internet, no API costs, your code never leaves your machine.

Tested with: **Continue.dev**, **Cline / Roo Code**, **Cursor**, **Aider**, **Tabby**, **Cody**, **Zed**, and any OpenAI SDK client.

## What you get

| Endpoint | Purpose |
|---|---|
| `GET  /v1/models` | List the models Solo can run |
| `POST /v1/chat/completions` | Chat messages → reply (streaming or not) |
| `POST /v1/completions` | Text completion with Fill-in-the-Middle (FIM) for inline autocomplete |

- **No auth.** Solo binds to `127.0.0.1` only, so the endpoint is reachable from your machine but not from the network.
- **Streaming works.** Pass `"stream": true` and you'll get standard SSE `data: {...}` chunks.
- **Local models out of the box.** Anything you downloaded from the Model Hub is selectable by its model ID.

## Before you start

1. Make sure Solo is **running** (the desktop app must be open, or the backend started via `./run.sh`).
2. In the app, open **Model Hub** and download at least one local model — `qwen2.5-coder-7b` or `qwen2.5-7b` are great starting points for coding tasks.
3. Confirm the endpoint is up:

   ```bash
   curl http://localhost:18741/v1/models
   ```

   You should see a JSON list with the models you've downloaded.

## VS Code — Continue.dev

[Continue](https://continue.dev) is the most popular OSS coding assistant for VS Code and JetBrains IDEs.

1. Install the **Continue** extension.
2. Open `~/.continue/config.json` (Continue creates it on first run) and add Solo as a custom provider:

   ```json
   {
     "models": [
       {
         "title": "Solo — Qwen Coder",
         "provider": "openai",
         "model": "qwen2.5-coder-7b",
         "apiBase": "http://localhost:18741/v1",
         "apiKey": "not-needed"
       }
     ],
     "tabAutocompleteModel": {
       "title": "Solo — FIM",
       "provider": "openai",
       "model": "qwen2.5-coder-7b",
       "apiBase": "http://localhost:18741/v1",
       "apiKey": "not-needed"
     }
   }
   ```

3. Reload the Continue panel. Pick **Solo — Qwen Coder** from the model dropdown.
4. Inline autocompletion (the `tabAutocompleteModel`) uses `/v1/completions` with FIM — works out of the box.

## VS Code — Cline / Roo Code

[Cline](https://github.com/cline/cline) (and its fork **Roo Code**) is a full agentic assistant.

1. Install Cline.
2. Open the gear icon → **API Provider** → **OpenAI Compatible**.
3. Fill in:
   - **Base URL:** `http://localhost:18741/v1`
   - **API Key:** anything (e.g. `local`) — required by the form but ignored
   - **Model ID:** `qwen2.5-coder-7b` (or whichever model you downloaded)
4. Save. Start a new task and Cline will route every call through Solo.

## Cursor

Cursor accepts custom OpenAI-compatible endpoints.

1. **Settings → Models → Override OpenAI Base URL** → `http://localhost:18741/v1`
2. **OpenAI API Key** → anything non-empty.
3. **Models → Add a custom model** → enter your Solo model ID (e.g. `qwen2.5-coder-7b`) and enable it.

Note: Cursor's "smart" features (Cursor Tab, Composer) still call Cursor's own cloud unless you've explicitly switched them off. The chat sidebar will use Solo.

## Aider

[Aider](https://aider.chat) talks to OpenAI-compatible endpoints out of the box.

```bash
export OPENAI_API_BASE=http://localhost:18741/v1
export OPENAI_API_KEY=not-needed
aider --model qwen2.5-coder-7b
```

## Zed

In Zed's `~/.config/zed/settings.json`:

```json
{
  "assistant": {
    "default_model": {
      "provider": "openai",
      "model": "qwen2.5-coder-7b"
    },
    "openai": {
      "api_url": "http://localhost:18741/v1",
      "available_models": [
        { "name": "qwen2.5-coder-7b", "max_tokens": 32768 }
      ]
    }
  }
}
```

Drop your `OPENAI_API_KEY` env var in Zed's secret store with any string — it just has to be present.

## Plain curl / OpenAI Python SDK

```bash
curl http://localhost:18741/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen2.5-coder-7b",
    "messages": [
      {"role": "system", "content": "You are a senior Python engineer."},
      {"role": "user", "content": "Write a generator that yields Fibonacci numbers."}
    ],
    "stream": true
  }'
```

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:18741/v1",
    api_key="not-needed",  # required by the SDK, ignored by Solo
)

stream = client.chat.completions.create(
    model="qwen2.5-coder-7b",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

## Inline autocomplete (Fill-in-the-Middle)

If a tool sends a `prompt` plus a `suffix`, Solo runs the model in FIM mode — perfect for inline code completion:

```bash
curl http://localhost:18741/v1/completions \
  -d '{
    "model": "qwen2.5-coder-7b",
    "prompt": "def fib(n):\n    ",
    "suffix": "\n    return result",
    "max_tokens": 128
  }'
```

The Qwen Coder, DeepSeek Coder, and Code Llama families all support FIM and produce useful completions.

## Choosing a model

Open **Model Hub** in Solo to see what's downloaded. Some recommendations for coding work:

| Use case | Model | Why |
|---|---|---|
| General coding chat | `qwen2.5-coder-14b` | Strong reasoning + code, fits on most laptops |
| Tight RAM (≤8 GB) | `qwen2.5-coder-7b` | Quality holds up surprisingly well |
| Inline autocomplete (FIM) | `qwen2.5-coder-7b` or `deepseek-coder-6.7b` | Fast first-token latency |
| Long context (32k+) | `qwen2.5-coder-14b`, `phi-4` | Bigger context window |
| Reasoning-heavy refactors | `deepseek-r1-distill-qwen-14b` | Built-in chain-of-thought |

The model ID Solo expects is the filename stem from the Model Hub — e.g. `qwen2.5-coder-7b`, not `qwen/Qwen2.5-Coder-7B-Instruct-GGUF`. You can confirm any model's ID by hitting `GET /v1/models`.

## Coming soon — cloud models behind the same endpoint

Today the `/v1/chat/completions` endpoint serves your **local** models. The next release extends it so the same URL can route to your saved cloud keys (Anthropic, Google, OpenAI, AWS Bedrock, Ollama) just by prefixing the model name — e.g. `anthropic:claude-opus-4-7` or `google:gemini-2.5-pro`. Your IDE keeps pointing at `http://localhost:18741/v1`; Solo handles the rest.

## Troubleshooting

**`Connection refused`** — Solo isn't running. Open the desktop app or start the backend manually.

**`Model not found`** — The model isn't downloaded yet. Open Model Hub, download it, then sync (`POST /api/v1/local-models/sync` is called automatically on download).

**Slow first response** — Local models cold-start on the first request (the GGUF gets memory-mapped). Subsequent requests in the same session are much faster.

**RAM blew up** — You loaded a model too large for your machine. Quit the app to unload it, then pick a smaller variant in Model Hub.

**Streaming feels chunky** — That's normal on CPU inference. GPU acceleration is on the roadmap.
