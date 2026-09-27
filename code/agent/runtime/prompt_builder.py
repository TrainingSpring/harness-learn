"""根据运行中的 Agent 生成系统指令。"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .agent import Agent


class PromptBuilder:
    """把 Agent 的角色字段和 Session 能力组装成系统指令。"""

    def build(
        self,
        agent: "Agent",
        session_context: str | None = None,
        tools: list[str] | None = None,
        permission_mode: str | None = None,
        skill_metadata: str | None = None,
    ) -> str:
        """生成当前 Agent 的系统指令。"""
        if not agent.description.strip():
            raise ValueError("Agent description 不能为空")

        effective_tools = (
            [tool.schema["name"] for tool in agent.tool_definitions]
            if tools is None
            else tools
        )
        expertise = "、".join(agent.expertise) or "未指定"
        tool_text = "、".join(effective_tools) or "无"

        sections = [
            f"你是 {agent.name}。",
            f"Agent 描述：{agent.description}",
            f"Agent 性格：{agent.personality or '未指定'}",
            f"擅长领域：{expertise}",
            f"可使用工具：{tool_text}",
            "请遵循系统规则，明确区分分析、工具调用和最终回答。",
        ]
        if permission_mode is not None:
            sections.append(f"当前权限模式：{permission_mode}")
            sections.append(self._permission_instruction(permission_mode))
        if session_context:
            sections.append(f"当前会话背景：{session_context}")
        if skill_metadata:
            sections.append(skill_metadata)
        return "\n".join(sections)

    @staticmethod
    def _permission_instruction(permission_mode: str) -> str:
        """将 Session 权限规则转成 Agent 可执行的工具调用指令。"""
        mode = permission_mode.lower()
        if mode == "plan":
            return (
                "权限执行规则：只可读取工作目录内资源。不要尝试写入、访问工作目录外"
                "资源或执行通用终端命令；应直接说明限制。"
            )
        if mode == "build":
            return (
                "权限执行规则：工作目录内文件读写可直接调用工具。访问工作目录外的"
                "文件或目录时，仍须发起工具调用，由系统向用户请求确认；不要根据历史"
                "消息自行断言没有权限。通用终端命令也由系统逐条确认。工具是否执行"
                "及最终权限结论以工具结果为准。"
            )
        if mode == "yolo":
            return (
                "权限执行规则：普通资源可直接调用工具；只有系统强制安全规则或工具"
                "结果可以阻止操作。不要根据工作目录边界自行断言没有权限。"
            )
        raise ValueError("permission_mode 必须是 plan、build 或 yolo")
