import { api } from "@/lib/transport";

export type DlpCategoryKey =
  | "api_keys"
  | "emails"
  | "phones"
  | "ssns"
  | "credit_cards"
  | "custom";

export interface DlpCustomRule {
  id: string;
  name: string;
  pattern: string;
  placeholder: string;
  enabled: boolean;
}

export interface DlpCategories {
  api_keys: boolean;
  emails: boolean;
  phones: boolean;
  ssns: boolean;
  credit_cards: boolean;
  custom: boolean;
}

export interface DlpSettings {
  enabled: boolean;
  redact_logs: boolean;
  categories: DlpCategories;
  custom_rules: DlpCustomRule[];
  policy_path?: string;
}

export interface DlpSettingsUpdate {
  enabled?: boolean;
  redact_logs?: boolean;
  categories?: Partial<DlpCategories>;
  custom_rules?: Array<
    Partial<DlpCustomRule> & { name: string; pattern: string }
  >;
}

export interface DlpTestResponse {
  redacted_text: string;
  total_redactions: number;
  categories: string[];
  counts_by_category: Record<string, number>;
}

export async function getDlpSettings(): Promise<DlpSettings> {
  const { data } = await api.get<DlpSettings>("/dlp/settings");
  return data;
}

export async function updateDlpSettings(
  patch: DlpSettingsUpdate
): Promise<DlpSettings> {
  const { data } = await api.put<DlpSettings>("/dlp/settings", patch);
  return data;
}

export async function testDlpRedaction(text: string): Promise<DlpTestResponse> {
  const { data } = await api.post<DlpTestResponse>("/dlp/test", { text });
  return data;
}
