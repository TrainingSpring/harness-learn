import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CreateLlmDialog } from "./CreateLlmDialog";

it("提交 LLM 表单时保留凭据引用和 JSON 参数", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  render(
    <CreateLlmDialog
      isOpen
      mode="create"
      isSubmitting={false}
      error={null}
      onClose={vi.fn()}
      onSubmit={onSubmit}
    />,
  );

  await user.type(screen.getByLabelText("配置名称"), "OpenAI 主配置");
  await user.type(screen.getByLabelText("服务商"), "openai");
  await user.type(screen.getByLabelText("Base URL"), "https://api.openai.com/v1");
  await user.type(screen.getByLabelText("模型"), "gpt-5");
  await user.type(screen.getByLabelText("凭据引用"), "env:OPENAI_API_KEY");
  fireEvent.change(screen.getByLabelText("额外参数 JSON"), { target: { value: '{"temperature":0.2}' } });
  await user.click(screen.getByRole("button", { name: "创建配置" }));

  expect(onSubmit).toHaveBeenCalledWith({
    name: "OpenAI 主配置",
    provider: "openai",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-5",
    credentialRef: "env:OPENAI_API_KEY",
    options: { temperature: 0.2 },
  });
});

it("编辑时预填公开字段，留空凭据引用表示不提交替换值", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  render(
    <CreateLlmDialog
      mode="edit"
      profile={{
        id: "llm_OPENAI0001",
        name: "主模型",
        provider: "openai",
        baseUrl: "https://api.openai.com/v1",
        model: "gpt-5",
        hasCredential: true,
        options: { temperature: 0.2 },
      }}
      isOpen
      isSubmitting={false}
      error={null}
      onClose={vi.fn()}
      onSubmit={onSubmit}
    />,
  );

  expect(screen.getByLabelText("配置名称")).toHaveValue("主模型");
  expect(screen.getByLabelText("凭据引用")).toHaveValue("");
  await user.clear(screen.getByLabelText("模型"));
  await user.type(screen.getByLabelText("模型"), "gpt-5-mini");
  await user.click(screen.getByRole("button", { name: "保存修改" }));

  expect(onSubmit).toHaveBeenCalledWith({
    name: "主模型",
    provider: "openai",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-5-mini",
    options: { temperature: 0.2 },
  });
});
