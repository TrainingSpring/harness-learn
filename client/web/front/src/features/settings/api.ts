import { apiClient } from "../../api/client";
import type {
  ApiKeyResponse,
  CreateLLMProfileRequest,
  DiscoverDraftModelsRequest,
  ListResponse,
  LLMProfileSummary,
  ModelListResponse,
  ToolSummary,
  UpdateLLMProfileRequest,
} from "../../api/types";

export function listLlmProfiles(): Promise<ListResponse<LLMProfileSummary>> {
  return apiClient.get("/api/settings/llm-profiles?limit=100&offset=0");
}

/** 创建 LLM 配置并返回不含 API Key 的摘要。 */
export function createLlmProfile(request: CreateLLMProfileRequest): Promise<LLMProfileSummary> {
  return apiClient.post<CreateLLMProfileRequest, LLMProfileSummary>("/api/settings/llm-profiles", request);
}

/** 更新一套 LLM 配置；未传 apiKey 时服务端会保留当前密钥。 */
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

/** 用当前新增表单中的连接参数查询模型列表。 */
export function discoverDraftModels(request: DiscoverDraftModelsRequest): Promise<ModelListResponse> {
  return apiClient.post<DiscoverDraftModelsRequest, ModelListResponse>("/api/settings/llm-profiles/models", request);
}

/** 用已保存配置的 API Key 查询模型列表。 */
export function listSavedLlmProfileModels(profileId: string): Promise<ModelListResponse> {
  return apiClient.get(`/api/settings/llm-profiles/${profileId}/models`);
}

/** 读取指定配置的 API Key，供编辑弹窗默认遮蔽回显。 */
export function getLlmProfileApiKey(profileId: string): Promise<ApiKeyResponse> {
  return apiClient.get(`/api/settings/llm-profiles/${profileId}/api-key`);
}

export function listTools(): Promise<ListResponse<ToolSummary>> {
  return apiClient.get("/api/settings/tools");
}
