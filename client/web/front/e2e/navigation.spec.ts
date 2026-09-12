import { expect, test } from "@playwright/test";
import { installMockApi } from "./mockApi";

test("可在角色和设置页面之间导航", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "桌面主导航由该用例覆盖，移动抽屉单独验证");
  await installMockApi(page);
  await page.goto("/new");
  await page.getByRole("link", { name: "角色" }).click();
  await expect(page.getByRole("heading", { name: "选择适合当前任务的角色" })).toBeVisible();
  await page.getByRole("link", { name: "设置" }).click();
  await expect(page.getByRole("heading", { name: "设置" })).toBeVisible();
  await page.getByRole("link", { name: "LLM" }).click();
  await expect(page.getByRole("table", { name: "LLM 配置" })).toBeVisible();
});
