import { render, screen } from "@testing-library/react";
import { MessageList } from "./MessageList";
import type { ContextItemResponse } from "../../../api/types";

const base = {
  authorAgentId: "agent_ENABLED001",
  visibility: "PUBLIC",
  causedByItemId: null,
  createdAt: "2026-09-12T08:00:00Z",
};

test("将持久化 function call 与 output 合并为一条已完成工具记录", () => {
  HTMLElement.prototype.scrollTo = vi.fn();
  const messages: ContextItemResponse[] = [
    {
      ...base,
      id: "item_CALL000001",
      sequenceNo: 1,
      kind: "FUNCTION_CALL",
      payload: { name: "read", arguments: '{"target_path":"README.md"}' },
      callId: "call_READ000001",
    },
    {
      ...base,
      id: "item_OUTPUT0001",
      sequenceNo: 2,
      kind: "FUNCTION_CALL_OUTPUT",
      payload: { output: '{"ok":true}' },
      callId: "call_READ000001",
    },
  ];

  render(
    <MessageList
      messages={messages}
      optimisticUserText={null}
      streamingText=""
      toolEvents={[]}
    />,
  );

  expect(screen.getByText("read")).toBeInTheDocument();
  expect(screen.getByText("已完成")).toBeInTheDocument();
  expect(screen.queryByText("执行中")).not.toBeInTheDocument();
});
