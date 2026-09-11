"""权限系统使用的领域值对象。

本模块只描述权限“是什么”：动作、请求、规则和用户确认；不包含
规则匹配、文件系统访问或 CLI 交互。这样工具、运行时和权限管理器
可以共享同一契约，而不依赖彼此的实现细节。
"""

from dataclasses import dataclass
from enum import StrEnum


class PermissionAction(StrEnum):
    """工具可能请求的受控动作。

    枚举值是稳定的机器可读标识，规则存储、日志和未来 MCP 适配都应
    使用它们，而不是根据工具名称判断权限。
    """

    FILE_READ = "filesystem.read"
    FILE_WRITE = "filesystem.write"
    BASH_EXECUTE = "bash.execute"


class PermissionDecision(StrEnum):
    """权限检查的三态结果。

    `ASK` 表示需要 Runtime 暂停并向用户确认；它只描述一次检查结果，
    不能写入长期规则。
    """

    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class PermissionScope(StrEnum):
    """用户确认后写入规则的生效范围。"""

    ONCE = "once"
    SESSION = "session"
    AGENT = "agent"


class PermissionMode(StrEnum):
    """没有命中明确规则时使用的默认权限模式。"""

    PLAN = "plan"
    BUILD = "build"
    YOLO = "yolo"


@dataclass(frozen=True)
class PermissionRequirement:
    """工具静态声明的权限需求。

    Attributes:
        action: 工具执行时需要检查的动作。
        resource_from: 资源所在的工具参数名；没有可可靠定位资源的工具
            （例如 bash）使用 None。
    """

    action: PermissionAction
    resource_from: str | None

    def __post_init__(self) -> None:
        """校验资源参数名，避免工具注册后在运行时才发现配置错误。"""
        if self.resource_from is not None and not self.resource_from:
            raise ValueError("resource_from 只能是非空参数名或 None")


@dataclass(frozen=True)
class PermissionRequest:
    """一次真实工具调用的权限请求。

    Attributes:
        action: 本次调用请求的动作。
        resource: 已解析、规范化后的实际资源；bash 等无可靠资源归属的
            调用为 None。
        tool_name: 发起请求的已注册工具名，仅用于呈现和诊断。
        call_id: 模型本次 function_call 的标识，用于 ONCE 规则和恢复。
        session_id: 当前 Agent 会话标识，用于 SESSION 规则。
        agent_id: 稳定逻辑 Agent 标识，用于跨会话的 AGENT 规则。
    """

    action: PermissionAction
    resource: str | None
    tool_name: str
    call_id: str
    session_id: str
    agent_id: str

    def __post_init__(self) -> None:
        """保证用于规则匹配和恢复的身份字段都存在。"""
        if not self.tool_name:
            raise ValueError("tool_name 不能为空")
        if not self.call_id:
            raise ValueError("call_id 不能为空")
        if not self.session_id:
            raise ValueError("session_id 不能为空")
        if not self.agent_id:
            raise ValueError("agent_id 不能为空")


@dataclass(frozen=True)
class PermissionRule:
    """用户确认后保存的允许或拒绝规则。

    Attributes:
        action: 规则约束的动作。
        resource: 覆盖的资源根；文件操作通常是目录，None 仅用于无资源
            动作，例如 bash.execute。
        decision: 持久化的允许或拒绝决定，禁止保存 ASK。
        scope: 规则的生效范围。
        call_id: ONCE 规则绑定的调用标识。
        session_id: SESSION 规则绑定的会话标识。
        agent_id: AGENT 规则绑定的逻辑 Agent 标识。
    """

    action: PermissionAction
    resource: str | None
    decision: PermissionDecision
    scope: PermissionScope
    call_id: str | None = None
    session_id: str | None = None
    agent_id: str | None = None

    def __post_init__(self) -> None:
        """确保每种 scope 只携带自己需要的身份字段。"""
        if self.decision is PermissionDecision.ASK:
            raise ValueError("ASK 是暂态权限结果，不能保存为 PermissionRule")

        expected_identity = {
            PermissionScope.ONCE: ("call_id", self.call_id),
            PermissionScope.SESSION: ("session_id", self.session_id),
            PermissionScope.AGENT: ("agent_id", self.agent_id),
        }
        identity_name, identity_value = expected_identity[self.scope]
        other_values = {
            "call_id": self.call_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
        }
        other_values.pop(identity_name)

        if not identity_value:
            raise ValueError(f"{self.scope.value} 规则必须绑定 {identity_name}")
        if any(other_values.values()):
            raise ValueError(f"{self.scope.value} 规则不能绑定其他作用域身份")


@dataclass(frozen=True)
class PermissionResponse:
    """用户对待确认权限请求作出的选择。

    Attributes:
        call_id: 必须对应 Runtime 当前等待确认的 function call。
        decision: 用户的最终允许或拒绝选择，禁止 ASK。
        scope: 用户希望将选择保存到的作用域。
    """

    call_id: str
    decision: PermissionDecision
    scope: PermissionScope

    def __post_init__(self) -> None:
        """阻止空 call_id 和无意义的二次 ASK 响应。"""
        if not self.call_id:
            raise ValueError("call_id 不能为空")
        if self.decision is PermissionDecision.ASK:
            raise ValueError("PermissionResponse 只能允许或拒绝")
