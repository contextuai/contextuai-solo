# Manual Setup & Testing Guide

> Steps you need to do personally to test the full auto-reply flow.
> Everything code-side is built — you just need to connect a real Telegram bot.

---

## What Was Built (Summary)

| Feature | Status | What it does |
|---|---|---|
| **Think-tag parser** | Done | Strips `<think>...</think>` from Qwen 3/3.5 output, shows in collapsible UI |
| **OpenAI-compat API** | Done | `/v1/chat/completions` — works with Aider, Continue.dev, etc. |
| **Channel AI dispatch** | Done | Inbound messages → AI response (uses default local model) |
| **Trigger system** | Done | Link channels to crews/agents, with cooldown |
| **Trigger config UI** | Done | Auto-reply toggle per channel in Connections page |
| **Approval queue** | Done | Human-in-the-loop review before sending replies |
| **Approvals page** | Done | Full review/edit/approve/reject UI at `/approvals` |

---

## Step 1: Create a Telegram Bot (2 minutes)

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a name (e.g., "My Solo Assistant")
4. Choose a username (e.g., `my_solo_assistant_bot`)
5. BotFather gives you a **bot token** like: `7123456789:AAHxxx...`
6. **Copy this token** — you'll need it in Step 3

## Step 2: Start the Backend

```bash
cd backend
# Set the Telegram bot token as an environment variable
export TELEGRAM_BOT_TOKEN="7123456789:AAHxxx..."

# Start the backend
CONTEXTUAI_MODE=desktop python -m uvicorn app:app --host 127.0.0.1 --port 18741 --reload
```

## Step 3: Set Up ngrok (for webhook)

Telegram needs a public URL to send webhooks to your local machine.

```bash
# Install ngrok if not already: https://ngrok.com/download
ngrok http 18741
```

This gives you a URL like `https://abc123.ngrok-free.app`

## Step 4: Register the Webhook with Telegram

```bash
# Replace YOUR_BOT_TOKEN and YOUR_NGROK_URL
curl "https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook?url=YOUR_NGROK_URL/api/v1/channels/telegram/webhook"
```

You should see: `{"ok":true,"result":true,"description":"Webhook was set"}`

## Step 5: Test Direct AI Reply

1. Open Telegram and find your bot
2. Send it a message: "What is 2+2?"
3. The bot should reply with an AI-generated response using your default local model
4. Check the backend console — you'll see the model loading and inference

## Step 6: Test with a Trigger (Auto-Reply via Crew)

### Option A: UI Method
1. Start the frontend: `cd frontend && npm run dev`
2. Open `http://localhost:1420/connections`
3. Find Telegram → paste your bot token → Save
4. Toggle **Auto-Reply** ON
5. Check **Require Approval** if you want to review before sending
6. Send a message to your bot in Telegram
7. If approval required: go to `http://localhost:1420/approvals` to review

### Option B: API Method
```bash
# Create a trigger for Telegram (auto-reply, with approval)
curl -X POST http://localhost:18741/api/v1/triggers/ \
  -H "Content-Type: application/json" \
  -d '{
    "channel_type": "telegram",
    "approval_required": true,
    "cooldown_seconds": 10
  }'

# Send a message to your bot in Telegram
# Check pending approvals
curl http://localhost:18741/api/v1/approvals/

# Approve (replace APPROVAL_ID with the actual ID)
curl -X POST http://localhost:18741/api/v1/approvals/APPROVAL_ID/approve

# Or approve with edit
curl -X POST http://localhost:18741/api/v1/approvals/APPROVAL_ID/approve \
  -H "Content-Type: application/json" \
  -d '{"edited_response": "Your custom edited response here"}'
```

## Step 7: Test with a Crew

1. Go to `http://localhost:1420/crews` and create a crew (or use an existing one)
2. Note the crew ID
3. Create a trigger linked to the crew:
```bash
curl -X POST http://localhost:18741/api/v1/triggers/ \
  -H "Content-Type: application/json" \
  -d '{
    "channel_type": "telegram",
    "crew_id": "YOUR_CREW_ID",
    "approval_required": true
  }'
```
4. Send a message to your bot — the crew will execute and the draft will appear in Approvals

## Step 8: Test Think Tags (Qwen 3)

If you have Qwen 3 downloaded:
```bash
# Non-streaming — thinking is stripped
curl http://localhost:18741/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3-1.7b","messages":[{"role":"user","content":"What is 15*37?"}]}'

# With thinking included
curl "http://localhost:18741/v1/chat/completions?include_thinking=true" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3-1.7b","messages":[{"role":"user","content":"What is 5+3?"}]}'
```

In the Chat UI (`http://localhost:1420`), select a Qwen 3 model and ask a question.
You'll see a collapsible purple "Thinking" section above the response.

## Step 9: Test with Aider

```bash
pip install aider-chat
aider --openai-api-base http://localhost:18741/v1 --model qwen3-1.7b
```

---

## Cleanup

```bash
# Remove webhook when done testing
curl "https://api.telegram.org/botYOUR_BOT_TOKEN/deleteWebhook"
```

## Troubleshooting

| Issue | Fix |
|---|---|
| Bot doesn't respond | Check `TELEGRAM_BOT_TOKEN` env var is set before starting backend |
| "No AI model configured" | Go to Model Hub, download a model, then restart backend |
| Webhook returns 503 | Token not set — restart backend with the env var |
| ngrok URL expired | Restart ngrok, re-register webhook |
| Approval sent but Telegram fails | Bot token env var not set — response saved but couldn't deliver |

---

## Architecture Reference

```
Telegram → ngrok → POST /api/v1/channels/telegram/webhook
                     ↓
              parse_update() → ChannelMessage
                     ↓
              handle_message()
              ├─ Check triggers (trigger_service)
              │  ├─ No trigger → direct AI (local_model_service)
              │  ├─ Trigger + no approval → AI → send immediately
              │  └─ Trigger + approval → AI → store in approval_queue
              └─ Store messages in channel_messages
                     ↓
              send_message() → Telegram Bot API → user
```
