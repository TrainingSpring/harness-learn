import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { SessionSummary } from "../../../api/types";
import { SessionHistory } from "./SessionHistory";

it("分组展示历史并标记当前会话", () => {
  const sessions: SessionSummary[] = [{
    id: "session_1",
    title: "梳理权限模块",
    conversationMode: "DIRECT",
    status: "ACTIVE",
    agent: { id: "agent_1", name: "架构师" },
    lastMessage: "继续检查权限范围",
    lastSequenceNo: 3,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    permissionMode: "plan",
    workspacePath: null,
    isWorkspaceLocked: false,
  }];

  render(
    <MemoryRouter initialEntries={["/sessions/session_1"]}>
      <SessionHistory sessions={sessions} currentSessionId="session_1" />
    </MemoryRouter>,
  );

  expect(screen.getByText("今天")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /梳理权限模块/ })).toHaveAttribute("aria-current", "page");
  expect(screen.getByText("架构师")).toBeInTheDocument();
});
