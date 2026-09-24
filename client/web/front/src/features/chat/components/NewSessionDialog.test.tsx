import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { AgentSummary } from "../../../api/types";
import { NewSessionDialog } from "./NewSessionDialog";

const agents: AgentSummary[] = [{
  id: "agent_ENGINEER01",
  name: "工程师",
  description: "负责实现任务",
  personality: "直接",
  expertise: ["代码"],
  tools: [],
  isEnabled: true,
}];

function renderDialog(overrides: Partial<React.ComponentProps<typeof NewSessionDialog>> = {}) {
  const props = {
    agents,
    selectedAgentId: null,
    workspacePath: null,
    isSubmitting: false,
    error: null,
    onAgentSelect: vi.fn(),
    onWorkspaceChange: vi.fn(),
    onConfirm: vi.fn(),
    onClose: vi.fn(),
    ...overrides,
  };
  render(<NewSessionDialog {...props} />);
  return props;
}

it("角色未选择时禁止确认，取消只关闭弹窗", async () => {
  const user = userEvent.setup();
  const props = renderDialog();

  expect(screen.getByRole("button", { name: "确认创建" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "取消" }));

  expect(props.onConfirm).not.toHaveBeenCalled();
  expect(props.onClose).toHaveBeenCalledOnce();
});

it("选择角色后允许不选工作目录并显式确认创建", async () => {
  const user = userEvent.setup();
  const props = renderDialog({ selectedAgentId: "agent_ENGINEER01" });

  expect(screen.getByText("不选择工作目录")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "确认创建" }));

  expect(props.onConfirm).toHaveBeenCalledOnce();
  expect(props.onWorkspaceChange).not.toHaveBeenCalled();
});
