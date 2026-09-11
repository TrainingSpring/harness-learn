"""Agent 级权限规则的 SQLite 仓储。"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from permission.types import (
    PermissionAction,
    PermissionDecision,
    PermissionRule,
    PermissionScope,
)

from ..database import StateDatabase
from ..errors import StorageConflictError, StorageFormatError
from ..ids import generate_id, validate_id


class PermissionRuleRepository:
    """负责持久化 Agent 级文件权限规则。

    Attributes:
        database: 已初始化的 workspace 状态数据库。
        workspace: 规则资源允许覆盖的工作目录；数据库只保存相对路径。

    首期只保存 ``AGENT`` 作用域的 ``FILE_READ`` 和 ``FILE_WRITE`` 规则。
    ``ONCE``、``SESSION`` 属于运行时状态，``BASH_EXECUTE`` 暂不支持跨会话
    持久化，避免把无法精确描述的命令权限变成过宽的长期授权。
    """

    _SUPPORTED_ACTIONS = frozenset(
        {PermissionAction.FILE_READ, PermissionAction.FILE_WRITE}
    )

    def __init__(self, database: StateDatabase) -> None:
        """创建权限规则仓储。

        Args:
            database: 已调用 ``initialize()`` 的状态数据库。
        """
        self.database = database
        self.workspace = database.workspace

    def list_for_agent(self, agent_id: str) -> list[PermissionRule]:
        """读取一个 Agent 的全部持久化规则。

        Args:
            agent_id: 带 ``agent_`` 前缀的稳定 Agent ID。

        Returns:
            按更新时间和规则 ID 稳定排序的 Agent 级规则列表。

        Raises:
            StorageFormatError: 数据库中存在非法动作、资源或决定时抛出。

        读取时重新把 workspace 相对路径解析为绝对路径，并再次检查路径边界。
        这一步不能省略，否则手工改库或数据库损坏可能变成越权授权。
        """
        validate_id("agent", agent_id)
        rows = self.database.connection.execute(
            """
            SELECT * FROM permission_agent_rules
            WHERE agent_id = ?
            ORDER BY updated_at ASC, id ASC
            """,
            (agent_id,),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    def save(self, rule: PermissionRule) -> PermissionRule:
        """保存一条 Agent 级文件规则，并替换同一规则槽位的旧决定。

        Args:
            rule: 需要保存的权限规则；必须是 AGENT 作用域的文件规则。

        Returns:
            校验并写入数据库的原规则对象。

        Raises:
            ValueError: 规则作用域、动作或资源不符合首期持久化契约。
            StorageConflictError: Agent 外键不存在或数据库约束冲突。
        """
        self._validate_rule(rule)
        resource_value = self._to_workspace_relative(rule.resource)
        now = _utc_now()
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO permission_agent_rules (
                        id, agent_id, action, resource_kind, resource_value,
                        decision, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(agent_id, action, resource_kind, resource_value)
                    DO UPDATE SET
                        decision = excluded.decision,
                        updated_at = excluded.updated_at
                    """,
                    (
                        generate_id("permission_rule"),
                        rule.agent_id,
                        rule.action.value,
                        "path",
                        resource_value,
                        rule.decision.value,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise StorageConflictError(
                f"权限规则保存冲突: {rule.agent_id}"
            ) from error
        return rule

    def _validate_rule(self, rule: PermissionRule) -> None:
        """验证规则是否属于首期可持久化的安全子集。"""
        if not isinstance(rule, PermissionRule):
            raise TypeError("rule 必须是 PermissionRule")
        if rule.scope is not PermissionScope.AGENT:
            raise ValueError("PermissionRuleRepository 只支持 AGENT 规则")
        if rule.action not in self._SUPPORTED_ACTIONS:
            raise ValueError("首期只允许持久化文件读写规则")
        if rule.resource is None:
            raise ValueError("文件权限规则必须指定绝对资源路径")
        validate_id("agent", rule.agent_id)
        self._to_workspace_relative(rule.resource)

    def _to_workspace_relative(self, resource: str) -> str:
        """把绝对资源路径转换为 workspace 内的规范相对路径。"""
        if not isinstance(resource, str) or not os.path.isabs(resource):
            raise ValueError("持久化权限资源必须是绝对路径")
        normalized_resource = os.path.normpath(os.path.abspath(resource))
        normalized_workspace = os.path.normpath(
            os.path.abspath(str(self.workspace))
        )
        try:
            if os.path.commonpath([normalized_resource, normalized_workspace]) != normalized_workspace:
                raise ValueError("Agent 级权限规则不能越出 workspace")
        except ValueError as error:
            raise ValueError("Agent 级权限规则不能越出 workspace") from error
        relative = os.path.relpath(normalized_resource, normalized_workspace)
        return Path(relative).as_posix()

    def _from_row(self, row: sqlite3.Row) -> PermissionRule:
        """将一行数据库记录严格转换为 PermissionRule。"""
        try:
            action = PermissionAction(row["action"])
            decision = PermissionDecision(row["decision"])
        except (TypeError, ValueError) as error:
            raise StorageFormatError("权限规则动作或决定不是有效枚举值") from error

        if row["resource_kind"] != "path":
            raise StorageFormatError("权限规则 resource_kind 不是 path")
        resource_value = row["resource_value"]
        if not isinstance(resource_value, str) or not resource_value:
            raise StorageFormatError("权限规则 resource_value 不是有效路径")

        resource = os.path.normpath(
            os.path.abspath(os.path.join(str(self.workspace), resource_value))
        )
        try:
            self._to_workspace_relative(resource)
            return PermissionRule(
                action=action,
                resource=resource,
                decision=decision,
                scope=PermissionScope.AGENT,
                agent_id=row["agent_id"],
            )
        except (TypeError, ValueError) as error:
            raise StorageFormatError("权限规则数据不符合领域约束") from error


def _utc_now() -> str:
    """生成统一的 UTC ISO 时间字符串。"""
    return datetime.now(timezone.utc).isoformat()
