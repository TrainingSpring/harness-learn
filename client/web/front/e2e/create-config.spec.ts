import { expect, test } from "@playwright/test";
import { installMockApi } from "./mockApi";

test("可以从角色页面新增角色并刷新列表", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/agents");

  await page.getByRole("button", { name: "新增角色" }).click();
  await page.getByLabel("描述").fill("负责整理文档");
  await page.getByLabel("LLM 配置").selectOption("llm_LOCAL01");
  await page.getByRole("button", { name: "AI 生成角色信息" }).click();
  await expect(page.getByLabel("名称")).toHaveValue("文档助手");
  await expect(page.getByLabel("性格")).toHaveValue("清晰、耐心");
  await page.getByLabel("read").check();
  await page.getByRole("button", { name: "创建角色" }).click();

  await expect(page.getByRole("heading", { name: "文档助手" })).toBeVisible();
  await expect(page.getByRole("dialog")).not.toBeVisible();
});

test("可以从设置页面新增 LLM 配置并刷新列表", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/settings/llms");

  await page.getByRole("button", { name: "新增配置" }).click();
  await page.getByLabel("配置名称").fill("备用模型");
  await page.getByLabel("服务商").selectOption("openai");
  await page.getByLabel("Base URL").fill("https://api.openai.com/v1");
  await page.getByRole("textbox", { name: "API Key" }).fill("sk-backup-key");
  await page.getByRole("button", { name: "刷新模型列表" }).click();
  await page.getByLabel("模型", { exact: true }).selectOption("gpt-5-mini");
  await page.getByRole("button", { name: "创建配置" }).click();

  await expect(page.getByText("备用模型")).toBeVisible();
  await expect(page.getByRole("dialog")).not.toBeVisible();
});

test("可以编辑并删除未被引用的 LLM 配置", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/settings/llms");

  await page.getByRole("button", { name: "编辑 本地 GPT" }).click();
  const apiKey = page.getByLabel("API Key", { exact: true });
  await expect(apiKey).toHaveValue("sk-local-key");
  await expect(apiKey).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "显示 API Key 内容" }).click();
  await expect(apiKey).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "刷新模型列表" }).click();
  await page.getByLabel("模型", { exact: true }).selectOption("gpt-5-mini");
  await page.getByRole("button", { name: "保存修改" }).click();
  await expect(page.getByText("gpt-5-mini")).toBeVisible();

  await page.getByRole("button", { name: "删除 本地 GPT" }).click();
  await page.getByRole("button", { name: "删除配置" }).click();
  await expect(page.getByText("尚未配置 LLM")).toBeVisible();
});
