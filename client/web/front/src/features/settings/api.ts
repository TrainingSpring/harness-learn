import { apiClient } from "../../api/client";
import type { CreateLLMProfileRequest, ListResponse, LLMProfileSummary, ToolSummary } from "../../api/types";

export function listLlmProfiles(): Promise<ListResponse<LLMProfileSummary>> {
  return apiClient.get("/api/settings/llm-profiles?limit=100&offset=0");
}

/** 创建 LLM 配置并返回不含凭据引用的摘要。 */
export function createLlmProfile(request: CreateLLMProfileRequest): Promise<LLMProfileSummary> {
  return apiClient.post<CreateLLMProfileRequest, LLMProfileSummary>("/api/settings/llm-profiles", request);
}

export function listTools(): Promise<ListResponse<ToolSummary>> {
  return apiClient.get("/api/settings/tools");
}
