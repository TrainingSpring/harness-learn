import { expect, test } from "@playwright/test";
import { installMockApi } from "./mockApi";

test("三种目标视口无控制台错误、水平溢出或元素重叠", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "单个 Chromium 页面依次验证三个精确视口");
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.addInitScript(() => localStorage.setItem("harness-theme", "dark"));
  await installMockApi(page, { hasSession: true });

  const cases = [
    { width: 1440, height: 900, path: "/agents", name: "visual-1440x900.png", readyText: "选择适合当前任务的角色" },
    { width: 1024, height: 768, path: "/new?agentId=agent_ENGINEER01", name: "visual-1024x768.png", readyText: "与 工程师 对话" },
    { width: 390, height: 844, path: "/settings/appearance", name: "visual-390x844.png", readyText: "选择工作区的显示主题。" },
  ];

  for (const current of cases) {
    await page.setViewportSize({ width: current.width, height: current.height });
    await page.goto(current.path);
    await expect(page.getByText(current.readyText, { exact: true })).toBeVisible();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(current.name), fullPage: true });
  }

  expect(pageErrors).toEqual([]);
});
