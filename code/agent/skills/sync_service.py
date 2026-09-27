"""把固定目录中的 Skill 索引同步到 SQLite。"""

from dataclasses import dataclass
from datetime import datetime, timezone

from storage.repositories.skill import SkillRepository
from storage.types import SkillProfile

from .catalog import SkillCatalog
from .types import SkillStatus


@dataclass(frozen=True)
class SkillSyncResult:
    """一次刷新操作的统计结果。"""

    added: int = 0
    updated: int = 0
    unchanged: int = 0
    missing: int = 0
    invalid: int = 0


class SkillSyncService:
    """协调文件发现和 Skill 索引持久化。"""

    def __init__(self, catalog: SkillCatalog, repository: SkillRepository) -> None:
        self.catalog = catalog
        self.repository = repository

    def refresh(self) -> SkillSyncResult:
        discovered = self.catalog.list_discovered()
        existing = {skill.root_path: skill for skill in self.repository.list_all()}
        seen_paths: set[str] = set()
        counts = {"added": 0, "updated": 0, "unchanged": 0, "missing": 0, "invalid": 0}

        for item in discovered:
            definition = item.definition
            seen_paths.add(item.root_path)
            previous = existing.get(item.root_path)
            if definition.status is SkillStatus.INVALID:
                counts["invalid"] += 1
            if previous is not None and previous.content_digest == item.content_digest:
                counts["unchanged"] += 1
                continue
            skill = SkillProfile(
                id=previous.id if previous else _skill_id(definition.name),
                name=definition.name,
                description=definition.description or definition.name,
                root_path=definition.root_path,
                instructions=definition.instructions,
                license=definition.license,
                compatibility=definition.compatibility,
                metadata=definition.metadata,
                allowed_tools=list(definition.allowed_tools),
                content_digest=item.content_digest,
                status=definition.status.value,
                validation_error=definition.validation_error,
                discovered_at=previous.discovered_at if previous else None,
                updated_at=None,
            )
            self.repository.upsert(skill)
            counts["added" if previous is None else "updated"] += 1

        for skill in existing.values():
            if skill.root_path in seen_paths or skill.status == SkillStatus.MISSING.value:
                continue
            missing = SkillProfile(
                **{**skill.__dict__, "status": SkillStatus.MISSING.value,
                   "validation_error": "Skill 目录不存在", "updated_at": None}
            )
            self.repository.upsert(missing)
            counts["missing"] += 1

        return SkillSyncResult(**counts)


def _skill_id(name: str) -> str:
    """由名称生成稳定且符合数据库 ID 规则的初始 ID。"""
    import hashlib

    suffix = hashlib.sha256(name.encode("utf-8")).hexdigest().upper()[:10]
    return f"skill_{suffix}"
