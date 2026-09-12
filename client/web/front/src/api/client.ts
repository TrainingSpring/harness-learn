import type { ApiErrorBody } from "./types";

/** HTTP API 的稳定错误类型，页面无需了解 fetch Response。 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown | null;

  constructor(status: number, code: string, message: string, details: unknown | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }

  let body: ApiErrorBody | null = null;
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    // 非 JSON 的网关错误不能向 UI 泄露 HTML，只提供稳定的通用信息。
  }
  throw new ApiError(
    response.status,
    body?.error?.code ?? "HTTP_ERROR",
    body?.error?.message ?? "请求失败，请稍后重试",
    body?.error?.details ?? null,
  );
}

export const apiClient = {
  async get<T>(path: string, signal?: AbortSignal): Promise<T> {
    return parseResponse<T>(await fetch(path, { headers: { Accept: "application/json" }, signal }));
  },

  async post<TRequest, TResponse>(path: string, body?: TRequest, signal?: AbortSignal): Promise<TResponse> {
    return parseResponse<TResponse>(
      await fetch(path, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal,
      }),
    );
  },
};
