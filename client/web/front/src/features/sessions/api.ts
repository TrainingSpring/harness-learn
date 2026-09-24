import { apiClient } from "../../api/client";
import type { ContextItemResponse, CreateDirectSessionRequest, ListResponse, PermissionMode, SessionDetail, SessionSummary, WorkspaceDirectoryResponse } from "../../api/types";

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

export function updateSessionPermissionMode(sessionId: string, permissionMode: PermissionMode): Promise<SessionSummary> {
  return apiClient.patch<{ permissionMode: PermissionMode }, SessionSummary>(`/api/sessions/${encodeURIComponent(sessionId)}/permission-mode`, { permissionMode });
}

export function updateSessionWorkspace(sessionId: string, workspacePath: string | null): Promise<SessionSummary> {
  return apiClient.patch<{ workspacePath: string | null }, SessionSummary>(`/api/sessions/${encodeURIComponent(sessionId)}/workspace`, { workspacePath });
}

export function listWorkspaceDirectories(path = "."): Promise<WorkspaceDirectoryResponse> {
  return apiClient.get(`/api/sessions/projects?path=${encodeURIComponent(path)}`);
}
