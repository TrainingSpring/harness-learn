"""Skill 索引和 Agent-Skill 关联的 SQLite 仓储。"""

import json
import sqlite3
from datetime import datetime, timezone

from ..database import StateDatabase
from ..errors import StorageConflictError, StorageFormatError
from ..ids import validate_id
from ..types import SkillProfile


class SkillRepository:
    """只负责 Skill 快照和关联 SQL，不扫描文件系统。"""

    def __init__(self, database: StateDatabase) -> None:
        self.database = database

    def get(self, skill_id: str) -> SkillProfile | None:
        validate_id("skill", skill_id)
        row = self.database.connection.execute(
            "SELECT * FROM skills WHERE id = ?", (skill_id,)
        ).fetchone()
        return None if row is None else self._from_row(row)

    def get_by_name(self, name: str) -> SkillProfile | None:
        row = self.database.connection.execute(
            "SELECT * FROM skills WHERE name = ?", (name,)
        ).fetchone()
        return None if row is None else self._from_row(row)

    def list_all(self, status: str | None = None) -> list[SkillProfile]:
        if status is None:
            rows = self.database.connection.execute(
                "SELECT * FROM skills ORDER BY name ASC, id ASC"
            ).fetchall()
        else:
            rows = self.database.connection.execute(
                "SELECT * FROM skills WHERE status = ? ORDER BY name ASC, id ASC",
                (status,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def upsert(self, skill: SkillProfile) -> SkillProfile:
        now = _utc_now()
        current = self.get(skill.id)
        discovered_at = skill.discovered_at or (current.discovered_at if current else now)
        updated_at = skill.updated_at or now
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO skills (
                        id, name, description, root_path, instructions, license,
                        compatibility, metadata_json, allowed_tools_json,
                        content_digest, status, validation_error, discovered_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name, description = excluded.description,
                        root_path = excluded.root_path, instructions = excluded.instructions,
                        license = excluded.license, compatibility = excluded.compatibility,
                        metadata_json = excluded.metadata_json,
                        allowed_tools_json = excluded.allowed_tools_json,
                        content_digest = excluded.content_digest, status = excluded.status,
                        validation_error = excluded.validation_error,
                        updated_at = excluded.updated_at
                    """,
                    (skill.id, skill.name, skill.description, skill.root_path,
                     skill.instructions, skill.license, skill.compatibility,
                     json.dumps(skill.metadata, ensure_ascii=False, sort_keys=True),
                     json.dumps(skill.allowed_tools, ensure_ascii=False),
                     skill.content_digest, skill.status, skill.validation_error,
                     discovered_at, updated_at),
                )
        except sqlite3.IntegrityError as error:
            raise StorageConflictError(f"Skill 保存冲突: {skill.name}") from error
        return SkillProfile(
            **{**skill.__dict__, "discovered_at": discovered_at, "updated_at": updated_at}
        )

    def list_for_agent(self, agent_id: str) -> list[SkillProfile]:
        validate_id("agent", agent_id)
        rows = self.database.connection.execute(
            """
            SELECT skills.* FROM skills
            JOIN agent_skills ON agent_skills.skill_id = skills.id
            WHERE agent_skills.agent_id = ?
            ORDER BY agent_skills.position ASC
            """, (agent_id,),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    def replace_agent_skills(self, agent_id: str, skill_ids: list[str]) -> None:
        validate_id("agent", agent_id)
        if len(skill_ids) != len(set(skill_ids)):
            raise ValueError("Agent 不能重复关联同一个 Skill")
        for skill_id in skill_ids:
            validate_id("skill", skill_id)
        now = _utc_now()
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM agent_skills WHERE agent_id = ?", (agent_id,))
            connection.executemany(
                "INSERT INTO agent_skills (agent_id, skill_id, position, created_at) VALUES (?, ?, ?, ?)",
                [(agent_id, skill_id, index, now) for index, skill_id in enumerate(skill_ids)],
            )

    def count_agents(self, skill_id: str) -> int:
        validate_id("skill", skill_id)
        return self.database.connection.execute(
            "SELECT COUNT(*) FROM agent_skills WHERE skill_id = ?", (skill_id,)
        ).fetchone()[0]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> SkillProfile:
        try:
            metadata = json.loads(row["metadata_json"])
            allowed_tools = json.loads(row["allowed_tools_json"])
        except (TypeError, json.JSONDecodeError) as error:
            raise StorageFormatError("Skill JSON 字段格式无效") from error
        try:
            return SkillProfile(
                id=row["id"], name=row["name"], description=row["description"],
                root_path=row["root_path"], instructions=row["instructions"],
                license=row["license"], compatibility=row["compatibility"],
                metadata=metadata, allowed_tools=allowed_tools,
                content_digest=row["content_digest"], status=row["status"],
                validation_error=row["validation_error"],
                discovered_at=row["discovered_at"], updated_at=row["updated_at"],
            )
        except (TypeError, ValueError) as error:
            raise StorageFormatError("Skill 数据不符合领域约束") from error


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
