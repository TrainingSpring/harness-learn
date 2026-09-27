"""固定 Skill 根目录的发现和内容摘要。"""

import hashlib
from pathlib import Path
from .parser import parse_skill_file
from .types import DiscoveredSkill, SkillDefinition, SkillStatus


class SkillCatalog:
    """只扫描固定根目录直接子目录，不负责数据库持久化。"""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or (Path.home() / ".harness-learn" / "skills")).expanduser().resolve()

    def list_discovered(self) -> list[DiscoveredSkill]:
        """发现直接子目录；单个坏目录不会阻断其他目录。"""
        if not self.root.exists():
            return []
        results: list[DiscoveredSkill] = []
        for child in sorted(self.root.iterdir(), key=lambda item: item.name):
            if not child.is_dir() or child.is_symlink() or child.name.startswith("."):
                continue
            skill_file = child / "SKILL.md"
            digest = self.digest(child)
            definition = parse_skill_file(skill_file, digest=digest)
            results.append(DiscoveredSkill(str(child), digest, definition))
        return results

    def load(self, name: str) -> SkillDefinition:
        """按目录名读取单个 Skill。"""
        if not isinstance(name, str) or not name or Path(name).name != name:
            raise ValueError("Skill 名称无效")
        path = self.root / name
        if not path.is_dir() or path.is_symlink():
            return SkillDefinition(
                id=f"skill_{name}", name=name, description="", root_path=str(path),
                status=SkillStatus.MISSING, validation_error="Skill 目录不存在",
            )
        digest = self.digest(path)
        return parse_skill_file(path / "SKILL.md", digest=digest)

    @staticmethod
    def digest(root: Path) -> str:
        """按稳定相对路径、文件类型和内容计算目录 SHA-256。"""
        digest = hashlib.sha256()
        if not root.exists():
            return digest.hexdigest()
        for path in sorted(item for item in root.rglob("*") if not item.is_symlink()):
            relative = path.relative_to(root).as_posix().encode("utf-8")
            digest.update(relative + b"\0")
            digest.update(b"d\0" if path.is_dir() else b"f\0")
            if path.is_file():
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
            digest.update(b"\0")
        return digest.hexdigest()
