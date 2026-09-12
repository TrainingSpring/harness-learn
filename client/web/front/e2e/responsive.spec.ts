import { expect, test } from "@playwright/test";
import { installMockApi } from "./mockApi";

test("移动端使用抽屉导航且内容没有水平溢出", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "仅在移动项目验证抽屉");
  await installMockApi(page);
  await page.goto("/agents");
  await expect(page.getByRole("button", { name: "打开导航" })).toBeVisible();
  await page.getByRole("button", { name: "打开导航" }).click();
  await expect(page.getByRole("link", { name: "新对话" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
});
