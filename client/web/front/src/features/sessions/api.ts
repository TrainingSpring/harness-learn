import { apiClient } from "../../api/client";
import type { ContextItemResponse, CreateDirectSessionRequest, ListResponse, SessionDetail, SessionSummary } from "../../api/types";

interface ContextItemList {
  items: ContextItemResponse[];
}

export function listSessions(): Promise<ListResponse<SessionSummary>> {
  return apiClient.get("/api/sessions?limit=30&offset=0");
}

export function createSession(request: CreateDirectSessionRequest): Promise<SessionSummary> {
  return apiClient.post("/api/sessions", request);
}

export function getSession(sessionId: string): Promise<SessionDetail> {
  return apiClient.get(`/api/sessions/${encodeURIComponent(sessionId)}`);
}

export function listMessages(sessionId: string): Promise<ContextItemList> {
  return apiClient.get(`/api/sessions/${encodeURIComponent(sessionId)}/messages?afterSequence=0`);
}
