// Provider onboarding guides — typed constant consumed by Settings → AI Providers tab.
// Cost copy reflects 2026-05 pricing and will rot; update it when prices change.

export interface ProviderGuideField {
  key: string;
  label: string;
  type: "password" | "text";
  placeholder: string;
  required: boolean;
}

export interface ProviderGuide {
  id: "anthropic" | "openai" | "google" | "bedrock" | "ollama" | "openai_compat";
  name: string;
  /** One-liner displayed under the name. */
  short_blurb: string;
  /** Opens in a new tab when the user clicks "Open dashboard". */
  dashboard_url: string;
  /** Numbered setup steps shown in the collapsible. */
  steps: string[];
  /** Approximate pricing copy. Intentionally static — no live fetch. */
  cost_copy: string;
  fields: ProviderGuideField[];
}

export const PROVIDER_GUIDES: readonly ProviderGuide[] = [
  {
    id: "anthropic",
    name: "Anthropic Claude",
    short_blurb: "Claude Opus 4.7, Sonnet 4.6, Haiku 4.5 — direct API",
    dashboard_url: "https://console.anthropic.com/",
    steps: [
      "Sign in (or sign up) at console.anthropic.com",
      "Add billing — Anthropic requires at least $5 in credits before you can call the API",
      'Open Settings → API Keys → "Create Key", give it a name like "ContextuAI Solo"',
      "Copy the key — it starts with sk-ant-",
      "Paste it below and click Save",
    ],
    cost_copy:
      "Sonnet 4.6: ~$3 / 1M input · ~$15 / 1M output  ·  Opus 4.7: ~$15 / 1M input · ~$75 / 1M output  ·  Haiku 4.5: ~$0.80 / 1M input · ~$4 / 1M output",
    fields: [
      {
        key: "api_key",
        label: "API Key",
        type: "password",
        placeholder: "sk-ant-…",
        required: true,
      },
    ],
  },
  {
    id: "openai",
    name: "OpenAI",
    short_blurb: "GPT-4o, GPT-4o mini — direct API",
    dashboard_url: "https://platform.openai.com/api-keys",
    steps: [
      "Sign in at platform.openai.com",
      "Add a payment method under Billing — most requests need a paid plan",
      'Open API Keys → "Create new secret key"',
      'Set a name and pick "All" permissions unless you want to scope it',
      "Copy the key — it starts with sk-",
      "Paste below and click Save",
    ],
    cost_copy:
      "GPT-4o: ~$2.50 / 1M input · ~$10 / 1M output  ·  GPT-4o mini: ~$0.15 / 1M input · ~$0.60 / 1M output",
    fields: [
      {
        key: "api_key",
        label: "API Key",
        type: "password",
        placeholder: "sk-…",
        required: true,
      },
    ],
  },
  {
    id: "google",
    name: "Google Gemini",
    short_blurb: "Gemini 2.5 Pro, 2.5 Flash, 2.0 Flash — via AI Studio",
    dashboard_url: "https://aistudio.google.com/apikey",
    steps: [
      "Visit aistudio.google.com/apikey (sign in with a Google account if prompted)",
      'Click "Create API key"',
      "Pick an existing Google Cloud project, or create a new one when prompted",
      "Copy the generated key",
      "Paste below and click Save",
      "Free tier available — no card needed for low volumes",
    ],
    cost_copy:
      "Gemini 2.5 Pro: ~$1.25 / 1M input · ~$5 / 1M output  ·  Gemini 2.5 Flash: ~$0.10 / 1M input · ~$0.40 / 1M output  ·  Free tier covers light use",
    fields: [
      {
        key: "api_key",
        label: "API Key",
        type: "password",
        placeholder: "AIza…",
        required: true,
      },
    ],
  },
  {
    id: "bedrock",
    name: "AWS Bedrock",
    short_blurb: "Claude, Llama, Titan and more — through your AWS account",
    dashboard_url: "https://console.aws.amazon.com/bedrock/home",
    steps: [
      "Sign in to the AWS Console and switch to a region that supports Bedrock (e.g. us-east-1)",
      "Open Amazon Bedrock → Model access → request access to the models you want (Anthropic Claude, Meta Llama, etc.). Approval is usually instant",
      'Open IAM → Users → "Create user" → attach the AmazonBedrockFullAccess policy',
      'On that user, go to Security credentials → Create access key → "Application running outside AWS"',
      "Copy the Access key ID and Secret access key (you only see the secret once)",
      "Paste both below along with the region and click Save",
    ],
    cost_copy:
      "Pricing varies by model and region. Bedrock invoices through your AWS account — no separate billing",
    fields: [
      {
        key: "aws_access_key_id",
        label: "AWS Access Key ID",
        type: "password",
        placeholder: "AKIA…",
        required: true,
      },
      {
        key: "aws_secret_access_key",
        label: "AWS Secret Access Key",
        type: "password",
        placeholder: "…",
        required: true,
      },
      {
        key: "aws_region",
        label: "Region",
        type: "text",
        placeholder: "us-east-1",
        required: true,
      },
    ],
  },
  {
    id: "ollama",
    name: "Ollama (Local)",
    short_blurb: "Run open models on your machine via Ollama",
    dashboard_url: "https://ollama.com/",
    steps: [
      "Install Ollama from ollama.com (macOS / Windows / Linux installers)",
      "Open a terminal and run `ollama pull qwen2.5-coder:7b` (or any model you want)",
      "Make sure Ollama is running — its server defaults to http://localhost:11434",
      "Confirm with `curl http://localhost:11434/api/tags` (optional)",
      "Save below — no API key required",
    ],
    cost_copy: "Free. Inference runs on your CPU / GPU",
    fields: [
      {
        key: "base_url",
        label: "Ollama URL",
        type: "text",
        placeholder: "http://localhost:11434",
        required: false,
      },
    ],
  },
  {
    id: "openai_compat",
    name: "OpenAI-Compatible",
    short_blurb: "Any server with an OpenAI /v1 API — vLLM, LM Studio, llama.cpp, TGI",
    dashboard_url: "https://platform.openai.com/docs/api-reference",
    steps: [
      "Start your OpenAI-compatible server (vLLM, LM Studio, llama.cpp server, TGI, …)",
      "Find its base URL — it must end in /v1 (e.g. http://localhost:8000/v1)",
      "Confirm with `curl http://your-server:8000/v1/models`",
      "Paste the base URL below (and an API key only if your server requires one)",
      "Save — models are auto-discovered from the server's /v1/models",
    ],
    cost_copy: "Depends on your server. Self-hosted is free; hosted endpoints bill per their pricing.",
    fields: [
      {
        key: "base_url",
        label: "Base URL",
        type: "text",
        placeholder: "http://localhost:8000/v1",
        required: true,
      },
      {
        key: "api_key",
        label: "API Key (optional)",
        type: "password",
        placeholder: "sk-… (leave blank if your server is keyless)",
        required: false,
      },
    ],
  },
] as const;
