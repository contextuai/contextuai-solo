import { api } from "@/lib/transport";

export interface Approval {
  approval_id: string;
  trigger_id: string | null;
  channel_type: string;
  channel_id: string;
  sender_name: string;
  sender_id: string;
  inbound_text: string;
  draft_response: string;
  final_response: string | null;
  session_id: string | null;
  status: "pending" | "approved" | "rejected" | "edited";
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export async function listApprovals(
  status: string = "pending",
  limit: number = 50
): Promise<Approval[]> {
  const { data } = await api.get<{ approvals: Approval[] }>(
    `/approvals/?status=${status}&limit=${limit}`
  );
  return data.approvals;
}

export async function countPending(): Promise<number> {
  const { data } = await api.get<{ pending_count: number }>("/approvals/count");
  return data.pending_count;
}

export async function getApproval(approvalId: string): Promise<Approval> {
  const { data } = await api.get<{ approval: Approval }>(`/approvals/${approvalId}`);
  return data.approval;
}

export async function approveApproval(
  approvalId: string,
  editedResponse?: string
): Promise<Approval> {
  const body = editedResponse ? { edited_response: editedResponse } : {};
  const { data } = await api.post<{ approval: Approval }>(
    `/approvals/${approvalId}/approve`,
    body
  );
  return data.approval;
}

export async function rejectApproval(approvalId: string): Promise<Approval> {
  const { data } = await api.post<{ approval: Approval }>(
    `/approvals/${approvalId}/reject`
  );
  return data.approval;
}
