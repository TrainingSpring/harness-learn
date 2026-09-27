import { apiClient } from "../../api/client";
import type {
  AgentDetail,
  AgentProfileSuggestion,
  AgentProfileSuggestionRequest,
  AgentSummary,
  CreateAgentRequest,
  UpdateAgentRequest,
  ListResponse,
} from "../../api/types";

export function listAgents(): Promise<ListResponse<AgentSummary>> {
  return apiClient.get("/api/agents?limit=100&offset=0");
}

export function getAgent(agentId: string): Promise<AgentDetail> {
  return apiClient.get(`/api/agents/${encodeURIComponent(agentId)}`);
}

/** 创建角色并返回服务端生成 ID 后的详情。 */
export function createAgent(request: CreateAgentRequest): Promise<AgentDetail> {
  return apiClient.post<CreateAgentRequest, AgentDetail>("/api/agents", request);
}

export function updateAgent(agentId: string, request: UpdateAgentRequest): Promise<AgentDetail> {
  return apiClient.patch<UpdateAgentRequest, AgentDetail>(`/api/agents/${encodeURIComponent(agentId)}`, request);
}

/** 使用用户选定的 LLM，根据描述生成角色草案。 */
export function generateAgentProfileSuggestion(
  request: AgentProfileSuggestionRequest,
): Promise<AgentProfileSuggestion> {
  return apiClient.post<AgentProfileSuggestionRequest, AgentProfileSuggestion>(
    "/api/agents/profile-suggestion",
    request,
  );
}
