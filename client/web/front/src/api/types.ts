/** 分页信息，与 Web API 的 camelCase 响应保持一致。 */
export interface Pagination {
  limit: number;
  offset: number;
  hasMore: boolean;
}

/** 所有列表接口共用的响应外壳。 */
export interface ListResponse<T> {
  items: T[];
  pagination: Pagination;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: unknown | null;
  };
}

export interface AgentReference {
  id: string;
  name: string;
}

export interface AgentSummary extends AgentReference {
  description: string;
  personality: string;
  expertise: string[];
  tools: string[];
  isEnabled: boolean;
}

/** 创建角色时提交给 Web API 的配置。ID 由服务端生成。 */
export interface CreateAgentRequest {
  name: string;
  description: string;
  personality: string;
  expertise: string[];
  llmProfileId: string;
  tools: string[];
  permissionMode: string;
  isEnabled: boolean;
}

/** 请求 AI 根据原始描述生成角色表单草案。 */
export interface AgentProfileSuggestionRequest {
  description: string;
  llmProfileId: string;
}

/** 服务端验证后允许回填到角色表单的 AI 生成字段。 */
export interface AgentProfileSuggestion {
  name: string;
  description: string;
  personality: string;
  expertise: string[];
}

export interface AgentDetail extends AgentSummary {
  llmProfileId: string;
  permissionMode: "PLAN" | "BUILD" | "YOLO" | string;
}

export type ConversationMode = "DIRECT";
export type SessionStatus = "ACTIVE" | "PAUSED" | "COMPLETED" | "CLOSED" | "FAILED" | string;

export interface SessionSummary {
  id: string;
  title: string | null;
  conversationMode: ConversationMode;
  status: SessionStatus;
  agent: AgentReference;
  lastMessage: string | null;
  lastSequenceNo: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface CreateDirectSessionRequest {
  mode: "DIRECT";
  agentId: string;
  title?: string | null;
}

export type ContextItemKind =
  | "USER_MESSAGE"
  | "AGENT_MESSAGE"
  | "FUNCTION_CALL"
  | "FUNCTION_CALL_OUTPUT"
  | "AGENT_DELEGATION"
  | "SYSTEM_EVENT"
  | string;

export interface ContextItemResponse {
  id: string;
  sequenceNo: number;
  kind: ContextItemKind;
  authorAgentId: string | null;
  visibility: string;
  payload: Record<string, unknown>;
  callId: string | null;
  causedByItemId: string | null;
  createdAt: string | null;
}

export interface SessionDetail extends SessionSummary {
  messages: ContextItemResponse[];
}

export interface LLMProfileSummary {
  id: string;
  name: string;
  provider: string;
  baseUrl: string | null;
  model: string;
  hasCredential: boolean;
  options: Record<string, unknown>;
}

/** 创建 LLM 配置时提交的连接参数；credentialRef 是引用而不是密钥。 */
export interface CreateLLMProfileRequest {
  name: string;
  provider: string;
  baseUrl: string | null;
  model: string;
  credentialRef: string;
  options: Record<string, unknown>;
}

export interface ToolSummary {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  permissionAction: string;
}

export type PermissionScope = "once" | "session" | "agent";
export type PermissionDecision = "allow" | "deny";

export interface PermissionRequest {
  callId: string;
  toolName: string;
  action: string;
  resource: string | null;
  allowedScopes: PermissionScope[];
}

export interface PermissionResponse {
  callId: string;
  decision: PermissionDecision;
  scope: PermissionScope;
}

export interface ToolEventData {
  callId: string;
  toolName: string;
  itemId?: string;
  arguments?: unknown;
  output?: unknown;
  status?: string;
  durationMs?: number;
  summary?: string;
}

export type ServerEvent =
  | { type: "run.started"; runId: string; sessionId: string; data: { status: string } }
  | { type: "message.delta"; runId: string; sessionId: string; data: { text: string } }
  | { type: "message.completed"; runId: string; sessionId: string; data: { itemId?: string; text?: string } }
  | { type: "tool.started"; runId: string; sessionId: string; data: { callId: string; toolName: string; itemId?: string; arguments?: unknown } }
  | { type: "tool.completed"; runId: string; sessionId: string; data: { callId: string; itemId?: string; output?: unknown } }
  | { type: "permission.required"; runId: string; sessionId: string; data: PermissionRequest }
  | { type: "run.completed"; runId: string; sessionId: string; data: Record<string, unknown> }
  | { type: "run.failed"; runId: string; sessionId: string; data: { code?: string; message: string } };
