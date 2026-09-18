"""工具调用期间共享、不可变的执行环境。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionContext:
    """描述一次 Agent 会话中工具运行所需的环境信息。

    Attributes:
        workspace: 工具解析相对路径时使用的工作目录；它不是本期的安全
            沙箱边界，路径隔离由后续 harness 层实现。
        agent_id: 稳定的逻辑 Agent 标识，用于跨会话的 AGENT 权限规则。
        session_id: 当前交互会话标识，用于 SESSION 权限规则。
        max_tool_call_length: 单次工具文本输出允许返回给模型的最大字符数。
    """

    workspace: str
    agent_id: str
    session_id: str
    max_tool_call_length: int = 20_000

    def __post_init__(self) -> None:
        """尽早拒绝缺少身份或工作目录的执行上下文。"""
        if not self.workspace:
            raise ValueError("workspace 不能为空")
        if not self.agent_id:
            raise ValueError("agent_id 不能为空")
        if not self.session_id:
            raise ValueError("session_id 不能为空")
        if self.max_tool_call_length <= 0:
            raise ValueError("max_tool_call_length 必须大于 0")
