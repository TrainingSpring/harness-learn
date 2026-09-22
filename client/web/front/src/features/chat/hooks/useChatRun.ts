import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { ApiError, apiClient } from "../../../api/client";
import { streamPost } from "../../../api/stream";
import type { PermissionDecision, PermissionRequest, PermissionResponse, PermissionScope, ServerEvent, ToolEventData } from "../../../api/types";

type RunStatus = "idle" | "running" | "waiting";
export type ToolEventState = { data: ToolEventData; completed: boolean };

function summarizeOutput(value: unknown): string | undefined {
  if (typeof value === "string") return value;
  if (value === undefined) return undefined;
  try {
    return JSON.stringify(value);
  } catch {
    return "结果无法序列化";
  }
}

/** 将不含工具名的 completed 事件与先前 started 事件合并。 */
export function mergeCompletedToolEvent(
  current: ToolEventState[],
  completed: { callId: string; itemId?: string; output?: unknown },
): ToolEventState[] {
  const found = current.some((item) => item.data.callId === completed.callId);
  const summary = summarizeOutput(completed.output);
  if (!found) {
    return [...current, { data: { callId: completed.callId, itemId: completed.itemId, toolName: "tool", summary }, completed: true }];
  }
  return current.map((item) => item.data.callId === completed.callId
    ? { data: { ...item.data, itemId: completed.itemId, summary }, completed: true }
    : item);
}

/** 管理单个 Session 的内存流状态；持久化消息仍由 Query 负责。 */
export function useChatRun(sessionId: string) {
  const queryClient = useQueryClient();
  const abortRef = useRef<AbortController | null>(null);
  const runIdRef = useRef<string | null>(null);
  const [status, setStatus] = useState<RunStatus>("idle");
  const [streamingText, setStreamingText] = useState("");
  const [toolEvents, setToolEvents] = useState<ToolEventState[]>([]);
  const [permission, setPermission] = useState<PermissionRequest | null>(null);
  const [permissionSubmitting, setPermissionSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const applyEvent = useCallback((event: ServerEvent) => {
    runIdRef.current = event.runId;
    if (event.type === "message.delta") setStreamingText((current) => current + event.data.text);
    if (event.type === "tool.started") setToolEvents((current) => [...current, { data: event.data, completed: false }]);
    if (event.type === "tool.completed") setToolEvents((current) => mergeCompletedToolEvent(current, event.data));
    if (event.type === "message.completed") setStreamingText("");
    if (event.type === "permission.required") { setPermission(event.data); setStatus("waiting"); }
    if (event.type === "run.failed") {
      runIdRef.current = null;
      setStreamingText("");
      setPermission(null);
      setError(event.data.message);
      setStatus("idle");
    }
    if (event.type === "run.completed") {
      runIdRef.current = null;
      setPermission(null);
      setStatus("idle");
    }
  }, []);

  const consume = useCallback(async <TBody,>(path: string, body: TBody, onOpen?: () => void) => {
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamPost(path, body, controller.signal, applyEvent, onOpen);
    } finally {
      // 只有创建本次请求的控制器才能清空引用，避免权限恢复请求与上一段流
      // 几乎同时切换时，旧请求的 finally 覆盖新请求的停止控制器。
      if (abortRef.current === controller) abortRef.current = null;
      await queryClient.invalidateQueries({ queryKey: ["messages", sessionId] });
      await queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
      // 工具完成事件已经进入持久化时间线；刷新完成后移除临时事件，避免同一
      // function call 同时以 SSE 临时状态和 ContextItem 再显示一次。
      setToolEvents([]);
    }
  }, [applyEvent, queryClient, sessionId]);

  const send = useCallback(async (text: string) => {
    setError(null);
    setStreamingText("");
    setToolEvents([]);
    setPermission(null);
    setStatus("running");
    try {
      await consume(`/api/sessions/${encodeURIComponent(sessionId)}/messages`, { text });
    } catch (cause) {
      if (!(cause instanceof DOMException && cause.name === "AbortError")) {
        setError(cause instanceof Error ? cause.message : "流式响应失败");
        setStatus("idle");
      }
    }
  }, [consume, sessionId]);

  const resolvePermission = useCallback(async (decision: PermissionDecision, scope: PermissionScope) => {
    const runId = runIdRef.current;
    if (!runId || !permission) return;
    const response: PermissionResponse = { callId: permission.callId, decision, scope };
    let opened = false;
    setError(null);
    setPermissionSubmitting(true);
    setStatus("running");
    try {
      await consume(`/api/runs/${encodeURIComponent(runId)}/permission`, response, () => {
        opened = true;
        setPermission(null);
      });
    } catch (cause) {
      if (!(cause instanceof DOMException && cause.name === "AbortError")) {
        setError(cause instanceof Error ? cause.message : "权限决定提交失败");
        setStatus(opened ? "idle" : "waiting");
      }
    } finally {
      setPermissionSubmitting(false);
    }
  }, [consume, permission]);

  const stop = useCallback(async () => {
    const controller = abortRef.current;
    const runId = runIdRef.current;
    setStatus("idle");
    controller?.abort();
    if (!runId) {
      setPermission(null);
      return;
    }
    try {
      await apiClient.post(`/api/runs/${encodeURIComponent(runId)}/cancel`, undefined);
      runIdRef.current = null;
      setPermission(null);
    } catch (cause) {
      // 流断开会同步清理 Run，因此停止请求与清理竞争得到 404 也视为成功。
      if (!(cause instanceof ApiError && cause.status === 404)) {
        setError(cause instanceof Error ? cause.message : "停止运行失败");
        if (permission) setStatus("waiting");
      } else {
        runIdRef.current = null;
        setPermission(null);
      }
    }
  }, [permission]);

  return { status, streamingText, toolEvents, permission, permissionSubmitting, error, send, resolvePermission, stop };
}
