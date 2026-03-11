export interface AIProviderConfig {
  provider: string;
  api_key?: string;
  base_url?: string;
  default_model?: string;
  is_active: boolean;
  status: "connected" | "disconnected" | "error";
}

export interface BrandVoiceConfig {
  business_name: string;
  industry: string;
  description: string;
  voice: string;
  target_audience: string;
  topics: string[];
}

export interface AppSettings {
  theme: "light" | "dark" | "system";
  font_size: "small" | "medium" | "large";
  sidebar_default: "expanded" | "collapsed";
  ai_providers: AIProviderConfig[];
  brand_voice: BrandVoiceConfig;
}
