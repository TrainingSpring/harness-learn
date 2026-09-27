"""安全解析 Skill.md 的 YAML frontmatter 和 Markdown 正文。"""

from pathlib import Path
import re
from typing import Any

import yaml

from .types import SkillDefinition, SkillStatus

_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_MAX_FILE_BYTES = 1024 * 1024


def parse_skill_file(path: Path, *, skill_id: str | None = None, digest: str = "") -> SkillDefinition:
    """解析一个 ``SKILL.md``，任何格式错误都转为 INVALID 定义。"""
    root = path.parent.resolve()
    identifier = skill_id or f"skill_{root.name}"
    try:
        if not path.is_file():
            raise ValueError("SKILL.md 不存在或不是普通文件")
        if path.stat().st_size > _MAX_FILE_BYTES:
            raise ValueError("SKILL.md 超过允许的大小限制")
        raw = path.read_text(encoding="utf-8")
        frontmatter, instructions = _split_frontmatter(raw)
        values = yaml.safe_load(frontmatter)
        if not isinstance(values, dict):
            raise ValueError("frontmatter 必须是 YAML 对象")
        name = _required_text(values, "name")
        description = _required_text(values, "description")
        if not _NAME_PATTERN.fullmatch(name):
            raise ValueError("name 必须使用小写字母、数字和连字符，长度不超过 64")
        return SkillDefinition(
            id=identifier,
            name=name,
            description=description,
            root_path=str(root),
            instructions=instructions,
            license=_optional_text(values, "license"),
            compatibility=_optional_text(values, "compatibility"),
            metadata=_metadata(values),
            allowed_tools=_allowed_tools(values.get("allowed-tools")),
            content_digest=digest,
        )
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as error:
        return SkillDefinition(
            id=identifier,
            name=root.name,
            description="",
            root_path=str(root),
            content_digest=digest,
            status=SkillStatus.INVALID,
            validation_error=str(error),
        )


def _split_frontmatter(raw: str) -> tuple[str, str]:
    if not raw.startswith("---"):
        raise ValueError("SKILL.md 必须以 frontmatter 开始")
    lines = raw.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("frontmatter 起始标记无效")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1:]).lstrip("\r\n")
    raise ValueError("frontmatter 缺少结束标记")


def _required_text(values: dict[str, Any], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} 必须是非空字符串")
    return value.strip()


def _optional_text(values: dict[str, Any], key: str) -> str | None:
    value = values.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} 必须是字符串")
    return value.strip() or None


def _allowed_tools(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = value.split()
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        values = value
    else:
        raise ValueError("allowed-tools 必须是字符串或字符串列表")
    return tuple(dict.fromkeys(item.strip() for item in values if item.strip()))


def _metadata(values: dict[str, Any]) -> dict[str, Any]:
    metadata = values.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("metadata 必须是 YAML 对象")
    result = dict(metadata or {})
    for key, value in values.items():
        if key not in {"name", "description", "license", "compatibility", "allowed-tools", "metadata"}:
            result[key] = value
    return result
