import { api } from "@/lib/transport";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ConnectionPlatform =
  | "telegram"
  | "discord"
  | "reddit"
  | "twitter"
  | "linkedin"
  | "instagram"
  | "facebook"
  | "blog"
  | "email"
  | "slack_webhook";

export type ConnectionStore =
  | "oauth_connections"
  | "reddit_accounts"
  | "twitter_accounts"
  | "channel_registrations"
  | "distribution_channels";

export interface ConnectionSummary {
  id: string;
  platform: ConnectionPlatform;
  store: ConnectionStore;
  display_name?: string | null;
  connected: boolean;
  inbound_enabled: boolean;
  outbound_enabled: boolean;
  inbound_supported: boolean;
  outbound_supported: boolean;
  config_summary: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ConnectionListResponse {
  success: boolean;
  connections: ConnectionSummary[];
  total_count: number;
}

export interface CapabilityUpdate {
  inbound_enabled?: boolean;
  outbound_enabled?: boolean;
}

export type OutboundPlatform = "blog" | "email" | "slack_webhook";

export interface OutboundConnectionCreate {
  platform: OutboundPlatform;
  name: string;
  config: Record<string, unknown>;
  enabled?: boolean;
}

export interface OutboundConnectionUpdate {
  name?: string;
  config?: Record<string, unknown>;
  enabled?: boolean;
}

// ---------------------------------------------------------------------------
// API client
// ---------------------------------------------------------------------------

export const connectionsApi = {
  list: async (): Promise<ConnectionSummary[]> => {
    const { data } = await api.get<ConnectionListResponse>("/connections");
    return data.connections ?? [];
  },

  get: async (id: string): Promise<ConnectionSummary> => {
    const { data } = await api.get<ConnectionSummary>(`/connections/${encodeURIComponent(id)}`);
    return data;
  },

  updateCapabilities: async (
    id: string,
    update: CapabilityUpdate,
  ): Promise<ConnectionSummary> => {
    const { data } = await api.patch<ConnectionSummary>(
      `/connections/${encodeURIComponent(id)}/capabilities`,
      update,
    );
    return data;
  },

  createOutbound: async (payload: OutboundConnectionCreate): Promise<ConnectionSummary> => {
    const { data } = await api.post<ConnectionSummary>("/connections/outbound", payload);
    return data;
  },

  updateOutbound: async (
    id: string,
    update: OutboundConnectionUpdate,
  ): Promise<ConnectionSummary> => {
    const { data } = await api.put<ConnectionSummary>(
      `/connections/outbound/${encodeURIComponent(id)}`,
      update,
    );
    return data;
  },

  deleteOutbound: async (id: string): Promise<void> => {
    await api.delete(`/connections/outbound/${encodeURIComponent(id)}`);
  },
};
