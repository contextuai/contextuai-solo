import { api } from "@/lib/transport";

export interface RedditAccount {
  _id: string;
  client_id: string;
  client_secret: string;
  username: string;
  password: string;
  user_agent: string;
  subreddits: string[];
  keywords: string[];
  poll_inbox: boolean;
  enabled: boolean;
  last_seen_ids: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface CreateRedditAccountPayload {
  client_id: string;
  client_secret: string;
  username: string;
  password: string;
  user_agent?: string;
  subreddits?: string[];
  keywords?: string[];
  poll_inbox?: boolean;
}

export interface UpdateRedditAccountPayload {
  subreddits?: string[];
  keywords?: string[];
  poll_inbox?: boolean;
  enabled?: boolean;
}

export async function getRedditAccount(): Promise<RedditAccount | null> {
  const { data, ok } = await api.get<{ account: RedditAccount | null }>("/reddit/account");
  if (!ok) return null;
  return data.account ?? null;
}

export async function createRedditAccount(
  payload: CreateRedditAccountPayload,
): Promise<RedditAccount> {
  const { data } = await api.post<{ account: RedditAccount }>("/reddit/account", payload);
  return data.account;
}

export async function updateRedditAccount(
  id: string,
  payload: UpdateRedditAccountPayload,
): Promise<RedditAccount> {
  const { data } = await api.put<{ account: RedditAccount }>(`/reddit/account/${id}`, payload);
  return data.account;
}

export async function deleteRedditAccount(id: string): Promise<boolean> {
  const { ok } = await api.delete<{ deleted: boolean }>(`/reddit/account/${id}`);
  return ok;
}

export async function testRedditConnection(): Promise<{ ok: boolean; username?: string }> {
  const { data, ok } = await api.post<{ ok: boolean; username?: string }>("/reddit/test", {});
  return ok ? data : { ok: false };
}

export async function replyOnReddit(payload: {
  target_type: "comment" | "submission" | "dm";
  target_id: string;
  text: string;
  recipient?: string;
}): Promise<{ ok: boolean; reply_id?: string }> {
  const { data, ok } = await api.post<{ ok: boolean; reply_id?: string }>("/reddit/reply", payload);
  return ok ? data : { ok: false };
}
