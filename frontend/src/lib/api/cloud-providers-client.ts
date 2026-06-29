import { api } from "@/lib/transport";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type CloudProviderType =
  | "anthropic"
  | "openai"
  | "google"
  | "bedrock"
  | "ollama";

export interface CloudProvider {
  provider_id: string;
  provider_type: CloudProviderType;
  display_name: string;
  connected: boolean;
  last_tested_at: string | null;
  last_test_status: "ok" | "failed" | null;
  last_test_error: string | null;
  config: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface TestResult {
  ok: boolean;
  latency_ms: number;
  error?: string;
}

export interface CloudProviderListResponse {
  success: boolean;
  providers: CloudProvider[];
  total_count: number;
}

export interface SaveCloudProviderInput {
  provider_type: CloudProviderType;
  display_name?: string;
  config: Record<string, string>;
}

export type UpdateCloudProviderInput = Partial<SaveCloudProviderInput>;

export interface TestCloudProviderInput {
  provider_type: CloudProviderType;
  config: Record<string, string>;
}

// ---------------------------------------------------------------------------
// CRUD
// ---------------------------------------------------------------------------

export async function listCloudProviders(): Promise<CloudProvider[]> {
  const { data } = await api.get<CloudProviderListResponse>("/cloud-providers");
  return data.providers || [];
}

export async function saveCloudProvider(
  input: SaveCloudProviderInput,
): Promise<CloudProvider> {
  const { data } = await api.post<CloudProvider>("/cloud-providers", input);
  return data;
}

export async function getCloudProvider(id: string): Promise<CloudProvider> {
  const { data } = await api.get<CloudProvider>(`/cloud-providers/${id}`);
  return data;
}

export async function updateCloudProvider(
  id: string,
  input: UpdateCloudProviderInput,
): Promise<CloudProvider> {
  const { data } = await api.put<CloudProvider>(
    `/cloud-providers/${id}`,
    input,
  );
  return data;
}

export async function deleteCloudProvider(id: string): Promise<void> {
  await api.delete(`/cloud-providers/${id}`);
}

// ---------------------------------------------------------------------------
// Test
// ---------------------------------------------------------------------------

export async function testCloudProvider(
  input: TestCloudProviderInput,
): Promise<TestResult> {
  const { data } = await api.post<TestResult>("/cloud-providers/test", input);
  return data;
}

export async function testSavedCloudProvider(id: string): Promise<TestResult> {
  const { data } = await api.post<TestResult>(`/cloud-providers/${id}/test`);
  return data;
}
