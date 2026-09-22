import { ApiError } from "./client";
import type { ApiErrorBody, ServerEvent } from "./types";

const EVENT_TYPES = new Set<ServerEvent["type"]>([
  "run.started",
  "message.delta",
  "message.completed",
  "tool.started",
  "tool.completed",
  "permission.required",
  "run.completed",
  "run.failed",
]);

const TERMINAL_EVENT_TYPES = new Set<ServerEvent["type"]>([
  "permission.required",
  "run.completed",
  "run.failed",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function invalidEvent(message: string): never {
  throw new ApiError(502, "INVALID_STREAM_EVENT", message);
}

/** 校验网络边界上的 SSE 事件，避免非法数据进入 React 状态。 */
export function parseServerEvent(value: unknown): ServerEvent {
  if (!isRecord(value)) invalidEvent("服务端返回了非法的流事件");
  const { type, runId, sessionId, data } = value;
  if (typeof type !== "string" || !EVENT_TYPES.has(type as ServerEvent["type"])) invalidEvent("服务端返回了未知的流事件");
  if (typeof runId !== "string" || typeof sessionId !== "string" || !isRecord(data)) invalidEvent("流事件缺少运行标识或数据");

  if (type === "run.started" && typeof data.status !== "string") invalidEvent("运行开始事件缺少状态");
  if (type === "message.delta" && typeof data.text !== "string") invalidEvent("消息分片缺少文本");
  if (type === "run.failed" && typeof data.message !== "string") invalidEvent("运行失败事件缺少错误信息");
  if (type === "tool.started" && (typeof data.callId !== "string" || typeof data.toolName !== "string")) invalidEvent("工具开始事件缺少调用信息");
  if (type === "tool.completed" && typeof data.callId !== "string") invalidEvent("工具完成事件缺少调用标识");
  if (type === "permission.required") {
    const validResource = data.resource === null || typeof data.resource === "string";
    const validScopes = Array.isArray(data.allowedScopes)
      && data.allowedScopes.length > 0
      && data.allowedScopes.every((scope) => scope === "once" || scope === "session");
    if (
      typeof data.callId !== "string"
      || typeof data.toolName !== "string"
      || typeof data.action !== "string"
      || !validResource
      || !validScopes
    ) invalidEvent("权限请求事件结构不完整");
  }

  return value as ServerEvent;
}

/**
 * 解析 SSE 字节流。TextDecoder 使用流式模式，确保一个中文字符跨网络 chunk 时不会乱码。
 * 返回事件数组便于单元测试；生产调用通常同时传入 onEvent 逐条消费。
 */
export async function parseSseStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onEvent?: (event: ServerEvent) => void,
): Promise<ServerEvent[]> {
  const decoder = new TextDecoder();
  const events: ServerEvent[] = [];
  let buffer = "";

  const consumeBlock = (block: string) => {
    const dataLines = block
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).replace(/^ /, ""));
    if (dataLines.length === 0) return;

    const event = parseServerEvent(JSON.parse(dataLines.join("\n")));
    events.push(event);
    onEvent?.(event);
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? "";
    blocks.forEach(consumeBlock);
  }

  buffer += decoder.decode();
  if (buffer.trim()) consumeBlock(buffer);
  return events;
}

/** 使用 POST 发起 SSE 请求，并将每个服务端事件实时交给调用方。 */
export async function streamPost<TBody>(
  path: string,
  body: TBody,
  signal: AbortSignal,
  onEvent: (event: ServerEvent) => void,
  onOpen?: () => void,
): Promise<void> {
  const response = await fetch(path, {
    method: "POST",
    headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    let errorBody: ApiErrorBody | null = null;
    try {
      errorBody = (await response.json()) as ApiErrorBody;
    } catch {
      // 与普通 API 一致，不渲染上游可能返回的 HTML 错误页。
    }
    throw new ApiError(
      response.status,
      errorBody?.error?.code ?? "STREAM_REQUEST_FAILED",
      errorBody?.error?.message ?? "无法开始对话",
      errorBody?.error?.details ?? null,
    );
  }

  if (!response.body) throw new ApiError(502, "EMPTY_STREAM", "服务端没有返回事件流");
  onOpen?.();
  const events = await parseSseStream(response.body.getReader(), onEvent);
  const lastType = events.at(-1)?.type;
  if (!lastType || !TERMINAL_EVENT_TYPES.has(lastType)) {
    throw new ApiError(502, "STREAM_ENDED_EARLY", "事件流在运行完成前中断");
  }
}
