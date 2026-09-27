import shutil
from pathlib import Path

import pytest

from skills.catalog import SkillCatalog
from skills.parser import parse_skill_file
from skills.resources import SkillResourceError, read_resource, resolve_resource
from skills.types import SkillStatus


FIXTURES = Path(__file__).parents[1] / "fixtures" / "skills"


def test_parser_reads_frontmatter_body_unknown_metadata_and_allowed_tools():
    definition = parse_skill_file(FIXTURES / "valid-skill" / "SKILL.md")
    assert definition.status is SkillStatus.AVAILABLE
    assert definition.name == "valid-skill"
    assert definition.description == "A valid test skill."
    assert definition.allowed_tools == ("read", "Bash")
    assert definition.metadata == {"owner": "tests", "custom-setting": "keep-me"}
    assert "Use this instruction" in definition.instructions


def test_parser_marks_invalid_frontmatter_without_breaking_call():
    definition = parse_skill_file(FIXTURES / "invalid-skill" / "SKILL.md")
    assert definition.status is SkillStatus.INVALID
    assert definition.validation_error


def test_catalog_only_scans_direct_non_symlink_skill_directories(tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    shutil.copytree(FIXTURES / "valid-skill", root / "valid-skill")
    (root / ".claude").mkdir()
    (root / ".claude" / "SKILL.md").write_text("ignored", encoding="utf-8")
    (root / "nested").mkdir()
    (root / "nested" / "child").mkdir(parents=True)
    catalog = SkillCatalog(root)
    discovered = catalog.list_discovered()
    assert [(item.definition.name, item.definition.status) for item in discovered] == [
        ("nested", SkillStatus.INVALID),
        ("valid-skill", SkillStatus.AVAILABLE),
    ]


def test_catalog_digest_changes_with_content_but_not_file_order(tmp_path):
    root = tmp_path / "skill"
    root.mkdir()
    (root / "SKILL.md").write_text("content", encoding="utf-8")
    first = SkillCatalog.digest(root)
    (root / "z.txt").write_text("z", encoding="utf-8")
    (root / "a.txt").write_text("a", encoding="utf-8")
    second = SkillCatalog.digest(root)
    assert first != second
    (root / "a.txt").unlink()
    (root / "z.txt").unlink()
    assert SkillCatalog.digest(root) == first


def test_resources_reject_escape_and_read_in_root(tmp_path):
    root = tmp_path / "skill"
    root.mkdir()
    (root / "reference.txt").write_text("hello", encoding="utf-8")
    assert read_resource(root, "reference.txt") == "hello"
    with pytest.raises(SkillResourceError):
        resolve_resource(root, "../secret")
    with pytest.raises(SkillResourceError):
        resolve_resource(root, str(tmp_path / "secret"))


def test_missing_skill_is_explicit(tmp_path):
    definition = SkillCatalog(tmp_path / "skills").load("missing")
    assert definition.status is SkillStatus.MISSING
