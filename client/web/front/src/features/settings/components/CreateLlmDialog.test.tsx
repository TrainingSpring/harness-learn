import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { discoverDraftModels, getLlmProfileApiKey, listSavedLlmProfileModels } from "../api";
import { CreateLlmDialog } from "./CreateLlmDialog";

vi.mock("../api", () => ({
  discoverDraftModels: vi.fn(),
  getLlmProfileApiKey: vi.fn(),
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

it("编辑时默认遮蔽回显 API Key，并支持显示和隐藏", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  vi.mocked(listSavedLlmProfileModels).mockResolvedValue({ models: ["gpt-5", "gpt-5-mini"] });
  vi.mocked(getLlmProfileApiKey).mockResolvedValue({ apiKey: "sk-saved-key" });
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
  const apiKeyInput = await screen.findByLabelText("API Key", { exact: true });
  expect(apiKeyInput).toHaveValue("sk-saved-key");
  expect(apiKeyInput).toHaveAttribute("type", "password");
  await user.click(screen.getByRole("button", { name: "显示 API Key" }));
  expect(apiKeyInput).toHaveAttribute("type", "text");
  await user.click(screen.getByRole("button", { name: "隐藏 API Key" }));
  expect(apiKeyInput).toHaveAttribute("type", "password");
  await user.click(screen.getByRole("button", { name: "刷新模型列表" }));
  await user.selectOptions(screen.getByLabelText("模型"), "gpt-5-mini");
  await user.click(screen.getByRole("button", { name: "保存修改" }));

  expect(onSubmit).toHaveBeenCalledWith({
    name: "主模型",
    provider: "openai",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-5-mini",
    apiKey: "sk-saved-key",
    options: { temperature: 0.2 },
  });
  expect(listSavedLlmProfileModels).toHaveBeenCalledWith("llm_OPENAI0001");
  expect(getLlmProfileApiKey).toHaveBeenCalledWith("llm_OPENAI0001");
});
