"""持久化领域对象。

这些对象表达业务数据，不负责 SQL、LLM 调用或工具执行。Repository 负责在
它们和 SQLite 行之间进行转换；运行时 Agent 则由 AgentProfile 重新组装。
"""

from dataclasses import dataclass, field
from typing import Any

from .ids import validate_id


def _validate_non_empty(value: str, field_name: str) -> None:
    """验证 ID 之外的必填字符串字段。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串")


@dataclass
class LLMProfile:
    """可复用的 LLM 连接和调用配置。

    Attributes:
        id: 带 llm_ 前缀的稳定配置 ID。
        name: 用户可读的配置名称。
        provider: 模型服务商名称。
        base_url: 可选的服务地址。
        model: 模型名称。
        api_key: 保存在当前 workspace SQLite 中的 API Key。
        options: 经过校验的额外调用参数。
        created_at: 创建时间；持久化时由 Repository 补充。
        updated_at: 最后更新时间；持久化时由 Repository 补充。
    """

    id: str
    name: str
    provider: str
    base_url: str | None
    model: str
    api_key: str
    options: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        """校验 LLMProfile 的身份和必填连接参数。"""
        validate_id("llm", self.id)
        _validate_non_empty(self.name, "name")
        _validate_non_empty(self.provider, "provider")
        _validate_non_empty(self.model, "model")
        if not isinstance(self.api_key, str):
            raise ValueError("api_key 必须是字符串")
        if not isinstance(self.options, dict):
            raise ValueError("options 必须是字典")


@dataclass
class AgentProfile:
    """可复用的逻辑 Agent 配置。

    Attributes:
        id: 带 agent_ 前缀的稳定 Agent 身份。
        name: 用户看到的 Agent 名称。
        description: Agent 的职责和能力简介。
        personality: Agent 的性格和表达风格。
        expertise: Agent 擅长的领域标签。
        llm_profile_id: 该 Agent 使用的 LLMProfile ID。
        tools: 该 Agent 配置拥有的工具名称列表。
        is_enabled: 是否允许用户选择和加载该 Agent。
        created_at: 创建时间。
        updated_at: 最后更新时间。
    """

    id: str
    name: str
    description: str
    personality: str
    expertise: list[str]
    llm_profile_id: str
    tools: list[str]
    is_enabled: bool = True
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        """校验 Agent 身份、引用和工具集合。"""
        validate_id("agent", self.id)
        validate_id("llm", self.llm_profile_id)
        _validate_non_empty(self.name, "name")
        if not isinstance(self.expertise, list) or not all(
            isinstance(item, str) and item.strip() for item in self.expertise
        ):
            raise ValueError("expertise 必须是字符串列表")
        if not isinstance(self.tools, list) or not all(
            isinstance(item, str) and item.strip() for item in self.tools
        ):
            raise ValueError("tools 必须是非空字符串列表")


@dataclass
class Session:
    """一次可恢复的用户任务或多 Agent 会话容器。"""

    id: str
    title: str | None
    conversation_mode: str
    status: str
    permission_mode: str = "plan"
    project_path: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    closed_at: str | None = None

    def __post_init__(self) -> None:
        """校验会话模式和生命周期状态。"""
        validate_id("session", self.id)
        if self.conversation_mode not in {"DIRECT", "GROUP"}:
            raise ValueError(f"未知的会话模式: {self.conversation_mode}")
        if self.status not in {"ACTIVE", "PAUSED", "COMPLETED", "CLOSED", "FAILED"}:
            raise ValueError(f"未知的会话状态: {self.status}")
        if self.permission_mode not in {"plan", "build", "yolo"}:
            raise ValueError(f"未知的权限模式: {self.permission_mode}")
        if self.project_path is not None and not self.project_path:
            raise ValueError("project_path 必须是非空路径或 None")


@dataclass(frozen=True)
class DirectSessionSummary:
    """供客户端读取的固定 1v1 会话聚合摘要。

    Attributes:
        session: DIRECT 会话的基础数据。
        agent_id: 会话中唯一 Agent 的稳定 ID。
        agent_name: 会话中唯一 Agent 的用户可读名称。
        last_message: 最后一条用户或 Agent 消息的文本；无消息时为 None。
        last_sequence_no: 最后一条可展示消息的会话序号；无消息时为 None。

    该类型是只读查询结果，不参与 Session 或 ContextItem 的写入流程。
    """

    session: Session
    agent_id: str
    agent_name: str
    last_message: str | None
    last_sequence_no: int | None

    def __post_init__(self) -> None:
        """校验 1v1 聚合中的会话、Agent 和最后消息字段。"""
        if not isinstance(self.session, Session):
            raise ValueError("session 必须是 Session")
        if self.session.conversation_mode != "DIRECT":
            raise ValueError("DirectSessionSummary 只能包含 DIRECT 会话")
        validate_id("agent", self.agent_id)
        _validate_non_empty(self.agent_name, "agent_name")
        if self.last_message is None:
            if self.last_sequence_no is not None:
                raise ValueError("无最后消息时不能存在 last_sequence_no")
            return
        if not isinstance(self.last_message, str):
            raise ValueError("last_message 必须是字符串或 None")
        if (
            not isinstance(self.last_sequence_no, int)
            or isinstance(self.last_sequence_no, bool)
            or self.last_sequence_no <= 0
        ):
            raise ValueError("last_sequence_no 必须是正整数")


@dataclass
class SessionAgent:
    """表示固定会话与一个逻辑 Agent 之间的成员关系。

    Attributes:
        session_id: 成员所属的固定会话 ID。
        agent_id: AgentProfile 的稳定 ID，同时也是上下文中的作者身份。
        role: 会话内角色；PRIMARY 表示 1v1 主角色，MEMBER 表示群聊成员。
        created_at: 成员关系创建时间，由仓储在首次写入时补充。

    成员关系由 ``session_id + agent_id`` 唯一确定，不再创建临时的
    participant_id。当前产品中的会话成员创建后不可退出或替换。
    """

    session_id: str
    agent_id: str
    role: str
    created_at: str | None = None

    def __post_init__(self) -> None:
        """校验会话、Agent 引用和固定成员角色。"""
        validate_id("session", self.session_id)
        validate_id("agent", self.agent_id)
        if self.role not in {"PRIMARY", "MEMBER"}:
            raise ValueError(f"未知的会话 Agent 角色: {self.role}")


@dataclass
class ContextItem:
    """会话时间线中的一条消息或执行事件。"""

    id: str
    session_id: str
    sequence_no: int
    kind: str
    author_agent_id: str | None
    target_agent_id: str | None
    visibility: str
    payload: dict[str, Any]
    call_id: str | None = None
    caused_by_item_id: str | None = None
    created_at: str | None = None

    def __post_init__(self) -> None:
        """校验上下文类型、目标语义和会话内引用。"""
        validate_id("item", self.id)
        validate_id("session", self.session_id)
        if self.sequence_no < 0:
            raise ValueError("sequence_no 不能是负数")
        if self.kind not in {
            "USER_MESSAGE",
            "AGENT_MESSAGE",
            "FUNCTION_CALL",
            "FUNCTION_CALL_OUTPUT",
            "AGENT_DELEGATION",
            "SYSTEM_EVENT",
        }:
            raise ValueError(f"未知的上下文类型: {self.kind}")
        if self.visibility not in {"PUBLIC", "TARGETED", "PRIVATE"}:
            raise ValueError(f"未知的可见性: {self.visibility}")
        if self.author_agent_id is not None:
            validate_id("agent", self.author_agent_id)
        if self.target_agent_id is not None:
            validate_id("agent", self.target_agent_id)
        if self.caused_by_item_id is not None:
            validate_id("item", self.caused_by_item_id)
        if self.visibility == "PUBLIC" and self.target_agent_id is not None:
            raise ValueError("PUBLIC 上下文不能指定单个目标")
        if self.visibility == "TARGETED" and self.target_agent_id is None:
            raise ValueError("TARGETED 上下文必须指定一个目标")
        if self.visibility == "PRIVATE" and self.target_agent_id is not None:
            raise ValueError("PRIVATE 上下文不能指定目标")
        if not isinstance(self.payload, dict):
            raise ValueError("payload 必须是字典")
