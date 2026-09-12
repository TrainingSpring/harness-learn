import { mergeCompletedToolEvent } from "./useChatRun";

test("工具完成事件保留 started 中的工具名并补充结果摘要", () => {
  const current = [
    {
      data: { callId: "call_READ000001", toolName: "read" },
      completed: false,
    },
  ];

  const result = mergeCompletedToolEvent(current, {
    callId: "call_READ000001",
    output: { ok: true },
  });

  expect(result).toEqual([
    {
      data: {
        callId: "call_READ000001",
        toolName: "read",
        summary: '{"ok":true}',
      },
      completed: true,
    },
  ]);
});
