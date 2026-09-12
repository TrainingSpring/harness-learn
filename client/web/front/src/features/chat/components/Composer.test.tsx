import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { Composer } from "./Composer";

it("Enter 发送而 Shift+Enter 保留换行", async () => {
  const onSend = vi.fn();
  render(<Composer onSend={onSend} isRunning={false} onStop={vi.fn()} />);
  const textbox = screen.getByRole("textbox", { name: "消息" });

  await userEvent.type(textbox, "第一行{shift>}{enter}{/shift}第二行{enter}");

  expect(onSend).toHaveBeenCalledWith("第一行\n第二行");
});

it("运行期间显示停止按钮并禁止重复输入", () => {
  render(<Composer onSend={vi.fn()} isRunning onStop={vi.fn()} />);

  expect(screen.getByRole("textbox", { name: "消息" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "停止生成" })).toBeInTheDocument();
});
