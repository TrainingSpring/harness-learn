"""Skill 资源路径安全边界；本模块不执行脚本。"""

from pathlib import Path


class SkillResourceError(ValueError):
    """资源路径不属于 Skill 根目录或超过读取限制。"""


def resolve_resource(root: Path, relative_path: str) -> Path:
    """解析 Skill 根目录内的相对资源路径，拒绝穿越和符号链接逃逸。"""
    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SkillResourceError("Skill 资源路径必须是根目录内的相对路径")
    root = root.resolve()
    resolved = (root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise SkillResourceError("Skill 资源路径不能逃逸根目录")
    return resolved


def read_resource(root: Path, relative_path: str, *, max_bytes: int = 256 * 1024) -> str:
    """读取根目录内的 UTF-8 参考资料；脚本不会通过此接口执行。"""
    path = resolve_resource(root, relative_path)
    if not path.is_file():
        raise SkillResourceError("Skill 资源不存在或不是普通文件")
    if path.stat().st_size > max_bytes:
        raise SkillResourceError("Skill 资源超过读取大小限制")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise SkillResourceError("Skill 资源无法读取") from error
