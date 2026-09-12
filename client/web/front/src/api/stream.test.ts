import { describe, expect, it } from "vitest";
import { parseServerEvent, parseSseStream, streamPost } from "./stream";

function readerFromChunks(chunks: Uint8Array[]): ReadableStreamDefaultReader<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(chunk));
      controller.close();
    },
  }).getReader();
}

describe("parseSseStream", () => {
  it("解析一个 chunk 中的多个事件和注释心跳", async () => {
    const source = ': keep-alive\n\ndata: {"type":"run.started","runId":"run_1","sessionId":"session_1","data":{"status":"running"}}\n\ndata: {"type":"message.delta","runId":"run_1","sessionId":"session_1","data":{"text":"你好"}}\n\n';
    const events = await parseSseStream(readerFromChunks([new TextEncoder().encode(source)]));

    expect(events).toHaveLength(2);
    expect(events[1]).toMatchObject({ type: "message.delta", data: { text: "你好" } });
  });

  it("保留跨 UTF-8 chunk 的中文字符并拼接多行 data", async () => {
    const bytes = new TextEncoder().encode('data: {"type":"message.delta",\ndata: "runId":"run_1","sessionId":"session_1","data":{"text":"满江红"}}\n\n');
    const split = bytes.findIndex((value) => value > 127) + 1;
    const events = await parseSseStream(
      readerFromChunks([bytes.slice(0, split), bytes.slice(split, split + 1), bytes.slice(split + 1)]),
    );

    expect(events[0]).toMatchObject({ data: { text: "满江红" } });
  });

  it("流结束时也解析没有空行结尾的最后一个事件", async () => {
    const source = 'data: {"type":"run.completed","runId":"run_1","sessionId":"session_1","data":{}}';
    const events = await parseSseStream(readerFromChunks([new TextEncoder().encode(source)]));

    expect(events[0]?.type).toBe("run.completed");
  });

  it("拒绝缺少权限范围的非法事件", () => {
    expect(() => parseServerEvent({
      type: "permission.required",
      runId: "run_1",
      sessionId: "session_1",
      data: { callId: "call_1", toolName: "write", action: "filesystem.write", resource: null },
    })).toThrow("权限请求事件结构不完整");
  });

  it("SSE 提前结束时报告协议错误", async () => {
    const response = new Response(new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('data: {"type":"run.started","runId":"run_1","sessionId":"session_1","data":{"status":"running"}}\n\n'));
        controller.close();
      },
    }), { status: 200 });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response);
    await expect(streamPost("/api/session/messages", {}, new AbortController().signal, () => {})).rejects.toThrow("运行完成前中断");
    fetchMock.mockRestore();
  });
});
