"""Skill 的协议无关领域类型。"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SkillStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    INVALID = "INVALID"
    MISSING = "MISSING"


@dataclass(frozen=True)
class SkillDefinition:
    """从一个 Skill 目录解析出的完整索引快照。"""

    id: str
    name: str
    description: str
    root_path: str
    instructions: str = ""
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    allowed_tools: tuple[str, ...] = ()
    content_digest: str = ""
    status: SkillStatus = SkillStatus.AVAILABLE
    validation_error: str | None = None


@dataclass(frozen=True)
class DiscoveredSkill:
    """目录扫描阶段发现的 Skill 结果。"""

    root_path: str
    content_digest: str
    definition: SkillDefinition
