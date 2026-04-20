import { api } from "@/lib/transport";

export interface TwitterAccount {
  _id: string;
  api_key?: string;
  api_secret?: string;
  access_token?: string;
  access_token_secret?: string;
  bearer_token?: string;
  user_id: string;
  keywords: string[];
  poll_mentions: boolean;
  poll_dms: boolean;
  enabled: boolean;
  last_seen_ids: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface CreateTwitterAccountPayload {
  api_key?: string;
  api_secret?: string;
  access_token?: string;
  access_token_secret?: string;
  bearer_token?: string;
  user_id: string;
  keywords?: string[];
  poll_mentions?: boolean;
  poll_dms?: boolean;
}

export interface UpdateTwitterAccountPayload {
  keywords?: string[];
  poll_mentions?: boolean;
  poll_dms?: boolean;
  enabled?: boolean;
}

export async function getTwitterAccount(): Promise<TwitterAccount | null> {
  const { data, ok } = await api.get<{ account: TwitterAccount | null }>("/twitter/account");
  if (!ok) return null;
  return data.account ?? null;
}

export async function createTwitterAccount(
  payload: CreateTwitterAccountPayload,
): Promise<TwitterAccount> {
  const { data } = await api.post<{ account: TwitterAccount }>("/twitter/account", payload);
  return data.account;
}

export async function updateTwitterAccount(
  id: string,
  payload: UpdateTwitterAccountPayload,
): Promise<TwitterAccount> {
  const { data } = await api.put<{ account: TwitterAccount }>(`/twitter/account/${id}`, payload);
  return data.account;
}

export async function deleteTwitterAccount(id: string): Promise<boolean> {
  const { ok } = await api.delete<{ deleted: boolean }>(`/twitter/account/${id}`);
  return ok;
}

export async function testTwitterConnection(): Promise<{
  ok: boolean;
  id?: string;
  username?: string;
  name?: string;
}> {
  const { data, ok } = await api.post<{
    ok: boolean;
    id?: string;
    username?: string;
    name?: string;
  }>("/twitter/test", {});
  return ok ? data : { ok: false };
}

export async function replyOnTwitter(payload: {
  target_type: "tweet" | "dm";
  target_id: string;
  text: string;
  recipient?: string;
}): Promise<{ ok: boolean; tweet_id?: string; dm_event_id?: string }> {
  const { data, ok } = await api.post<{
    ok: boolean;
    tweet_id?: string;
    dm_event_id?: string;
  }>("/twitter/reply", payload);
  return ok ? data : { ok: false };
}
