import { apiClient } from "../../api/client";
import type { AgentDetail, AgentSummary, CreateAgentRequest, ListResponse } from "../../api/types";

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
