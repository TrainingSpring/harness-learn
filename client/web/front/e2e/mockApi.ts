import type { Page, Route } from "@playwright/test";

const agent = {
  id: "agent_ENGINEER01",
  name: "工程师",
  description: "专注代码实现、系统设计与严谨审查",
  personality: "直接、严谨、重视证据",
  expertise: ["Python", "TypeScript", "架构"],
  tools: ["read", "write", "edit", "bash"],
  isEnabled: true,
};

const llmProfile = {
  id: "llm_LOCAL01",
  name: "本地 GPT",
  provider: "openai",
  baseUrl: "https://api.openai.com/v1",
  model: "gpt-5",
  hasApiKey: true,
  options: {},
};

const session = {
  id: "session_DIRECT01",
  title: "检查权限模块",
  conversationMode: "DIRECT",
  status: "ACTIVE",
  agent: { id: agent.id, name: agent.name },
  lastMessage: "请检查权限模块",
  lastSequenceNo: 2,
  createdAt: "2026-09-12T08:00:00Z",
  updatedAt: "2026-09-12T08:00:00Z",
};

const list = <T,>(items: T[]) => ({ items, pagination: { limit: 100, offset: 0, hasMore: false } });
const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
const event = (type: string, data: unknown) => `data: ${JSON.stringify({ type, runId: "run_DIRECT01", sessionId: session.id, data })}\n\n`;

/** 为 E2E 安装与公开 camelCase 契约一致的本地假 API。 */
export async function installMockApi(page: Page, options: { hasSession?: boolean; permission?: boolean } = {}) {
  let hasSession = options.hasSession ?? false;
  let agents = [agent];
  let llmProfiles = [llmProfile];
  const messages: Array<Record<string, unknown>> = [];
  const contextItem = (
    id: string,
    sequenceNo: number,
    kind: string,
    payload: Record<string, unknown>,
    callId: string | null = null,
  ) => ({
    id,
    sequenceNo,
    kind,
    authorAgentId: kind === "AGENT_MESSAGE" ? agent.id : null,
    visibility: "PUBLIC",
    payload,
    callId,
    causedByItemId: null,
    createdAt: "2026-09-12T08:00:00Z",
  });
  // 限定在站点根 API，避免把 Vite 的 /src/api/*.ts 源模块误当成后端请求。
  await page.route("http://127.0.0.1:4173/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();

    if (path === "/api/agents" && method === "GET") return json(route, list(agents));
    if (path === "/api/agents" && method === "POST") {
      const requestBody = request.postDataJSON() as {
        name: string;
        description: string;
        personality: string;
        expertise: string[];
        llmProfileId: string;
        tools: string[];
        permissionMode: string;
        isEnabled: boolean;
      };
      const createdAgent = {
        id: "agent_CREATED01",
        name: requestBody.name,
        description: requestBody.description,
        personality: requestBody.personality,
        expertise: requestBody.expertise,
        tools: requestBody.tools,
        isEnabled: requestBody.isEnabled,
        llmProfileId: requestBody.llmProfileId,
        permissionMode: requestBody.permissionMode,
      };
      agents = [...agents, createdAgent];
      return json(route, createdAgent, 201);
    }
    if (path === "/api/agents/profile-suggestion" && method === "POST") {
      const requestBody = request.postDataJSON() as { description: string; llmProfileId: string };
      return json(route, {
        name: "文档助手",
        description: requestBody.description,
        personality: "清晰、耐心",
        expertise: ["Documentation", "Technical Writing"],
      });
    }
    if (path === `/api/agents/${agent.id}`) return json(route, { ...agent, llmProfileId: "llm_LOCAL01", permissionMode: "BUILD" });
    if (path === "/api/sessions" && method === "GET") return json(route, list(hasSession ? [session] : []));
    if (path === "/api/sessions" && method === "POST") { hasSession = true; return json(route, session, 201); }
    if (path === `/api/sessions/${session.id}`) return json(route, { ...session, messages });
    if (path === `/api/sessions/${session.id}/messages` && method === "GET") return json(route, { items: messages });
    if (path === `/api/sessions/${session.id}/messages` && method === "POST") {
      messages.push(contextItem("item_USER000001", 1, "USER_MESSAGE", { text: options.permission ? "写入说明" : "请检查权限模块" }));
      if (options.permission) {
        messages.push(contextItem("item_CALL000001", 2, "FUNCTION_CALL", { name: "write", arguments: '{"target_path":"README.md"}' }, "call_WRITE01"));
      } else {
        messages.push(contextItem("item_AGENT00001", 2, "AGENT_MESSAGE", { text: "权限模块结构清晰。" }));
      }
      const body = options.permission
        ? event("run.started", { status: "running" })
          + event("tool.started", { itemId: "item_CALL000001", callId: "call_WRITE01", toolName: "write", arguments: '{"target_path":"README.md"}' })
          + event("permission.required", { callId: "call_WRITE01", toolName: "write", action: "filesystem.write", resource: "/workspace/README.md", allowedScopes: ["once", "session", "agent"] })
        : event("run.started", { status: "running" })
          + event("message.delta", { text: "权限模块结构清晰。" })
          + event("message.completed", { itemId: "item_AGENT00001", text: "权限模块结构清晰。" })
          + event("run.completed", { status: "completed" });
      return route.fulfill({ status: 200, contentType: "text/event-stream", body });
    }
    if (path === "/api/runs/run_DIRECT01/permission" && method === "POST") {
      messages.push(
        contextItem("item_OUTPUT0001", 3, "FUNCTION_CALL_OUTPUT", { output: '{"status":"ok"}' }, "call_WRITE01"),
        contextItem("item_AGENT00002", 4, "AGENT_MESSAGE", { text: "已获授权，文件写入完成。" }),
      );
      const body = event("tool.completed", { itemId: "item_OUTPUT0001", callId: "call_WRITE01", output: '{"status":"ok"}' })
        + event("message.delta", { text: "已获授权，文件写入完成。" })
        + event("message.completed", { itemId: "item_AGENT00002", text: "已获授权，文件写入完成。" })
        + event("run.completed", { status: "completed" });
      return route.fulfill({ status: 200, contentType: "text/event-stream", body });
    }
    if (path === "/api/runs/run_DIRECT01/cancel" && method === "POST") return route.fulfill({ status: 204 });
    if (path === "/api/settings/llm-profiles" && method === "GET") return json(route, list(llmProfiles));
    if (path === "/api/settings/llm-profiles" && method === "POST") {
      const requestBody = request.postDataJSON() as {
        name: string;
        provider: string;
        baseUrl: string | null;
        model: string;
        options: Record<string, unknown>;
      };
      const createdProfile = {
        id: "llm_CREATED01",
        name: requestBody.name,
        provider: requestBody.provider,
        baseUrl: requestBody.baseUrl,
        model: requestBody.model,
        hasApiKey: true,
        options: requestBody.options,
      };
      llmProfiles = [...llmProfiles, createdProfile];
      return json(route, createdProfile, 201);
    }
    if (path === "/api/settings/llm-profiles/models" && method === "POST") return json(route, { models: ["gpt-5", "gpt-5-mini"] });
    if (path === `/api/settings/llm-profiles/${llmProfile.id}/models` && method === "GET") return json(route, { models: ["gpt-5", "gpt-5-mini"] });
    if (path === `/api/settings/llm-profiles/${llmProfile.id}/api-key` && method === "GET") return json(route, { apiKey: "sk-local-key" });
    const llmProfileMatch = path.match(/^\/api\/settings\/llm-profiles\/(llm_[A-Z0-9]+)$/);
    if (llmProfileMatch && method === "PATCH") {
      const { apiKey: _apiKey, ...requestBody } = request.postDataJSON() as Omit<typeof llmProfile, "id" | "hasApiKey"> & { apiKey?: string };
      const profileId = llmProfileMatch[1];
      llmProfiles = llmProfiles.map((profile) => profile.id === profileId ? { ...profile, ...requestBody } : profile);
      return json(route, llmProfiles.find((profile) => profile.id === profileId));
    }
    if (llmProfileMatch && method === "DELETE") {
      const profileId = llmProfileMatch[1];
      llmProfiles = llmProfiles.filter((profile) => profile.id !== profileId);
      return route.fulfill({ status: 204 });
    }
    if (path === "/api/settings/tools") return json(route, list([{ name: "read", description: "读取工作区文件", inputSchema: { type: "object", properties: { targetPath: { type: "string" } } }, permissionAction: "filesystem.read" }]));
    return json(route, { error: { code: "NOT_FOUND", message: path, details: null } }, 404);
  });
}
