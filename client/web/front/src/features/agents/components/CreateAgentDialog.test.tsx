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
        hasApiKey: true,
        options: {},
      }]}
      tools={[
        { name: "read", description: "读取文件", inputSchema: {}, permissionAction: "filesystem.read" },
        { name: "bash", description: "执行命令", inputSchema: {}, permissionAction: "process.exec" },
      ]}
      onClose={vi.fn()}
      onSubmit={onSubmit}
      isSuggesting={false}
      onSuggest={async () => ({
        name: "文档助手",
        description: "帮助团队整理技术文档",
        personality: "清晰、耐心",
        expertise: ["Documentation", "Technical Writing"],
      })}
    />,
  );

  await user.type(screen.getByLabelText("名称"), "工程师");
  await user.type(screen.getByLabelText("描述"), "负责代码实现");
  await user.type(screen.getByLabelText("性格"), "直接、严谨");
  await user.type(screen.getByLabelText("擅长领域"), "Python, API");
  await user.click(screen.getByLabelText("read"));
  await user.selectOptions(screen.getByLabelText("LLM 配置"), "llm_OPENAI0001");
  await user.click(screen.getByRole("button", { name: "AI 生成角色信息" }));
  await user.selectOptions(screen.getByLabelText("权限模式"), "PLAN");
  await user.click(screen.getByRole("button", { name: "创建角色" }));

  expect(onSubmit).toHaveBeenCalledWith({
    name: "文档助手",
    description: "帮助团队整理技术文档",
    personality: "清晰、耐心",
    expertise: ["Documentation", "Technical Writing"],
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
      isSuggesting={false}
      onSuggest={vi.fn()}
    />,
  );

  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("只有填写描述并选择 LLM 后才启用 AI 生成按钮", async () => {
  const user = userEvent.setup();
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
        hasApiKey: true,
        options: {},
      }]}
      tools={[]}
      onClose={vi.fn()}
      onSubmit={vi.fn()}
      isSuggesting={false}
      onSuggest={vi.fn()}
    />,
  );

  const suggestButton = screen.getByRole("button", { name: "AI 生成角色信息" });
  expect(suggestButton).toBeDisabled();
  await user.type(screen.getByLabelText("描述"), "帮助团队整理技术文档");
  expect(suggestButton).toBeDisabled();
  await user.selectOptions(screen.getByLabelText("LLM 配置"), "llm_OPENAI0001");
  expect(suggestButton).toBeEnabled();
});
