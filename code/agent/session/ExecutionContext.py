"""工具调用期间共享、不可变的执行环境。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionContext:
    """描述一次 Agent 会话中工具运行所需的环境信息。

    Attributes:
        project_path: 用户为当前 Session 选择的项目目录；为空时不能执行项目工具。
        agent_id: 稳定的逻辑 Agent 标识，用于执行记录，不参与授权归属。
        session_id: 当前交互会话标识。
        max_tool_call_length: 单次工具文本输出允许返回给模型的最大字符数。
    """

    project_path: str | None
    agent_id: str
    session_id: str
    max_tool_call_length: int = 20_000

    def __post_init__(self) -> None:
        """尽早拒绝缺少身份或非法项目目录的执行上下文。"""
        if self.project_path is not None and not self.project_path:
            raise ValueError("project_path 必须是非空路径或 None")
        if not self.agent_id:
            raise ValueError("agent_id 不能为空")
        if not self.session_id:
            raise ValueError("session_id 不能为空")
        if self.max_tool_call_length <= 0:
            raise ValueError("max_tool_call_length 必须大于 0")
