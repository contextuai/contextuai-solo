import { api } from "@/lib/transport";

export interface Trigger {
  trigger_id: string;
  channel_type: string;
  channel_id: string;
  crew_id: string | null;
  agent_id: string | null;
  enabled: boolean;
  approval_required: boolean;
  cooldown_seconds: number;
  last_fired_at: string | null;
  fire_count: number;
  created_at: string;
  updated_at: string;
}

export interface CreateTriggerPayload {
  channel_type: string;
  channel_id?: string;
  crew_id?: string;
  agent_id?: string;
  enabled?: boolean;
  approval_required?: boolean;
  cooldown_seconds?: number;
}

export interface UpdateTriggerPayload {
  crew_id?: string | null;
  agent_id?: string | null;
  enabled?: boolean;
  approval_required?: boolean;
  cooldown_seconds?: number;
}

export async function listTriggers(channelType?: string): Promise<Trigger[]> {
  const params = channelType ? `?channel_type=${channelType}` : "";
  const { data, ok } = await api.get<{ triggers: Trigger[] }>(`/triggers/${params}`);
  if (!ok) return [];
  return data.triggers ?? [];
}

export async function createTrigger(payload: CreateTriggerPayload): Promise<Trigger> {
  const { data } = await api.post<{ trigger: Trigger }>("/triggers/", payload);
  return data.trigger;
}

export async function updateTrigger(
  triggerId: string,
  payload: UpdateTriggerPayload
): Promise<Trigger> {
  const { data } = await api.put<{ trigger: Trigger }>(`/triggers/${triggerId}`, payload);
  return data.trigger;
}

export async function deleteTrigger(triggerId: string): Promise<void> {
  await api.delete(`/triggers/${triggerId}`);
}
