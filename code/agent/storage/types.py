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
        credential_ref: 凭据引用，不保存实际 API Key。
        options: 经过校验的额外调用参数。
        created_at: 创建时间；持久化时由 Repository 补充。
        updated_at: 最后更新时间；持久化时由 Repository 补充。
    """

    id: str
    name: str
    provider: str
    base_url: str | None
    model: str
    credential_ref: str
    options: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        """校验 LLMProfile 的身份和必填连接参数。"""
        validate_id("llm", self.id)
        _validate_non_empty(self.name, "name")
        _validate_non_empty(self.provider, "provider")
        _validate_non_empty(self.model, "model")
        _validate_non_empty(self.credential_ref, "credential_ref")
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
        permission_mode: 没有命中明确规则时使用的默认权限模式。
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
    permission_mode: str
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
        if not isinstance(self.permission_mode, str) or not self.permission_mode:
            raise ValueError("permission_mode 必须是非空字符串")


@dataclass
class Session:
    """一次可恢复的用户任务或多 Agent 会话容器。"""

    id: str
    title: str | None
    conversation_mode: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None
    closed_at: str | None = None

    def __post_init__(self) -> None:
        """校验会话模式和生命周期状态。"""
        validate_id("session", self.id)
        if self.conversation_mode not in {"DIRECT", "GROUP", "OPEN"}:
            raise ValueError(f"未知的会话模式: {self.conversation_mode}")
        if self.status not in {"ACTIVE", "PAUSED", "COMPLETED", "CLOSED", "FAILED"}:
            raise ValueError(f"未知的会话状态: {self.status}")


@dataclass
class SessionParticipant:
    """表示一个 Agent 在某个 Session 中的参与身份。"""

    id: str
    session_id: str
    agent_id: str
    role: str
    join_reason: str | None
    joined_at: str | None = None
    left_at: str | None = None

    def __post_init__(self) -> None:
        """校验参与者关联的实体 ID 和角色。"""
        validate_id("participant", self.id)
        validate_id("session", self.session_id)
        validate_id("agent", self.agent_id)
        if self.role not in {"PRIMARY", "PARTICIPANT"}:
            raise ValueError(f"未知的参与者角色: {self.role}")
        if self.join_reason is not None and self.join_reason not in {
            "USER_SELECTED",
            "DELEGATED",
            "AUTO_JOINED",
        }:
            raise ValueError(f"未知的参与原因: {self.join_reason}")


@dataclass
class ContextItem:
    """会话时间线中的一条消息或执行事件。"""

    id: str
    session_id: str
    sequence_no: int
    kind: str
    author_participant_id: str | None
    target_participant_id: str | None
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
        if self.author_participant_id is not None:
            validate_id("participant", self.author_participant_id)
        if self.target_participant_id is not None:
            validate_id("participant", self.target_participant_id)
        if self.caused_by_item_id is not None:
            validate_id("item", self.caused_by_item_id)
        if self.visibility == "PUBLIC" and self.target_participant_id is not None:
            raise ValueError("PUBLIC 上下文不能指定单个目标")
        if self.visibility == "TARGETED" and self.target_participant_id is None:
            raise ValueError("TARGETED 上下文必须指定一个目标")
        if self.visibility == "PRIVATE" and self.target_participant_id is not None:
            raise ValueError("PRIVATE 上下文不能指定目标")
        if not isinstance(self.payload, dict):
            raise ValueError("payload 必须是字典")


@dataclass
class AgentDelegation:
    """记录一个 Agent 委托另一个 Agent 处理任务的生命周期。"""

    id: str
    session_id: str
    requester_participant_id: str
    worker_participant_id: str
    request_item_id: str
    status: str
    parent_delegation_id: str | None = None
    result_item_id: str | None = None
    created_at: str | None = None
    completed_at: str | None = None

    def __post_init__(self) -> None:
        """校验委托链中所有实体均使用正确的 ID 类型。"""
        validate_id("delegation", self.id)
        validate_id("session", self.session_id)
        validate_id("participant", self.requester_participant_id)
        validate_id("participant", self.worker_participant_id)
        validate_id("item", self.request_item_id)
        if self.parent_delegation_id is not None:
            validate_id("delegation", self.parent_delegation_id)
        if self.result_item_id is not None:
            validate_id("item", self.result_item_id)
        if self.status not in {
            "PENDING",
            "RUNNING",
            "COMPLETED",
            "FAILED",
            "CANCELLED",
        }:
            raise ValueError(f"未知的委托状态: {self.status}")
