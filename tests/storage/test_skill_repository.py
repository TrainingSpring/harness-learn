import pytest

from storage.errors import StorageConflictError
from storage.repositories.skill import SkillRepository
from storage.types import SkillProfile


def make_skill(skill_id="skill_REVIEW0001", name="review"):
    return SkillProfile(
        id=skill_id.replace("skill_review0001", "skill_REVIEW0001").replace("skill_docs0001", "skill_DOCS0001"), name=name, description="Review code", root_path=f"/skills/{name}",
        instructions="# Review", license=None, compatibility=None, metadata={"owner": "test"},
        allowed_tools=["read"], content_digest="digest-1", status="AVAILABLE",
        validation_error=None,
    )


def test_skill_repository_round_trips_json_and_agent_order(database):
    repository = SkillRepository(database)
    first = repository.upsert(make_skill())
    second = repository.upsert(make_skill("skill_DOCS000001", "docs"))
    repository.replace_agent_skills("agent_TESTAGENT1", [second.id, first.id])
    assert [item.id for item in repository.list_for_agent("agent_TESTAGENT1")] == [second.id, first.id]
    assert repository.count_agents(first.id) == 1
    assert repository.get(first.id) == first


def test_skill_repository_rejects_duplicate_association(database):
    repository = SkillRepository(database)
    repository.upsert(make_skill())
    with pytest.raises(ValueError):
        repository.replace_agent_skills("agent_TESTAGENT1", ["skill_REVIEW0001", "skill_REVIEW0001"])


def test_skill_repository_prevents_deleting_in_use_via_foreign_key(database):
    repository = SkillRepository(database)
    repository.upsert(make_skill())
    repository.replace_agent_skills("agent_TESTAGENT1", ["skill_REVIEW0001"])
    with pytest.raises(Exception):
        database.connection.execute("DELETE FROM skills WHERE id = ?", ("skill_REVIEW0001",))
