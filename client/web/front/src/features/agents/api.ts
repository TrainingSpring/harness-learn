import { apiClient } from "../../api/client";
import type { AgentDetail, AgentSummary, ListResponse } from "../../api/types";

export function listAgents(): Promise<ListResponse<AgentSummary>> {
  return apiClient.get("/api/agents?limit=100&offset=0");
}

export function getAgent(agentId: string): Promise<AgentDetail> {
  return apiClient.get(`/api/agents/${encodeURIComponent(agentId)}`);
}
