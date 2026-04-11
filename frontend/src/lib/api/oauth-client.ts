import { api } from "@/lib/transport";

export interface OAuthStatus {
  provider: string;
  connected: boolean;
  profile_name?: string;
  profile_id?: string;
  connected_at?: string;
  scopes?: string[];
}

export interface OAuthAuthorizeResponse {
  auth_url: string;
  state: string;
  provider: string;
}

export async function configureOAuthClient(
  provider: string,
  clientId: string,
  clientSecret: string
): Promise<void> {
  await api.post(`/oauth/${provider}/configure`, {
    client_id: clientId,
    client_secret: clientSecret,
  });
}

export async function getOAuthAuthorizeUrl(
  provider: string
): Promise<OAuthAuthorizeResponse> {
  const { data } = await api.get<OAuthAuthorizeResponse>(
    `/oauth/${provider}/authorize`
  );
  return data;
}

export async function getOAuthStatus(provider: string): Promise<OAuthStatus> {
  const { data } = await api.get<OAuthStatus>(`/oauth/${provider}/status`);
  return data;
}

export interface OAuthTestResult {
  provider: string;
  success: boolean;
  message: string;
  profile_name?: string;
  profile_id?: string;
  response_time_ms?: number;
}

export async function testOAuthConnection(
  provider: string
): Promise<OAuthTestResult> {
  const { data } = await api.post<OAuthTestResult>(`/oauth/${provider}/test`);
  return data;
}

export async function disconnectOAuth(provider: string): Promise<void> {
  await api.delete(`/oauth/${provider}`);
}
