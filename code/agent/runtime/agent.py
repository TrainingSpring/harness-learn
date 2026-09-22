"""可跨 Session 复用的稳定 Agent 定义。"""

from dataclasses import dataclass
from head.types import LLMConfig
from storage.types import AgentProfile
from tools.types import Tool


@dataclass(frozen=True)
class Agent:
    """描述 Agent 的稳定身份和能力，不包含任何 Session 执行状态。"""

    agent_id: str
    profile: AgentProfile
    llm_config: LLMConfig
    tool_definitions: tuple[Tool, ...]
