import { apiClient } from "../../api/client";
import type { ListResponse, LLMProfileSummary, ToolSummary } from "../../api/types";

export function listLlmProfiles(): Promise<ListResponse<LLMProfileSummary>> {
  return apiClient.get("/api/settings/llm-profiles?limit=100&offset=0");
}

export function listTools(): Promise<ListResponse<ToolSummary>> {
  return apiClient.get("/api/settings/tools");
}
