import { api } from "@/lib/transport";

export interface EnterprisePolicy {
  catalog_url: string | null;
  catalog_exclusive: boolean;
  require_sha256: boolean;
  airplane_lock_enforced: boolean;
  allowed_model_sha256?: Record<string, string> | string[] | null;
  locked_fields: string[];
  policy_source: string;
  policy_file?: string | null;
}

export interface EnterprisePolicyUpdate {
  catalog_url?: string | null;
  catalog_exclusive?: boolean;
  require_sha256?: boolean;
}

export interface CatalogSyncResult {
  status: string;
  source: string;
  merged_count: number;
  total_catalog_models: number;
  exclusive?: boolean;
  catalog_url?: string | null;
}

export interface ModelVerifyResult {
  model_id: string;
  path: string;
  verified: boolean;
  sha256: string;
  expected_sha256: string | null;
}

const BASE = "/enterprise";

export async function getEnterprisePolicy(): Promise<EnterprisePolicy> {
  const { data } = await api.get<EnterprisePolicy>(`${BASE}/policy`);
  return data;
}

export async function updateEnterprisePolicy(
  patch: EnterprisePolicyUpdate
): Promise<EnterprisePolicy> {
  const { data } = await api.put<EnterprisePolicy>(`${BASE}/policy`, patch);
  return data;
}

export async function syncEnterpriseCatalog(params?: {
  remote_url?: string;
  exclusive?: boolean;
}): Promise<CatalogSyncResult> {
  const { data } = await api.post<CatalogSyncResult>(
    `${BASE}/catalog/sync`,
    params ?? {}
  );
  return data;
}

export async function verifyModelIntegrity(
  modelId: string,
  body?: { expected_sha256?: string; require_checksum?: boolean }
): Promise<ModelVerifyResult> {
  const { data } = await api.post<ModelVerifyResult>(
    `${BASE}/models/${encodeURIComponent(modelId)}/verify`,
    body ?? {}
  );
  return data;
}
