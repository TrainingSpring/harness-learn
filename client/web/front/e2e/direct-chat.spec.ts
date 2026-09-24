import { expect, test } from "@playwright/test";
import { installMockApi } from "./mockApi";

test("首次发送创建会话并显示流式回复", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/new");
  await page.getByRole("button", { name: /工程师/ }).click();
  await page.getByRole("button", { name: "确认创建" }).click();
  await expect(page).toHaveURL(/\/sessions\/session_DIRECT01/);
  await page.getByRole("textbox", { name: "消息" }).fill("请检查权限模块");
  await page.getByRole("button", { name: "发送消息" }).click();
  await expect(page.getByText("权限模块结构清晰。")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "工作目录已锁定" })).toBeDisabled();
});

test("新建对话必须选择角色，工作目录可以不选", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/new");
  await expect(page.getByRole("button", { name: "确认创建" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "选择工作目录" })).toBeVisible();
});

test("新建对话可以选择工作目录，确认后再进入 Session", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/new");
  await page.getByRole("button", { name: /工程师/ }).click();
  await page.getByRole("button", { name: "选择工作目录" }).click();
  const picker = page.getByRole("dialog", { name: "选择工作目录" });
  await expect(picker).toBeVisible();
  await expect(picker).not.toContainText("会话环境");
  await expect(page.getByRole("button", { name: "返回上级目录" })).toContainText("..");
  await page.getByRole("button", { name: "返回上级目录" }).click();
  await expect(page.getByLabel("工作目录路径")).toHaveValue("/");
  await page.getByRole("button", { name: "workspace", exact: true }).click();
  await page.getByRole("button", { name: "client", exact: true }).click();
  await expect(page.getByLabel("工作目录路径")).toHaveValue("/workspace/client");
  await page.getByRole("button", { name: "选择此目录" }).click();
  await page.getByRole("button", { name: "确认创建" }).click();
  await expect(page).toHaveURL(/\/sessions\/session_DIRECT01/);
  await page.getByLabel("权限模式").selectOption("build");
  await page.getByRole("textbox", { name: "消息" }).fill("选择项目后发送");
  await page.getByRole("button", { name: "发送消息" }).click();
});

test("权限请求必须显式确认并从原 run 恢复", async ({ page }) => {
  await installMockApi(page, { permission: true });
  await page.goto("/new?agentId=agent_ENGINEER01");
  await page.getByRole("button", { name: "确认创建" }).click();
  await expect(page).toHaveURL(/\/sessions\/session_DIRECT01/);
  await page.getByRole("textbox", { name: "消息" }).fill("写入说明");
  await page.getByRole("button", { name: "发送消息" }).click();
  await expect(page.getByRole("dialog")).toContainText("/workspace/README.md");
  await page.getByRole("button", { name: "仅本次允许" }).click();
  await expect(page.getByText("已获授权，文件写入完成。")).toHaveCount(1);
  await expect(page.getByText("write", { exact: true })).toHaveCount(1);
  await expect(page.getByText("已完成", { exact: true })).toHaveCount(1);
});
