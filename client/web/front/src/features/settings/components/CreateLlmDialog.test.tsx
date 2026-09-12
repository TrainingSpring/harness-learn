import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CreateLlmDialog } from "./CreateLlmDialog";

it("提交 LLM 表单时保留凭据引用和 JSON 参数", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  render(
    <CreateLlmDialog
      isOpen
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
