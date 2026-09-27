"""运行时 Skill 指令和资源边界。"""

from collections.abc import Iterable

from .types import SkillDefinition, SkillStatus


class SkillActivationError(ValueError):
    """请求激活了未分配或不可用的 Skill。"""


class SkillSet:
    """当前 Agent 的只读 Skill 集合，不负责注册工具或执行脚本。"""

    def __init__(self, skills: Iterable[SkillDefinition] = ()) -> None:
        self._skills = tuple(skills)
        self._by_id = {skill.id: skill for skill in self._skills}
        if len(self._by_id) != len(self._skills):
            raise ValueError("Skill ID 不能重复")

    @property
    def definitions(self) -> tuple[SkillDefinition, ...]:
        return self._skills

    def metadata_prompt(self) -> str:
        """生成始终可见的 Skill 名称和描述，不包含 Skill 正文。"""
        available = [skill for skill in self._skills if skill.status is SkillStatus.AVAILABLE]
        if not available:
            return ""
        lines = ["已配置的 Skills（仅在明确激活时加载其正文）："]
        lines.extend(f"- {skill.name}: {skill.description}" for skill in available)
        return "\n".join(lines)

    def instructions_for(self, skill_ids: Iterable[str] = ()) -> str:
        """返回本轮激活 Skill 的正文，拒绝未配置或不可用的 Skill。"""
        selected = list(dict.fromkeys(skill_ids))
        parts: list[str] = []
        for skill_id in selected:
            skill = self._by_id.get(skill_id)
            if skill is None or skill.status is not SkillStatus.AVAILABLE:
                raise SkillActivationError(f"Skill 未分配或不可用: {skill_id}")
            if skill.instructions.strip():
                parts.append(f"## Skill: {skill.name}\n{skill.instructions.strip()}")
        return "\n\n".join(parts)
