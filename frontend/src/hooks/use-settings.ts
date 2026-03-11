import { useState, useCallback } from "react";
import type { AppSettings, AIProviderConfig, BrandVoiceConfig } from "@/types/settings";

const STORAGE_KEY = "contextuai-solo-settings";

const defaultSettings: AppSettings = {
  theme: "system",
  font_size: "medium",
  sidebar_default: "expanded",
  ai_providers: [],
  brand_voice: {
    business_name: "",
    industry: "",
    description: "",
    voice: "",
    target_audience: "",
    topics: [],
  },
};

function loadSettings(): AppSettings {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      return { ...defaultSettings, ...parsed, brand_voice: { ...defaultSettings.brand_voice, ...parsed.brand_voice } };
    }
  } catch {
    // ignore parse errors
  }
  return defaultSettings;
}

export function useSettings() {
  const [settings, setSettings] = useState<AppSettings>(loadSettings);
  const [saving, setSaving] = useState(false);

  const updateSettings = useCallback((partial: Partial<AppSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...partial };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const updateBrandVoice = useCallback((partial: Partial<BrandVoiceConfig>) => {
    setSettings((prev) => {
      const next = {
        ...prev,
        brand_voice: { ...prev.brand_voice, ...partial },
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const updateProvider = useCallback((index: number, partial: Partial<AIProviderConfig>) => {
    setSettings((prev) => {
      const providers = [...prev.ai_providers];
      providers[index] = { ...providers[index], ...partial };
      const next = { ...prev, ai_providers: providers };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const setActiveProvider = useCallback((providerName: string) => {
    setSettings((prev) => {
      const providers = prev.ai_providers.map((p) => ({
        ...p,
        is_active: p.provider === providerName,
      }));
      const next = { ...prev, ai_providers: providers };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const saveBrandVoice = useCallback(async () => {
    setSaving(true);
    // Simulate save delay (will migrate to API later)
    await new Promise((r) => setTimeout(r, 400));
    setSaving(false);
  }, []);

  return {
    settings,
    updateSettings,
    updateBrandVoice,
    updateProvider,
    setActiveProvider,
    saveBrandVoice,
    saving,
  };
}
