import { api } from "@/lib/transport";

export interface ModelConfig {
  id: string;
  name: string;
  provider: string;
  model: string;
  max_tokens: string;
  enabled: boolean;
  description: string;
  capabilities: string[];
  input_cost: number;
  output_cost: number;
  context_window: number;
  supports_vision: boolean;
  supports_function_calling: boolean;
}

export async function getModels(): Promise<ModelConfig[]> {
  const { data } = await api.get<{ models: ModelConfig[] } | ModelConfig[]>("/models/");
  // Backend wraps models in { models: [...] }
  if (Array.isArray(data)) return data;
  return (data as { models: ModelConfig[] }).models ?? [];
}
