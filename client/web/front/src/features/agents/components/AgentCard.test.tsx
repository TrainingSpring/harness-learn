import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AgentCard } from "./AgentCard";

it("展示角色能力并将角色 id 带入新对话链接", () => {
  render(
    <MemoryRouter>
      <AgentCard agent={{
        id: "agent_ENGINEER01",
        name: "工程师",
        description: "负责实现和审查代码",
        personality: "直接、严谨",
        expertise: ["Python", "API"],
        tools: ["read", "write", "bash", "edit"],
        isEnabled: true,
      }} />
    </MemoryRouter>,
  );

  expect(screen.getByRole("heading", { name: "工程师" })).toBeInTheDocument();
  expect(screen.getByText("另有 1 项")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "与工程师开始对话" })).toHaveAttribute("href", "/new?agentId=agent_ENGINEER01");
});
