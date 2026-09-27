from pathlib import Path
import shutil

from skills.catalog import SkillCatalog
from skills.sync_service import SkillSyncService
from storage.repositories.skill import SkillRepository


FIXTURES = Path(__file__).parents[1] / "fixtures" / "skills"


def test_refresh_counts_add_unchanged_invalid_missing_and_recovery(database, tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    shutil.copytree(FIXTURES / "valid-skill", root / "valid-skill")
    service = SkillSyncService(SkillCatalog(root), SkillRepository(database))

    first = service.refresh()
    assert (first.added, first.updated, first.unchanged, first.missing, first.invalid) == (1, 0, 0, 0, 0)
    saved = SkillRepository(database).get_by_name("valid-skill")
    assert saved is not None
    first_updated_at = saved.updated_at

    unchanged = service.refresh()
    assert unchanged.unchanged == 1
    assert SkillRepository(database).get(saved.id).updated_at == first_updated_at

    (root / "valid-skill" / "SKILL.md").write_text(
        (root / "valid-skill" / "SKILL.md").read_text(encoding="utf-8") + "\nchanged\n",
        encoding="utf-8",
    )
    changed = service.refresh()
    assert changed.updated == 1

    shutil.rmtree(root / "valid-skill")
    missing = service.refresh()
    assert missing.missing == 1
    assert SkillRepository(database).get(saved.id).status == "MISSING"

    shutil.copytree(FIXTURES / "valid-skill", root / "valid-skill")
    recovered = service.refresh()
    assert recovered.updated == 1
    assert SkillRepository(database).get(saved.id).status == "AVAILABLE"


def test_invalid_skill_is_indexed_without_blocking_valid_skill(database, tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    shutil.copytree(FIXTURES / "valid-skill", root / "valid-skill")
    shutil.copytree(FIXTURES / "invalid-skill", root / "invalid-skill")
    result = SkillSyncService(SkillCatalog(root), SkillRepository(database)).refresh()
    assert result.added == 2
    assert result.invalid == 1
