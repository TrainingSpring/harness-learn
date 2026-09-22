"""根据 Agent 配置生成运行时系统指令。"""

from storage.types import AgentProfile


class PromptBuilder:
    """把 AgentProfile 的语义字段组装成发送给 LLM 的系统指令。

    最终 prompt 不持久化，因为工具列表、权限模式和会话上下文都可能在
    运行时发生变化。AgentProfile 保存原始配置，PromptBuilder 生成派生结果。
    """

    def build(
        self,
        profile: AgentProfile,
        session_context: str | None = None,
        tools: list[str] | None = None,
        permission_mode: str | None = None,
    ) -> str:
        """生成当前 Agent 的系统指令。

        Args:
            profile: 已校验的 AgentProfile。
            session_context: 当前会话需要附加的运行时背景。
            tools: 可选的运行时工具列表；为空时使用 profile.tools。
        permission_mode: 可选的运行时权限模式。

        Returns:
            组合后的系统指令文本。

        Raises:
            ValueError: Agent 描述为空时抛出。
        """
        if not profile.description.strip():
            raise ValueError("Agent description 不能为空")

        effective_tools = profile.tools if tools is None else tools
        expertise = "、".join(profile.expertise) or "未指定"
        tool_text = "、".join(effective_tools) or "无"

        sections = [
            f"你是 {profile.name}。",
            f"Agent 描述：{profile.description}",
            f"Agent 性格：{profile.personality or '未指定'}",
            f"擅长领域：{expertise}",
            f"可使用工具：{tool_text}",
            "请遵循系统规则，明确区分分析、工具调用和最终回答。",
        ]
        if permission_mode is not None:
            sections.append(f"当前权限模式：{permission_mode}")
        if session_context:
            sections.append(f"当前会话背景：{session_context}")
        return "\n".join(sections)
