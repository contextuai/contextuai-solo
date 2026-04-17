# Connections Setup Guide

Step-by-step instructions for connecting ContextuAI Solo to external platforms. All connections start from **Connections** page within the app.

---

## Telegram Bot

**Type:** Token paste | **Inbound + Outbound**

### Setup Steps

1. In Solo, go to **Connections** → click **Telegram Bot**
2. You'll see a field for **Bot Token** — to get one:
   - Open Telegram and search for **@BotFather**
   - Send `/newbot`
   - Choose a display name (e.g., "My Solo Assistant")
   - Choose a username (e.g., `my_solo_assistant_bot`)
   - BotFather gives you a token like: `7123456789:AAHxxx...`
3. Back in Solo, paste the bot token → click **Save**

### Receiving Messages (optional)

> **Note:** If you only want to **send messages** from Solo to Telegram, skip this section — the bot token is all you need.

To **receive** inbound messages (for auto-reply, crew triggers, etc.), Telegram needs a public URL to deliver messages to your local machine. Use [ngrok](https://ngrok.com/download):

```bash
ngrok http 18741
```

Register the webhook with Telegram:

```bash
curl "https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook?url=YOUR_NGROK_URL/api/v1/channels/telegram/webhook"
```

To remove the webhook when done:

```bash
curl "https://api.telegram.org/botYOUR_BOT_TOKEN/deleteWebhook"
```

> **Roadmap:** Native polling support (no ngrok required) is planned for a future release.

### Reference

- [Telegram Bot API — How to create a bot](https://core.telegram.org/bots#how-do-i-create-a-bot)

---

## Discord Bot

**Type:** Token paste | **Inbound + Outbound**

### Setup Steps

1. In Solo, go to **Connections** → click **Discord Bot**
2. You'll see fields for **Bot Token**, **Public Key**, and **Application ID** — to get these:
   - Go to the [Discord Developer Portal](https://discord.com/developers/applications)
   - Click **"New Application"** → give it a name → **Create**
   - On the **General Information** page, copy the **Application ID** and **Public Key**
   - Go to the **Bot** tab → click **"Reset Token"** → copy the **Bot Token**
   - Under **Privileged Gateway Intents**, enable **Message Content Intent**
   - Go to **OAuth2** → **URL Generator** → select scope `bot` with permissions `Send Messages` + `Read Message History` → copy the URL and open it to invite the bot to your server
3. Back in Solo, fill in all three fields → click **Save**

### Reference

- [Discord — Getting Started with Bots](https://discord.com/developers/docs/getting-started)

---

## Reddit

**Type:** Token paste (script app) | **Inbound + Outbound**

### Setup Steps

1. Go to [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
2. Scroll down and click **"create another app…"**
3. Fill in:
   - **Name:** ContextuAI Solo (or whatever you like)
   - **Type:** select **script**
   - **Redirect URI:** `http://localhost:18741` (not used, but required)
4. Click **Create app**
5. Copy your **Client ID** (under the app name, ~14 chars) and **Secret**
6. In Solo, go to **Connections** → click **Reddit**
7. Fill in:
   - **Client ID** and **Client Secret** from step 5
   - **Reddit Username** and **Reddit Password** (your account credentials)
   - **Subreddits** — comma-separated list to monitor (e.g., `LocalLLaMA,selfhosted`)
   - **Keywords** — only comments matching these words trigger the pipeline (leave empty to get all)
8. Click **Save** — Solo tests the connection and starts polling every 60 seconds

### How It Works

- **Inbound:** `RedditPoller` runs a 60-second background loop, fetching new comments from your configured subreddits (filtered by keywords) and unread inbox DMs. Each new item dispatches through the trigger + approval pipeline.
- **Outbound:** Reply to comments or send DMs via `POST /api/v1/reddit/reply`.
- **Rate limits:** praw handles Reddit's 60 req/min OAuth limit internally.

### Reference

- [Reddit — API Documentation](https://www.reddit.com/dev/api/)

---

## LinkedIn

**Type:** OAuth | **Outbound only**

### Setup Steps

1. In Solo, go to **Connections** → click **LinkedIn**
2. You'll see fields for **Client ID** and **Client Secret**, plus the redirect URL you'll need — to get the credentials:
   - Go to [LinkedIn Developers](https://www.linkedin.com/developers/apps) → **Create App**
   - Fill in: App name, LinkedIn Page (select or create one), and logo (optional)
   - After creation, go to the **Auth** tab
   - Copy the **Client ID** and **Client Secret**
   - Under **Authorized redirect URLs**, add the redirect URL shown in Solo:
     ```
     http://127.0.0.1:18741/api/v1/oauth/linkedin/callback
     ```
   - Go to the **Products** tab → request access to **Share on LinkedIn** and **Sign In with LinkedIn using OpenID Connect**
3. Back in Solo, enter the Client ID and Client Secret
4. Click **Connect with LinkedIn** → authorize in the popup

### Reference

- [LinkedIn Marketing API — Getting Started](https://learn.microsoft.com/en-us/linkedin/marketing/getting-started)

---

## Twitter / X

**Type:** Token paste | **Outbound only**

### Setup Steps

1. In Solo, go to **Connections** → click **Twitter / X**
2. You'll see fields for **API Key**, **API Secret**, **Access Token**, and **Access Token Secret** — to get these:
   - Go to the [X Developer Portal](https://developer.x.com/en/portal/dashboard)
   - Sign up for a developer account (Free tier works)
   - Create a **Project** and an **App** within it
   - In App Settings → **User authentication settings** → Edit → set permissions to **Read and write**
   - Go to **Keys and Tokens**:
     - Under **Consumer Keys**, generate **API Key** and **API Secret**
     - Under **Authentication Tokens**, generate **Access Token** and **Access Token Secret**
   - Important: generate the Access Token **after** setting Read and Write permissions — regenerate if you changed permissions after
3. Back in Solo, enter all 4 values → click **Save**

### Notes

- Free tier allows 1,500 tweets/month (50/day)

### Reference

- [X Developer Portal](https://developer.x.com/en/portal/dashboard)

---

## Instagram

**Type:** OAuth | **Outbound only**

### Prerequisites

- You need an **Instagram Business** or **Creator** account (not personal)
- The Instagram account must be linked to a Facebook Page

### Setup Steps

1. In Solo, go to **Connections** → click **Instagram**
2. You'll see fields for **App ID** and **App Secret**, plus the redirect URL — to get the credentials:
   - Go to [Meta for Developers](https://developers.facebook.com/apps/) → **Create App**
   - Select **Business** as the app type
   - Add the **Instagram Basic Display** product to your app
   - Go to **Instagram Basic Display** → **Basic Display**:
     - Under **Valid OAuth Redirect URIs**, add the redirect URL shown in Solo:
       ```
       http://127.0.0.1:18741/api/v1/oauth/instagram/callback
       ```
   - Go to **Settings** → **Basic** → copy the **App ID** and **App Secret**
3. Back in Solo, enter the App ID and App Secret
4. Click **Connect with Instagram** → authorize in the popup

### Reference

- [Instagram API Documentation](https://developers.facebook.com/docs/instagram-api/)

---

## Facebook

**Type:** OAuth | **Outbound only**

### Prerequisites

- You need a **Facebook Page** (not a personal profile) to publish to
- The app must be in **Live** mode for non-admin users (Development mode works for testing with your own account)

### Setup Steps

1. In Solo, go to **Connections** → click **Facebook**
2. You'll see fields for **App ID** and **App Secret**, plus the redirect URL — to get the credentials:
   - Go to [Meta for Developers](https://developers.facebook.com/apps/) → **Create App**
   - Select **Business** as the app type
   - Add the **Facebook Login** product to your app
   - Go to **Facebook Login** → **Settings**:
     - Under **Valid OAuth Redirect URIs**, add the redirect URL shown in Solo:
       ```
       http://127.0.0.1:18741/api/v1/oauth/facebook/callback
       ```
   - Go to **Settings** → **Basic** → copy the **App ID** and **App Secret**
   - Under **Permissions**, request `pages_manage_posts` and `pages_read_engagement`
3. Back in Solo, enter the App ID and App Secret
4. Click **Connect with Facebook** → authorize in the popup → select the Page to connect

### Reference

- [Facebook Pages API Documentation](https://developers.facebook.com/docs/pages-api/)

---

## Recommended AI Models for Connections

The quality of auto-replies and generated content depends heavily on which model you're running. For best results with social media and messaging:

| RAM | Recommended Model | Why |
|-----|-------------------|-----|
| 8 GB | **Qwen 3 8B** | Best balance of speed and quality for most business tasks |
| 16 GB+ | **Qwen 3 14B** | Significantly better writing quality — recommended for LinkedIn, Twitter, and customer-facing replies |

Download these from **Model Hub** in Solo. The smaller bundled models (1B-1.5B) work for quick tests but produce noticeably weaker output for social media content and professional communication.

---

## Auto-Reply & Approval Queue

Once a connection is set up, you can enable **Auto-Reply** to have Solo's AI automatically respond to inbound messages (currently supported for Telegram and Discord).

### How it works

1. Go to **Connections** → find your connected platform
2. Toggle **Auto-Reply** ON
3. Optionally check **Require Approval** for human-in-the-loop review
4. Inbound messages are processed by your default AI model
5. If approval is required, drafts appear at **Approvals** (`/approvals`) for review before sending

### Linking to Crews

You can route inbound messages through a multi-agent crew instead of a single AI response:

1. Create a crew in **Crews** with the agents you want
2. Create a trigger via the API:
   ```bash
   curl -X POST http://127.0.0.1:18741/api/v1/triggers/ \
     -H "Content-Type: application/json" \
     -d '{
       "channel_type": "telegram",
       "crew_id": "YOUR_CREW_ID",
       "approval_required": true,
       "cooldown_seconds": 10
     }'
   ```
3. Inbound messages will be processed by the full crew pipeline

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Telegram bot doesn't respond | Check that the bot token is correct and the webhook is registered |
| OAuth popup closes without connecting | Verify the redirect URI matches exactly (including `http` vs `https`) |
| "No AI model configured" on auto-reply | Download a local model in Model Hub, or configure an API key in Settings |
| Twitter post fails | Regenerate Access Token after enabling Read+Write permissions |
| Instagram won't connect | Ensure you have a Business/Creator account linked to a Facebook Page |
| Facebook shows "App not live" | Switch your Meta app from Development to Live mode |
