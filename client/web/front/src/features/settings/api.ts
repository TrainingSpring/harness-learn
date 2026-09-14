import { apiClient } from "../../api/client";
import type {
  CreateLLMProfileRequest,
  ListResponse,
  LLMProfileSummary,
  ToolSummary,
  UpdateLLMProfileRequest,
} from "../../api/types";

export function listLlmProfiles(): Promise<ListResponse<LLMProfileSummary>> {
  return apiClient.get("/api/settings/llm-profiles?limit=100&offset=0");
}

/** 创建 LLM 配置并返回不含凭据引用的摘要。 */
export function createLlmProfile(request: CreateLLMProfileRequest): Promise<LLMProfileSummary> {
  return apiClient.post<CreateLLMProfileRequest, LLMProfileSummary>("/api/settings/llm-profiles", request);
}

/** 更新一套 LLM 配置；未传 credentialRef 时服务端会保留当前引用。 */
export function updateLlmProfile(
  profileId: string,
  request: UpdateLLMProfileRequest,
): Promise<LLMProfileSummary> {
  return apiClient.patch<UpdateLLMProfileRequest, LLMProfileSummary>(
    `/api/settings/llm-profiles/${profileId}`,
    request,
  );
}

/** 删除未被任何 Agent 使用的 LLM 配置。 */
export function deleteLlmProfile(profileId: string): Promise<void> {
  return apiClient.delete(`/api/settings/llm-profiles/${profileId}`);
}

export function listTools(): Promise<ListResponse<ToolSummary>> {
  return apiClient.get("/api/settings/tools");
}
