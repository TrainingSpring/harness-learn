"""Session 级权限规则的 SQLite 仓储。"""

import os
import sqlite3
from datetime import datetime, timezone

from permission.types import (
    PermissionAction,
    PermissionDecision,
    PermissionRule,
)

from ..database import StateDatabase
from ..errors import StorageConflictError, StorageFormatError
from ..ids import generate_id, validate_id


class SessionPermissionRuleRepository:
    """持久化一个 Session 内有效的 allow/deny 规则。"""

    def __init__(self, database: StateDatabase) -> None:
        self.database = database

    def list_for_session(self, session_id: str) -> list[PermissionRule]:
        validate_id("session", session_id)
        project_path = self._project_path(session_id)
        rows = self.database.connection.execute(
            """
            SELECT * FROM session_permission_rules
            WHERE session_id = ?
            ORDER BY updated_at ASC, id ASC
            """,
            (session_id,),
        ).fetchall()
        return [self._from_row(row, project_path) for row in rows]

    def save(self, rule: PermissionRule) -> PermissionRule:
        self._validate_rule(rule)
        project_path = self._project_path(rule.session_id)
        resource_kind, resource_value = self._encode_resource(rule.resource, project_path)
        now = _utc_now()
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO session_permission_rules (
                        id, session_id, action, resource_kind, resource_value,
                        decision, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id, action, resource_kind, resource_value)
                    DO UPDATE SET decision = excluded.decision, updated_at = excluded.updated_at
                    """,
                    (
                        generate_id("permission_rule"),
                        rule.session_id,
                        rule.action.value,
                        resource_kind,
                        resource_value,
                        rule.decision.value,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise StorageConflictError(
                f"Session 权限规则保存冲突: {rule.session_id}"
            ) from error
        return rule

    @staticmethod
    def _validate_rule(rule: PermissionRule) -> None:
        if not isinstance(rule, PermissionRule):
            raise TypeError("rule 必须是 PermissionRule")
        validate_id("session", rule.session_id)

    def _project_path(self, session_id: str) -> str | None:
        row = self.database.connection.execute(
            "SELECT project_path FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Session 不存在: {session_id}")
        project_path = row["project_path"]
        if project_path is None:
            return None
        if not isinstance(project_path, str) or not os.path.isabs(project_path):
            raise StorageFormatError("Session project_path 不是有效绝对路径")
        return os.path.normpath(os.path.abspath(project_path))

    @staticmethod
    def _encode_resource(
        resource: str | None,
        project_path: str | None,
    ) -> tuple[str, str | None]:
        if resource is None:
            return "none", None
        if project_path is None:
            raise ValueError("空项目 Session 不能保存文件权限规则")
        if not isinstance(resource, str) or not os.path.isabs(resource):
            raise ValueError("权限规则资源必须是绝对路径")
        normalized = os.path.normpath(os.path.abspath(resource))
        try:
            if os.path.commonpath([normalized, project_path]) != project_path:
                raise ValueError("权限规则资源必须位于 Session 项目目录内")
        except ValueError as error:
            raise ValueError("权限规则资源必须位于 Session 项目目录内") from error
        return "path", os.path.relpath(normalized, project_path)

    @staticmethod
    def _from_row(row: sqlite3.Row, project_path: str | None) -> PermissionRule:
        try:
            action = PermissionAction(row["action"])
            decision = PermissionDecision(row["decision"])
        except (TypeError, ValueError) as error:
            raise StorageFormatError("Session 权限规则动作或决定无效") from error
        kind = row["resource_kind"]
        if kind == "none":
            resource = None
        elif kind == "path" and project_path is not None:
            value = row["resource_value"]
            if not isinstance(value, str) or not value:
                raise StorageFormatError("Session 权限规则路径无效")
            resource = os.path.normpath(os.path.abspath(os.path.join(project_path, value)))
            try:
                if os.path.commonpath([resource, project_path]) != project_path:
                    raise StorageFormatError("Session 权限规则路径越出项目目录")
            except ValueError as error:
                raise StorageFormatError("Session 权限规则路径越出项目目录") from error
        else:
            raise StorageFormatError("Session 权限规则资源无效")
        return PermissionRule(
            action=action,
            resource=resource,
            decision=decision,
            session_id=row["session_id"],
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
