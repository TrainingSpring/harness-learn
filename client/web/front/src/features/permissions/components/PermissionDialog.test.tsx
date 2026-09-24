import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { PermissionDialog } from "./PermissionDialog";

it("提供明确的本次和会话允许操作", async () => {
  const onDecision = vi.fn();
  render(
    <PermissionDialog
      request={{
        callId: "call_1",
        toolName: "write",
        action: "filesystem.write",
        resource: "/tmp/example.txt",
        allowedScopes: ["once", "session"],
      }}
      isSubmitting={false}
      onDecision={onDecision}
    />,
  );

  await userEvent.click(screen.getByRole("button", { name: "仅本次允许" }));
  expect(onDecision).toHaveBeenCalledWith("allow", "once");
  await userEvent.click(screen.getByRole("button", { name: "本会话允许" }));

  expect(onDecision).toHaveBeenCalledWith("allow", "session");
});

it("拒绝不携带可扩大权限的范围", async () => {
  const onDecision = vi.fn();
  render(
    <PermissionDialog
      request={{ callId: "call_1", toolName: "bash", action: "shell.execute", resource: "rm demo", allowedScopes: ["once"] }}
      isSubmitting={false}
      onDecision={onDecision}
    />,
  );

  expect(screen.getByText("此处确认的是整条终端命令。本会话允许或不再询问会影响后续所有终端命令。")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "拒绝" }));
  expect(onDecision).toHaveBeenCalledWith("deny", "once");
});

it("允许本会话后可以选择不再询问", async () => {
  const onDecision = vi.fn();
  render(
    <PermissionDialog
      request={{ callId: "call_1", toolName: "bash", action: "shell.execute", resource: "pwd", allowedScopes: ["once", "session"] }}
      isSubmitting={false}
      onDecision={onDecision}
    />,
  );

  await userEvent.click(screen.getByRole("button", { name: "不再询问" }));
  expect(onDecision).toHaveBeenCalledWith("deny", "session");
});
