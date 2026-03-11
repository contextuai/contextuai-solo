import { api } from "@/lib/transport";

export interface AnalyticsSummary {
  total_chats: number;
  total_tokens: number;
  total_cost: number;
  total_crews_run: number;
  total_agents_used: number;
  total_workshops: number;
  daily_usage: { date: string; chats: number; tokens: number; cost: number }[];
  feature_usage: { feature: string; count: number }[];
  top_models: { model: string; count: number; tokens: number }[];
  top_agents: { agent: string; runs: number }[];
}

export async function getAnalyticsSummary(
  startDate: string,
  endDate: string
): Promise<AnalyticsSummary> {
  const { data } = await api.get<AnalyticsSummary>(
    `/analytics/summary/?start_date=${startDate}&end_date=${endDate}`
  );
  return data;
}
