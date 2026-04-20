import { api } from "@/lib/transport";

// ─── Types ──────────────────────────────────────────────────────

export type DistributionChannelType =
  | "linkedin"
  | "twitter"
  | "instagram"
  | "facebook"
  | "blog"
  | "email"
  | "slack";

export type DeliveryStatus = "pending" | "published" | "failed" | "scheduled";

export interface ChannelConstraints {
  max_length?: number;
  supports_html?: boolean;
  supports_images?: boolean;
  supports_links?: boolean;
}

export interface ChannelTypeInfo {
  type: DistributionChannelType;
  constraints: ChannelConstraints;
  required_config: string[];
}

export interface DistributionChannel {
  id?: string;
  channel_id: string;
  channel_type: DistributionChannelType;
  name: string;
  config: Record<string, unknown>;
  organization: string | null;
  enabled: boolean;
  publish_count: number;
  last_published_at: string | null;
  created_at: string;
  updated_at: string;
  created_by: string | null;
}

export interface CreateChannelBody {
  channel_type: DistributionChannelType;
  name: string;
  config: Record<string, unknown>;
}

export interface UpdateChannelBody {
  name?: string;
  config?: Record<string, unknown>;
}

export interface PublishMetadata {
  image_url?: string;
  to_emails?: string[];
  status?: string;
  [key: string]: unknown;
}

export interface PublishRequestBody {
  channel_id: string;
  content: string;
  title?: string;
  metadata?: PublishMetadata;
}

export interface MultiPublishRequestBody {
  channel_ids: string[];
  content: string;
  title?: string;
  metadata?: PublishMetadata;
}

export interface PublishResult {
  success?: boolean;
  error?: string;
  status_code?: number;
  post_id?: string;
  tweet_id?: string;
  [key: string]: unknown;
}

export interface Delivery {
  id?: string;
  delivery_id: string;
  channel_id: string;
  channel_type: DistributionChannelType;
  channel_name: string | null;
  title: string | null;
  content_length: number;
  status: DeliveryStatus;
  result: PublishResult;
  metadata: PublishMetadata | null;
  published_by: string | null;
  timestamp: string;
}

export interface MultiPublishResult {
  total_channels: number;
  published: number;
  failed: number;
  deliveries: Delivery[];
}

interface ApiEnvelope<T> {
  status: string;
  data: T;
  message?: string;
}

// ─── Channel Types ──────────────────────────────────────────────

export async function listChannelTypes(): Promise<ChannelTypeInfo[]> {
  const { data } = await api.get<ApiEnvelope<{ types: ChannelTypeInfo[]; count: number }>>(
    "/distribution/types"
  );
  return data.data?.types ?? [];
}

// ─── Channel CRUD ───────────────────────────────────────────────

export async function listChannels(
  channelType?: DistributionChannelType
): Promise<DistributionChannel[]> {
  const qs = channelType ? `?channel_type=${encodeURIComponent(channelType)}` : "";
  const { data } = await api.get<ApiEnvelope<{ channels: DistributionChannel[]; count: number }>>(
    `/distribution/channels${qs}`
  );
  return data.data?.channels ?? [];
}

export async function getChannel(channelId: string): Promise<DistributionChannel> {
  const { data } = await api.get<ApiEnvelope<DistributionChannel>>(
    `/distribution/channels/${encodeURIComponent(channelId)}`
  );
  return data.data;
}

export async function createChannel(
  body: CreateChannelBody
): Promise<DistributionChannel> {
  const { data } = await api.post<ApiEnvelope<DistributionChannel>>(
    "/distribution/channels",
    body
  );
  return data.data;
}

export async function updateChannel(
  channelId: string,
  body: UpdateChannelBody
): Promise<DistributionChannel> {
  const { data } = await api.patch<ApiEnvelope<DistributionChannel>>(
    `/distribution/channels/${encodeURIComponent(channelId)}`,
    body
  );
  return data.data;
}

export async function deleteChannel(channelId: string): Promise<void> {
  await api.delete(`/distribution/channels/${encodeURIComponent(channelId)}`);
}

export async function toggleChannel(
  channelId: string,
  enabled: boolean
): Promise<DistributionChannel> {
  const { data } = await api.patch<ApiEnvelope<DistributionChannel>>(
    `/distribution/channels/${encodeURIComponent(channelId)}/toggle`,
    { enabled }
  );
  return data.data;
}

// ─── Publishing ─────────────────────────────────────────────────

export async function publish(body: PublishRequestBody): Promise<Delivery> {
  const { data } = await api.post<ApiEnvelope<Delivery>>(
    "/distribution/publish",
    body
  );
  return data.data;
}

export async function publishMulti(
  body: MultiPublishRequestBody
): Promise<MultiPublishResult> {
  const { data } = await api.post<ApiEnvelope<MultiPublishResult>>(
    "/distribution/publish/multi",
    body
  );
  return data.data;
}

// ─── Delivery History ───────────────────────────────────────────

export async function listDeliveries(
  channelId?: string,
  limit: number = 50
): Promise<Delivery[]> {
  const params = new URLSearchParams();
  if (channelId) params.set("channel_id", channelId);
  params.set("limit", String(limit));
  const { data } = await api.get<ApiEnvelope<{ deliveries: Delivery[]; count: number }>>(
    `/distribution/deliveries?${params.toString()}`
  );
  return data.data?.deliveries ?? [];
}
