import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { discoverDraftModels, listSavedLlmProfileModels } from "../api";
import { CreateLlmDialog } from "./CreateLlmDialog";

vi.mock("../api", () => ({
  discoverDraftModels: vi.fn(),
  listSavedLlmProfileModels: vi.fn(),
}));

it("提交 LLM 表单时保存 API Key 和 JSON 参数", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  vi.mocked(discoverDraftModels).mockResolvedValue({ models: ["gpt-5"] });
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
  await user.type(screen.getByLabelText("Base URL"), "https://api.openai.com/v1");
  await user.type(screen.getByLabelText("API Key"), "sk-test-key");
  await user.click(screen.getByRole("button", { name: "刷新模型列表" }));
  await user.selectOptions(screen.getByLabelText("模型"), "gpt-5");
  fireEvent.change(screen.getByLabelText("额外参数 JSON"), { target: { value: '{"temperature":0.2}' } });
  await user.click(screen.getByRole("button", { name: "创建配置" }));

  expect(onSubmit).toHaveBeenCalledWith({
    name: "OpenAI 主配置",
    provider: "openai",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-5",
    apiKey: "sk-test-key",
    options: { temperature: 0.2 },
  });
  expect(discoverDraftModels).toHaveBeenCalledWith({
    provider: "openai",
    baseUrl: "https://api.openai.com/v1",
    apiKey: "sk-test-key",
  });
});

it("编辑时预填公开字段，留空 API Key 表示不提交替换值", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  vi.mocked(listSavedLlmProfileModels).mockResolvedValue({ models: ["gpt-5", "gpt-5-mini"] });
  render(
    <CreateLlmDialog
      mode="edit"
      profile={{
        id: "llm_OPENAI0001",
        name: "主模型",
        provider: "openai",
        baseUrl: "https://api.openai.com/v1",
        model: "gpt-5",
        hasApiKey: true,
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
  expect(screen.getByLabelText("API Key")).toHaveValue("");
  await user.click(screen.getByRole("button", { name: "刷新模型列表" }));
  await user.selectOptions(screen.getByLabelText("模型"), "gpt-5-mini");
  await user.click(screen.getByRole("button", { name: "保存修改" }));

  expect(onSubmit).toHaveBeenCalledWith({
    name: "主模型",
    provider: "openai",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-5-mini",
    options: { temperature: 0.2 },
  });
  expect(listSavedLlmProfileModels).toHaveBeenCalledWith("llm_OPENAI0001");
});
