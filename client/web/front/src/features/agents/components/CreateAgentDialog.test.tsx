import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CreateAgentDialog } from "./CreateAgentDialog";

it("提交角色表单时组装领域标签、LLM 和工具配置", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  render(
    <CreateAgentDialog
      isOpen
      isSubmitting={false}
      error={null}
      llmProfiles={[{
        id: "llm_OPENAI0001",
        name: "主模型",
        provider: "openai",
        baseUrl: null,
        model: "gpt-5",
        hasCredential: true,
        options: {},
      }]}
      tools={[
        { name: "read", description: "读取文件", inputSchema: {}, permissionAction: "filesystem.read" },
        { name: "bash", description: "执行命令", inputSchema: {}, permissionAction: "process.exec" },
      ]}
      onClose={vi.fn()}
      onSubmit={onSubmit}
    />,
  );

  await user.type(screen.getByLabelText("名称"), "工程师");
  await user.type(screen.getByLabelText("描述"), "负责代码实现");
  await user.type(screen.getByLabelText("性格"), "直接、严谨");
  await user.type(screen.getByLabelText("擅长领域"), "Python, API");
  await user.click(screen.getByLabelText("read"));
  await user.selectOptions(screen.getByLabelText("LLM 配置"), "llm_OPENAI0001");
  await user.selectOptions(screen.getByLabelText("权限模式"), "PLAN");
  await user.click(screen.getByRole("button", { name: "创建角色" }));

  expect(onSubmit).toHaveBeenCalledWith({
    name: "工程师",
    description: "负责代码实现",
    personality: "直接、严谨",
    expertise: ["Python", "API"],
    llmProfileId: "llm_OPENAI0001",
    tools: ["read"],
    permissionMode: "PLAN",
    isEnabled: true,
  });
});

it("创建角色弹窗不可见时不渲染表单", () => {
  render(
    <CreateAgentDialog
      isOpen={false}
      isSubmitting={false}
      error={null}
      llmProfiles={[]}
      tools={[]}
      onClose={vi.fn()}
      onSubmit={vi.fn()}
    />,
  );

  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
