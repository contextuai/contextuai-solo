import { api } from "@/lib/transport";

// ─── Inbound Channels (Telegram, Discord) ──────────────────────

export interface ChannelRegistration {
  id: string;
  channel_type: "telegram" | "discord";
  config: Record<string, string>;
  status: "active" | "inactive" | "error";
  created_at?: string;
  updated_at?: string;
}

export interface ChannelStatus {
  telegram: { configured: boolean; status: string };
  discord: { configured: boolean; status: string };
}

export async function getChannelStatus(): Promise<ChannelStatus> {
  const { data } = await api.get<ChannelStatus>("/channels/status");
  return data;
}

export async function getChannelRegistrations(): Promise<ChannelRegistration[]> {
  const { data } = await api.get<{ registrations: ChannelRegistration[] } | ChannelRegistration[]>(
    "/channels/registrations"
  );
  if (Array.isArray(data)) return data;
  return (data as { registrations: ChannelRegistration[] }).registrations ?? [];
}

export async function registerChannel(
  channelType: "telegram" | "discord",
  config: Record<string, string>
): Promise<ChannelRegistration> {
  const { data } = await api.post<ChannelRegistration>("/channels/registrations", {
    channel_type: channelType,
    config,
  });
  return data;
}

// ─── Distribution Channels (LinkedIn) ──────────────────────────

export interface DistributionChannel {
  id: string;
  channel_type: "linkedin";
  name: string;
  config: Record<string, string>;
  enabled: boolean;
  created_at?: string;
  updated_at?: string;
}

export async function getDistributionChannels(): Promise<DistributionChannel[]> {
  const { data } = await api.get<{ channels: DistributionChannel[] } | DistributionChannel[]>(
    "/distribution/channels"
  );
  if (Array.isArray(data)) return data;
  return (data as { channels: DistributionChannel[] }).channels ?? [];
}

export async function createDistributionChannel(
  channelType: "linkedin",
  name: string,
  config: Record<string, string>
): Promise<DistributionChannel> {
  const { data } = await api.post<DistributionChannel>("/distribution/channels", {
    channel_type: channelType,
    name,
    config,
  });
  return data;
}

export async function updateDistributionChannel(
  id: string,
  updates: { name?: string; config?: Record<string, string> }
): Promise<DistributionChannel> {
  const { data } = await api.patch<DistributionChannel>(`/distribution/channels/${id}`, updates);
  return data;
}

export async function deleteDistributionChannel(id: string): Promise<void> {
  await api.delete(`/distribution/channels/${id}`);
}

export async function toggleDistributionChannel(id: string, enabled: boolean): Promise<void> {
  await api.patch(`/distribution/channels/${id}/toggle`, { enabled });
}
