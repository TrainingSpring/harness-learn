import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { PermissionDialog } from "./PermissionDialog";

it("默认只允许本次并提交选中的范围", async () => {
  const onDecision = vi.fn();
  render(
    <PermissionDialog
      request={{
        callId: "call_1",
        toolName: "write",
        action: "filesystem.write",
        resource: "/tmp/example.txt",
        allowedScopes: ["once", "session", "agent"],
      }}
      isSubmitting={false}
      onDecision={onDecision}
    />,
  );

  expect(screen.getByRole("radio", { name: "仅本次" })).toBeChecked();
  await userEvent.click(screen.getByRole("radio", { name: "当前会话" }));
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

  await userEvent.click(screen.getByRole("button", { name: "拒绝" }));
  expect(onDecision).toHaveBeenCalledWith("deny", "once");
});
