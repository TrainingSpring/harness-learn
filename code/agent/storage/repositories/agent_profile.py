"""AgentProfile 的 SQLite 仓储。"""

import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone

from ..database import StateDatabase
from ..errors import StorageConflictError, StorageFormatError
from ..ids import validate_id
from ..types import AgentProfile


class AgentProfileRepository:
    """负责 AgentProfile 与 agent_profiles 表之间的转换。

    AgentProfile 直接保存工具名称列表；首期不引入独立的 AgentToolConfig。
    仓储只负责持久化和查询，不负责创建运行时 Agent 或组装系统指令。
    """

    def __init__(self, database: StateDatabase) -> None:
        """创建 AgentProfile 仓储。

        Args:
            database: 已调用 initialize() 的状态数据库。
        """
        self.database = database

    def get(self, agent_id: str) -> AgentProfile | None:
        """根据稳定 Agent ID 读取配置。"""
        validate_id("agent", agent_id)
        row = self.database.connection.execute(
            "SELECT * FROM agent_profiles WHERE id = ?",
            (agent_id,),
        ).fetchone()
        return None if row is None else self._from_row(row)

    def list_enabled(
        self,
        limit: int,
        offset: int,
        expertise: str | None = None,
    ) -> list[AgentProfile]:
        """分页读取启用的 Agent，可按 expertise 标签筛选。

        Args:
            limit: 最大返回数量。
            offset: 跳过的记录数量。
            expertise: 可选的精确领域标签。

        Returns:
            符合条件的 AgentProfile 列表。
        """
        self._validate_page(limit, offset)
        if expertise is not None and (
            not isinstance(expertise, str) or not expertise.strip()
        ):
            raise ValueError("expertise 必须是非空字符串")

        if expertise is None:
            rows = self.database.connection.execute(
                """
                SELECT * FROM agent_profiles
                WHERE is_enabled = 1
                ORDER BY created_at ASC, id ASC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        else:
            rows = self.database.connection.execute(
                """
                SELECT * FROM agent_profiles
                WHERE is_enabled = 1
                  AND EXISTS (
                      SELECT 1
                      FROM json_each(agent_profiles.expertise_json)
                      WHERE json_each.value = ?
                  )
                ORDER BY created_at ASC, id ASC
                LIMIT ? OFFSET ?
                """,
                (expertise, limit, offset),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def save(self, profile: AgentProfile) -> AgentProfile:
        """新增或更新 AgentProfile，并返回带时间戳的对象。

        Args:
            profile: 待保存的 AgentProfile。

        Returns:
            保存后的 AgentProfile。

        Raises:
            StorageConflictError: LLM 外键不存在或其他数据库约束冲突时抛出。
        """
        current = self.get(profile.id)
        now = _utc_now()
        created_at = profile.created_at or (current.created_at if current else now)
        updated_profile = replace(
            profile,
            created_at=created_at,
            updated_at=now,
        )

        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO agent_profiles (
                        id, name, description, personality, expertise_json,
                        llm_profile_id, tools_json, is_enabled, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        description = excluded.description,
                        personality = excluded.personality,
                        expertise_json = excluded.expertise_json,
                        llm_profile_id = excluded.llm_profile_id,
                        tools_json = excluded.tools_json,
                        is_enabled = excluded.is_enabled,
                        updated_at = excluded.updated_at
                    """,
                    (
                        updated_profile.id,
                        updated_profile.name,
                        updated_profile.description,
                        updated_profile.personality,
                        json.dumps(
                            updated_profile.expertise,
                            ensure_ascii=False,
                        ),
                        updated_profile.llm_profile_id,
                        json.dumps(
                            updated_profile.tools,
                            ensure_ascii=False,
                        ),
                        int(updated_profile.is_enabled),
                        created_at,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise StorageConflictError(
                f"AgentProfile 保存冲突: {updated_profile.id}"
            ) from error
        return updated_profile

    def delete(self, agent_id: str) -> bool:
        """删除 AgentProfile。

        Args:
            agent_id: 待删除的 Agent ID。

        Returns:
            记录存在并成功删除时返回 True，否则返回 False。

        Raises:
            StorageConflictError: Agent 仍被权限或会话记录引用时抛出。
        """
        validate_id("agent", agent_id)
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute(
                    "DELETE FROM agent_profiles WHERE id = ?",
                    (agent_id,),
                )
        except sqlite3.IntegrityError as error:
            raise StorageConflictError(
                f"AgentProfile 仍被其他数据引用，不能删除: {agent_id}"
            ) from error
        return cursor.rowcount > 0

    @staticmethod
    def _validate_page(limit: int, offset: int) -> None:
        """验证分页参数。"""
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit 必须是正整数")
        if not isinstance(offset, int) or offset < 0:
            raise ValueError("offset 必须是非负整数")

    @staticmethod
    def _from_row(row: sqlite3.Row) -> AgentProfile:
        """将数据库行严格转换为 AgentProfile。"""
        try:
            expertise = json.loads(row["expertise_json"])
            tools = json.loads(row["tools_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise StorageFormatError("AgentProfile JSON 字段不是有效 JSON") from error
        if not isinstance(expertise, list) or not isinstance(tools, list):
            raise StorageFormatError("AgentProfile JSON 字段必须编码为数组")
        try:
            return AgentProfile(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                personality=row["personality"],
                expertise=expertise,
                llm_profile_id=row["llm_profile_id"],
                tools=tools,
                is_enabled=bool(row["is_enabled"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        except (TypeError, ValueError) as error:
            raise StorageFormatError("AgentProfile 数据不符合领域约束") from error


def _utc_now() -> str:
    """生成统一的 UTC ISO 时间字符串。"""
    return datetime.now(timezone.utc).isoformat()
