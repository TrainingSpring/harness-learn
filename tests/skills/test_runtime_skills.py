import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from skills.skills import SkillActivationError, SkillSet
from skills.types import SkillDefinition


def make_skill(skill_id="skill_REVIEW0001", name="review", instructions="Review carefully"):
    return SkillDefinition(
        id=skill_id,
        name=name,
        description="Review source code",
        root_path="/skills/review",
        instructions=instructions,
    )


def test_metadata_contains_name_and_description_but_not_body():
    prompt = SkillSet([make_skill()]).metadata_prompt()
    assert "review" in prompt
    assert "Review source code" in prompt
    assert "Review carefully" not in prompt


def test_activation_returns_only_selected_body():
    skills = SkillSet([make_skill(), make_skill("skill_DOCS000001", "docs", "Write docs")])
    prompt = skills.instructions_for(["skill_DOCS000001"])
    assert "Write docs" in prompt
    assert "Review carefully" not in prompt


def test_activation_rejects_unassigned_skill():
    with pytest.raises(SkillActivationError):
        SkillSet([make_skill()]).instructions_for(["skill_UNKNOWN01"])
