import { useState, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import {
  ArrowRight,
  Check,
  Sparkles,
  Zap,
  Globe,
  Server,
  Cloud,
  Loader2,
  X,
  Info,
} from "lucide-react";
import logoImg from "@/assets/logo.png";

type WizardStep = 1 | 2 | 3;

interface WizardData {
  name: string;
  provider: string;
  model: string;
  apiKey: string;
  businessName: string;
  industry: string;
  brandVoice: string;
  targetAudience: string;
  contentTopics: string[];
}

const PROVIDERS = [
  {
    id: "anthropic",
    name: "Anthropic",
    subtitle: "Best for content creation.\nRecommended.",
    icon: Sparkles,
    iconBg: "bg-amber-100 dark:bg-amber-500/20",
    iconColor: "text-amber-600 dark:text-amber-400",
    badge: "Recommended",
    badgeColor: "bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400",
    pricingUrl: "https://www.anthropic.com/pricing",
    models: [
      { id: "claude-sonnet-4-20250514", name: "Claude Sonnet 4", tag: "Recommended" },
      { id: "claude-haiku-4-5-20251001", name: "Claude Haiku 4.5", tag: "Budget" },
      { id: "claude-opus-4-20250514", name: "Claude Opus 4", tag: "Most capable" },
    ],
  },
  {
    id: "openai",
    name: "OpenAI (GPT-4)",
    subtitle: "Strong alternative with image\ngeneration.",
    icon: Zap,
    iconBg: "bg-emerald-100 dark:bg-emerald-500/20",
    iconColor: "text-emerald-600 dark:text-emerald-400",
    pricingUrl: "https://openai.com/api/pricing",
    models: [
      { id: "gpt-4o", name: "GPT-4o", tag: "Recommended" },
      { id: "gpt-4o-mini", name: "GPT-4o Mini", tag: "Budget" },
      { id: "gpt-4-turbo", name: "GPT-4 Turbo" },
      { id: "o3-mini", name: "o3-mini", tag: "Reasoning" },
    ],
  },
  {
    id: "google",
    name: "Google (Gemini)",
    subtitle: "Budget-friendly with large\ncontext.",
    icon: Globe,
    iconBg: "bg-blue-100 dark:bg-blue-500/20",
    iconColor: "text-blue-600 dark:text-blue-400",
    pricingUrl: "https://ai.google.dev/pricing",
    models: [
      { id: "gemini-2.0-flash", name: "Gemini 2.0 Flash", tag: "Recommended" },
      { id: "gemini-2.0-flash-lite", name: "Gemini 2.0 Flash Lite", tag: "Budget" },
      { id: "gemini-2.5-pro", name: "Gemini 2.5 Pro", tag: "Most capable" },
    ],
  },
  {
    id: "ollama",
    name: "Ollama (Local)",
    subtitle: "Free. Runs on your machine.\nNo internet needed.",
    icon: Server,
    iconBg: "bg-violet-100 dark:bg-violet-500/20",
    iconColor: "text-violet-600 dark:text-violet-400",
    badge: "Free",
    badgeColor: "bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400",
    models: [
      { id: "llama3.2:3b", name: "Llama 3.2 (3B)", tag: "Lightweight" },
      { id: "llama3.1:8b", name: "Llama 3.1 (8B)", tag: "Recommended" },
      { id: "mistral:7b", name: "Mistral (7B)" },
      { id: "deepseek-r1:8b", name: "DeepSeek R1 (8B)", tag: "Reasoning" },
    ],
  },
  {
    id: "bedrock",
    name: "AWS Bedrock",
    subtitle: "For users with AWS accounts.",
    icon: Cloud,
    iconBg: "bg-orange-100 dark:bg-orange-500/20",
    iconColor: "text-orange-600 dark:text-orange-400",
    pricingUrl: "https://aws.amazon.com/bedrock/pricing",
    models: [
      { id: "anthropic.claude-sonnet-4-20250514-v1:0", name: "Claude Sonnet 4", tag: "Recommended" },
      { id: "anthropic.claude-haiku-4-5-20251001-v1:0", name: "Claude Haiku 4.5", tag: "Budget" },
      { id: "amazon.nova-pro-v1:0", name: "Amazon Nova Pro" },
      { id: "amazon.nova-lite-v1:0", name: "Amazon Nova Lite", tag: "Budget" },
    ],
  },
];

const INDUSTRIES = [
  "Technology",
  "Leadership Coaching",
  "Finance & Banking",
  "Healthcare",
  "E-commerce & Retail",
  "Marketing & Advertising",
  "Education",
  "Legal",
  "Real Estate",
  "Manufacturing",
  "Consulting",
  "Media & Entertainment",
  "SaaS",
  "Non-Profit",
  "Freelancing",
  "Other",
];

// ─── Step indicators ────────────────────────────────────────────

function StepDots({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center justify-center gap-2 mt-6">
      <span className="text-xs text-neutral-400 mr-1">{current} of {total}</span>
      {Array.from({ length: total }, (_, i) => (
        <div
          key={i}
          className={cn(
            "w-2 h-2 rounded-full transition-colors",
            i + 1 === current
              ? "bg-primary-500"
              : i + 1 < current
                ? "bg-primary-300"
                : "bg-neutral-300 dark:bg-neutral-600"
          )}
        />
      ))}
    </div>
  );
}

function StepProgress({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center justify-center gap-1 mb-6">
      <span className="text-xs text-neutral-400">Step {current} of {total}</span>
      <div className="flex items-center gap-0.5 ml-2">
        {Array.from({ length: total }, (_, i) => (
          <div
            key={i}
            className={cn(
              "h-1 rounded-full transition-colors",
              i + 1 <= current ? "bg-primary-500 w-8" : "bg-neutral-200 dark:bg-neutral-700 w-8"
            )}
          />
        ))}
      </div>
    </div>
  );
}

// ─── Tag input ──────────────────────────────────────────────────

function TagInput({
  tags,
  onChange,
  placeholder,
}: {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
}) {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const addTag = useCallback(
    (tag: string) => {
      const trimmed = tag.trim().toLowerCase();
      if (trimmed && !tags.includes(trimmed)) {
        onChange([...tags, trimmed]);
      }
      setInput("");
    },
    [tags, onChange]
  );

  const removeTag = (tag: string) => {
    onChange(tags.filter((t) => t !== tag));
  };

  return (
    <div
      className="flex flex-wrap items-center gap-2 px-3 py-2.5 rounded-xl bg-neutral-50 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 min-h-[44px] cursor-text focus-within:ring-2 focus-within:ring-primary-500/40 focus-within:border-primary-500 transition-all"
      onClick={() => inputRef.current?.focus()}
    >
      {tags.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-primary-100 dark:bg-primary-500/20 text-primary-700 dark:text-primary-300 text-xs font-medium"
        >
          {tag}
          <button
            onClick={(e) => {
              e.stopPropagation();
              removeTag(tag);
            }}
            className="hover:text-primary-900 dark:hover:text-white transition-colors"
          >
            <X className="w-3 h-3" />
          </button>
        </span>
      ))}
      <input
        ref={inputRef}
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            addTag(input);
          } else if (e.key === "Backspace" && !input && tags.length > 0) {
            onChange(tags.slice(0, -1));
          }
        }}
        onBlur={() => {
          if (input.trim()) addTag(input);
        }}
        placeholder={tags.length === 0 ? placeholder : ""}
        className="flex-1 min-w-[120px] bg-transparent text-sm text-neutral-900 dark:text-white placeholder:text-neutral-400 outline-none"
      />
    </div>
  );
}

// ─── Main wizard ────────────────────────────────────────────────

export default function WizardPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState<WizardStep>(1);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<"success" | "error" | null>(null);
  const [data, setData] = useState<WizardData>({
    name: "",
    provider: "",
    model: "",
    apiKey: "",
    businessName: "",
    industry: "",
    brandVoice: "",
    targetAudience: "",
    contentTopics: [],
  });

  const update = (field: keyof WizardData, value: string | string[]) => {
    setData((prev) => ({ ...prev, [field]: value }));
  };

  const selectedProvider = PROVIDERS.find((p) => p.id === data.provider);

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);
    await new Promise((resolve) => setTimeout(resolve, 1500));
    if (data.apiKey.length > 8 || data.provider === "ollama") {
      setTestResult("success");
    } else {
      setTestResult("error");
    }
    setTesting(false);
  };

  const handleComplete = () => {
    localStorage.setItem(
      "contextuai-solo-wizard",
      JSON.stringify({
        completed: true,
        name: data.name,
        provider: data.provider,
        businessName: data.businessName,
        industry: data.industry,
        brandVoice: data.brandVoice,
        targetAudience: data.targetAudience,
        contentTopics: data.contentTopics,
      })
    );
    if (data.apiKey) {
      localStorage.setItem("contextuai-solo-api-key", data.apiKey);
    }
    if (data.provider) {
      localStorage.setItem("contextuai-solo-provider", data.provider);
    }
    if (data.model) {
      localStorage.setItem("contextuai-solo-model", data.model);
    }
    navigate("/");
  };

  const inputCls = cn(
    "w-full px-4 py-3 rounded-xl text-sm",
    "bg-neutral-50 dark:bg-neutral-800",
    "border border-neutral-200 dark:border-neutral-700",
    "text-neutral-900 dark:text-white",
    "placeholder:text-neutral-400 dark:placeholder:text-neutral-500",
    "focus:outline-none focus:ring-2 focus:ring-primary-500/40 focus:border-primary-500",
    "transition-all"
  );

  // ── Step 1: Welcome ───────────────────────────────────────────

  if (step === 1) {
    return (
      <div className="min-h-screen bg-neutral-50 dark:bg-[#242523] flex items-center justify-center px-6">
        <div className="w-full max-w-md text-center">
          {/* Logo */}
          <div className="flex items-center justify-center gap-3 mb-8">
            <img src={logoImg} alt="ContextuAI" className="w-12 h-12 rounded-2xl shadow-lg shadow-primary-500/25" />
            <span className="text-2xl font-bold text-neutral-900 dark:text-white">
              ContextuAI <span className="text-primary-500">Solo</span>
            </span>
          </div>

          <p className="text-neutral-500 dark:text-neutral-400 mb-8">
            Your AI business assistant. Runs locally.
          </p>

          {/* Illustration area */}
          <div className="flex justify-center mb-8">
            <div className="relative w-40 h-28 flex items-center justify-center">
              <div className="w-32 h-24 rounded-xl bg-gradient-to-br from-neutral-100 to-neutral-200 dark:from-neutral-700 dark:to-neutral-800 flex items-center justify-center shadow-inner">
                <Sparkles className="w-10 h-10 text-primary-400" />
              </div>
              <div className="absolute -top-1 -right-1 w-5 h-5 text-primary-500 animate-pulse">
                <Sparkles className="w-full h-full" />
              </div>
              <div className="absolute -bottom-1 -left-2 w-4 h-4 text-primary-400 animate-pulse [animation-delay:500ms]">
                <Sparkles className="w-full h-full" />
              </div>
            </div>
          </div>

          {/* Name input card */}
          <div className="bg-white dark:bg-neutral-900 rounded-2xl border border-neutral-200 dark:border-neutral-800 p-6 shadow-sm text-left mb-6">
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
              What&apos;s your name?
            </label>
            <input
              type="text"
              value={data.name}
              onChange={(e) => update("name", e.target.value)}
              placeholder="Sarah"
              autoFocus
              className={inputCls}
              onKeyDown={(e) => {
                if (e.key === "Enter" && data.name.trim()) setStep(2);
              }}
            />
          </div>

          <StepDots current={1} total={3} />

          <div className="mt-6">
            <button
              onClick={() => setStep(2)}
              disabled={!data.name.trim()}
              className={cn(
                "w-full py-3.5 rounded-xl text-sm font-semibold transition-all",
                data.name.trim()
                  ? "bg-primary-500 hover:bg-primary-600 text-white shadow-lg shadow-primary-500/25"
                  : "bg-neutral-200 dark:bg-neutral-700 text-neutral-400 cursor-not-allowed"
              )}
            >
              Get Started
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Step 2: AI Provider ───────────────────────────────────────

  if (step === 2) {
    const needsKey = data.provider && data.provider !== "ollama";

    return (
      <div className="min-h-screen bg-neutral-50 dark:bg-[#242523] flex flex-col">
        {/* Title bar */}
        <div className="text-center text-xs text-neutral-400 py-3 border-b border-neutral-200 dark:border-neutral-800">
          ContextuAI Solo
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-8">
          <div className="max-w-xl mx-auto">
            <StepProgress current={2} total={3} />

            <h1 className="text-2xl font-bold text-neutral-900 dark:text-white text-center mb-8">
              Connect Your AI
            </h1>

            {/* Provider grid */}
            <div className="grid grid-cols-2 gap-3 mb-3">
              {PROVIDERS.slice(0, 4).map((provider) => {
                const Icon = provider.icon;
                const selected = data.provider === provider.id;
                return (
                  <button
                    key={provider.id}
                    onClick={() => {
                      update("provider", provider.id);
                      update("model", provider.models[0].id);
                      setTestResult(null);
                    }}
                    className={cn(
                      "relative flex items-start gap-3 p-4 rounded-xl border-2 text-left transition-all",
                      selected
                        ? "border-primary-500 bg-primary-50/50 dark:bg-primary-500/5"
                        : "border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 hover:border-neutral-300 dark:hover:border-neutral-700"
                    )}
                  >
                    {provider.badge && (
                      <span className={cn(
                        "absolute top-2 right-2 px-1.5 py-0.5 rounded text-[10px] font-semibold",
                        provider.badgeColor
                      )}>
                        {provider.badge}
                      </span>
                    )}
                    <div className={cn("p-2 rounded-lg flex-shrink-0", provider.iconBg)}>
                      <Icon className={cn("w-4 h-4", provider.iconColor)} />
                    </div>
                    <div className="min-w-0">
                      <span className="text-sm font-semibold text-neutral-900 dark:text-white block">
                        {provider.name}
                      </span>
                      <span className="text-[11px] text-neutral-500 dark:text-neutral-400 leading-tight whitespace-pre-line">
                        {provider.subtitle}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Bedrock - full width */}
            {(() => {
              const bedrock = PROVIDERS[4];
              const Icon = bedrock.icon;
              const selected = data.provider === bedrock.id;
              return (
                <button
                  onClick={() => {
                    update("provider", bedrock.id);
                    update("model", bedrock.models[0].id);
                    setTestResult(null);
                  }}
                  className={cn(
                    "w-full flex items-center gap-3 p-4 rounded-xl border-2 text-left transition-all mb-6",
                    selected
                      ? "border-primary-500 bg-primary-50/50 dark:bg-primary-500/5"
                      : "border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 hover:border-neutral-300 dark:hover:border-neutral-700"
                  )}
                >
                  <div className={cn("p-2 rounded-lg", bedrock.iconBg)}>
                    <Icon className={cn("w-4 h-4", bedrock.iconColor)} />
                  </div>
                  <div>
                    <span className="text-sm font-semibold text-neutral-900 dark:text-white">
                      {bedrock.name}
                    </span>
                    <span className="text-[11px] text-neutral-500 dark:text-neutral-400 ml-2">
                      {bedrock.subtitle}
                    </span>
                  </div>
                </button>
              );
            })()}

            {/* API Key section */}
            {needsKey && (
              <div className="space-y-3 mb-4">
                <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
                  {selectedProvider?.name} API Key
                </label>
                <input
                  type="password"
                  value={data.apiKey}
                  onChange={(e) => {
                    update("apiKey", e.target.value);
                    setTestResult(null);
                  }}
                  placeholder={`Enter your ${selectedProvider?.name} API key`}
                  className={inputCls}
                />
                <button
                  onClick={handleTestConnection}
                  disabled={!data.apiKey || testing}
                  className={cn(
                    "w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-medium transition-all border",
                    data.apiKey && !testing
                      ? "border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white hover:bg-neutral-50 dark:hover:bg-neutral-700"
                      : "border-neutral-200 dark:border-neutral-700 bg-neutral-100 dark:bg-neutral-800 text-neutral-400 cursor-not-allowed"
                  )}
                >
                  {testing ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    "Test Connection"
                  )}
                </button>
                {testResult === "success" && (
                  <p className="text-sm text-green-600 dark:text-green-400 flex items-center gap-1.5">
                    <Check className="w-4 h-4" /> Connected successfully!
                  </p>
                )}
                {testResult === "error" && (
                  <p className="text-sm text-red-500">
                    Connection failed. Please check your API key.
                  </p>
                )}
              </div>
            )}

            {data.provider === "ollama" && (
              <div className="p-4 bg-green-50 dark:bg-green-500/10 border border-green-200 dark:border-green-800 rounded-xl mb-4">
                <p className="text-sm text-green-700 dark:text-green-400">
                  Ollama runs models locally — no API key needed. Make sure Ollama is installed and running on your system.
                </p>
              </div>
            )}

            {/* Model selector */}
            {selectedProvider && (
              <div className="space-y-3 mb-6">
                <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
                  Preferred Model
                </label>
                <div className="grid gap-2">
                  {selectedProvider.models.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => update("model", m.id)}
                      className={cn(
                        "flex items-center justify-between px-4 py-2.5 rounded-xl border text-left text-sm transition-all",
                        data.model === m.id
                          ? "border-primary-500 bg-primary-50/50 dark:bg-primary-500/5"
                          : "border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 hover:border-neutral-300 dark:hover:border-neutral-600"
                      )}
                    >
                      <div className="flex items-center gap-2">
                        {data.model === m.id && (
                          <Check className="w-3.5 h-3.5 text-primary-500" />
                        )}
                        <span className={cn(
                          "font-medium",
                          data.model === m.id ? "text-primary-600 dark:text-primary-400" : "text-neutral-900 dark:text-white"
                        )}>
                          {m.name}
                        </span>
                      </div>
                      {m.tag && (
                        <span className={cn(
                          "text-[10px] font-medium px-2 py-0.5 rounded-full",
                          m.tag === "Recommended"
                            ? "bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400"
                            : m.tag === "Budget"
                              ? "bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400"
                              : "bg-neutral-100 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-300"
                        )}>
                          {m.tag}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
                {selectedProvider.pricingUrl && (
                  <p className="text-xs text-neutral-400 text-center">
                    Pricing changes often.{" "}
                    <a
                      href={selectedProvider.pricingUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary-500 hover:text-primary-400 underline underline-offset-2"
                    >
                      Check {selectedProvider.name} pricing
                    </a>
                  </p>
                )}
              </div>
            )}

            {/* Navigation */}
            <div className="flex items-center justify-between pt-4">
              <button
                onClick={() => setStep(1)}
                className="text-sm font-medium text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300 transition-colors"
              >
                Back
              </button>
              <div className="flex items-center gap-3">
                {!data.provider && (
                  <button
                    onClick={() => setStep(3)}
                    className="text-xs text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
                  >
                    Skip for now
                  </button>
                )}
                <button
                  onClick={() => setStep(3)}
                  className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-semibold bg-primary-500 hover:bg-primary-600 text-white shadow-lg shadow-primary-500/25 transition-all"
                >
                  Continue
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Step 3: Brand Voice ───────────────────────────────────────

  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-[#242523] flex flex-col">
      {/* Title bar */}
      <div className="text-center text-xs text-neutral-400 py-3 border-b border-neutral-200 dark:border-neutral-800">
        {data.name ? `${data.name}` : "ContextuAI Solo"} — Setup Wizard
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-8">
        <div className="max-w-xl mx-auto">
          <StepProgress current={3} total={3} />

          <div className="text-center mb-8">
            <h1 className="text-2xl font-bold text-neutral-900 dark:text-white mb-2">
              Tell Me About Your Brand
            </h1>
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              Define your brand&apos;s unique identity.
            </p>
          </div>

          <div className="bg-white dark:bg-neutral-900 rounded-2xl border border-neutral-200 dark:border-neutral-800 p-6 shadow-sm space-y-5 mb-6">
            {/* Business Name */}
            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                Business Name
              </label>
              <input
                type="text"
                value={data.businessName}
                onChange={(e) => update("businessName", e.target.value)}
                placeholder={data.name ? `${data.name}'s Business` : "e.g. Acme Corp"}
                className={inputCls}
              />
            </div>

            {/* Industry */}
            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                Industry
              </label>
              <select
                value={data.industry}
                onChange={(e) => update("industry", e.target.value)}
                className={cn(
                  inputCls,
                  "appearance-none",
                  !data.industry && "text-neutral-400 dark:text-neutral-500"
                )}
              >
                <option value="">Select your industry</option>
                {INDUSTRIES.map((industry) => (
                  <option key={industry} value={industry}>
                    {industry}
                  </option>
                ))}
              </select>
            </div>

            {/* Brand Voice */}
            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                Your Brand Voice
              </label>
              <p className="text-xs text-neutral-400 dark:text-neutral-500 mb-2">
                Describe how you communicate.{" "}
                <span className="italic">
                  Example: Warm, direct, evidence-based. I speak like a trusted advisor, not a marketer.
                </span>
              </p>
              <textarea
                value={data.brandVoice}
                onChange={(e) => update("brandVoice", e.target.value)}
                rows={3}
                placeholder="Describe your brand's tone and communication style..."
                className={cn(inputCls, "resize-none")}
              />
            </div>

            {/* Target Audience */}
            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                Target Audience
              </label>
              <input
                type="text"
                value={data.targetAudience}
                onChange={(e) => update("targetAudience", e.target.value)}
                placeholder="e.g. Mid-level managers transitioning to executive roles"
                className={inputCls}
              />
            </div>

            {/* Content Topics */}
            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                Content Topics
              </label>
              <TagInput
                tags={data.contentTopics}
                onChange={(tags) => update("contentTopics", tags)}
                placeholder="Type a topic and press Enter..."
              />
            </div>
          </div>

          {/* Info banner */}
          <div className="flex items-start gap-3 p-4 bg-primary-50 dark:bg-primary-500/5 border border-primary-200 dark:border-primary-800/50 rounded-xl mb-6">
            <Info className="w-4 h-4 text-primary-500 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-neutral-600 dark:text-neutral-400 leading-relaxed">
              Your brand voice shapes every piece of content the AI creates. You can always change this later in Settings.
            </p>
          </div>

          <StepDots current={3} total={3} />

          {/* Navigation */}
          <div className="flex items-center justify-between pt-6">
            <button
              onClick={() => setStep(2)}
              className="text-sm font-medium text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300 transition-colors"
            >
              Back
            </button>
            <button
              onClick={handleComplete}
              className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-semibold bg-primary-500 hover:bg-primary-600 text-white shadow-lg shadow-primary-500/25 transition-all"
            >
              Continue
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
