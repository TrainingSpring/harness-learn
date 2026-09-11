"""LLMProfile 的 SQLite 仓储。"""

import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone

from ..database import StateDatabase
from ..errors import StorageConflictError, StorageFormatError
from ..ids import validate_id
from ..types import LLMProfile


class LLMProfileRepository:
    """负责 LLMProfile 与 llm_profiles 表之间的转换。

    Attributes:
        database: 已初始化的状态数据库；仓储不负责创建数据库。

    仓储只处理保存、查询和删除，不解析 credential_ref，也不会接触实际 API
    Key。凭据解析属于运行时的 CredentialResolver。
    """

    def __init__(self, database: StateDatabase) -> None:
        """创建 LLMProfile 仓储。

        Args:
            database: 已调用 initialize() 的状态数据库。
        """
        self.database = database

    def get(self, profile_id: str) -> LLMProfile | None:
        """根据 ID 读取一套 LLM 配置。

        Args:
            profile_id: 带 llm_ 前缀的 LLMProfile ID。

        Returns:
            找到时返回 LLMProfile，找不到时返回 None。
        """
        validate_id("llm", profile_id)
        row = self.database.connection.execute(
            "SELECT * FROM llm_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        return None if row is None else self._from_row(row)

    def get_by_name(self, name: str) -> LLMProfile | None:
        """根据用户可读名称读取 LLM 配置。"""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("LLMProfile 名称必须是非空字符串")
        row = self.database.connection.execute(
            "SELECT * FROM llm_profiles WHERE name = ?",
            (name,),
        ).fetchone()
        return None if row is None else self._from_row(row)

    def list_all(self, limit: int, offset: int) -> list[LLMProfile]:
        """按创建顺序分页读取 LLM 配置。"""
        self._validate_page(limit, offset)
        rows = self.database.connection.execute(
            """
            SELECT * FROM llm_profiles
            ORDER BY created_at ASC, id ASC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    def save(self, profile: LLMProfile) -> LLMProfile:
        """新增或更新一套 LLM 配置，并返回带时间戳的对象。

        Args:
            profile: 待保存的 LLMProfile。

        Returns:
            保存后的 LLMProfile。已存在记录的 ID 不会改变。

        Raises:
            StorageConflictError: 名称与另一条配置重复时抛出。
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
                    INSERT INTO llm_profiles (
                        id, name, provider, base_url, model, credential_ref,
                        options_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        provider = excluded.provider,
                        base_url = excluded.base_url,
                        model = excluded.model,
                        credential_ref = excluded.credential_ref,
                        options_json = excluded.options_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        updated_profile.id,
                        updated_profile.name,
                        updated_profile.provider,
                        updated_profile.base_url,
                        updated_profile.model,
                        updated_profile.credential_ref,
                        json.dumps(
                            updated_profile.options,
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        created_at,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise StorageConflictError(
                f"LLMProfile 保存冲突: {updated_profile.name}"
            ) from error
        return updated_profile

    def delete(self, profile_id: str) -> bool:
        """删除 LLM 配置。

        Args:
            profile_id: 待删除的 LLMProfile ID。

        Returns:
            记录存在并成功删除时返回 True，否则返回 False。

        Raises:
            StorageConflictError: 仍被 AgentProfile 引用时抛出。
        """
        validate_id("llm", profile_id)
        try:
            with self.database.transaction() as connection:
                cursor = connection.execute(
                    "DELETE FROM llm_profiles WHERE id = ?",
                    (profile_id,),
                )
        except sqlite3.IntegrityError as error:
            raise StorageConflictError(
                f"LLMProfile 仍被 Agent 使用，不能删除: {profile_id}"
            ) from error
        return cursor.rowcount > 0

    @staticmethod
    def _validate_page(limit: int, offset: int) -> None:
        """验证分页参数，避免将无意义值传给 SQL。"""
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit 必须是正整数")
        if not isinstance(offset, int) or offset < 0:
            raise ValueError("offset 必须是非负整数")

    @staticmethod
    def _from_row(row: sqlite3.Row) -> LLMProfile:
        """将数据库行严格转换为 LLMProfile。"""
        try:
            options = json.loads(row["options_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise StorageFormatError("LLMProfile.options_json 不是有效 JSON") from error
        if not isinstance(options, dict):
            raise StorageFormatError("LLMProfile.options_json 必须编码为对象")
        try:
            return LLMProfile(
                id=row["id"],
                name=row["name"],
                provider=row["provider"],
                base_url=row["base_url"],
                model=row["model"],
                credential_ref=row["credential_ref"],
                options=options,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        except (TypeError, ValueError) as error:
            raise StorageFormatError("LLMProfile 数据不符合领域约束") from error


def _utc_now() -> str:
    """生成统一的 UTC ISO 时间字符串。"""
    return datetime.now(timezone.utc).isoformat()
