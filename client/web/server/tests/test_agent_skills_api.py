from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile


def _import_skill(client):
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr("review/SKILL.md", "---\nname: review\ndescription: Review code\n---\nUse review.\n")
    stream.seek(0)
    response = client.post("/api/settings/skills/import", files={"file": ("review.zip", stream, "application/zip")})
    assert response.status_code == 200
    return response.json()["items"][0]["id"]


def test_create_agent_persists_available_skill_ids(client):
    skill_id = _import_skill(client)
    response = client.post("/api/agents", json={"name": "带技能角色", "description": "review", "personality": "", "expertise": [], "llmProfileId": "llm_TESTLLM001", "tools": [], "skillIds": [skill_id], "isEnabled": True})
    assert response.status_code == 201
    assert response.json()["skills"] == [skill_id]


def test_create_agent_rejects_unknown_skill(client):
    response = client.post("/api/agents", json={"name": "错误角色", "description": "bad", "personality": "", "expertise": [], "llmProfileId": "llm_TESTLLM001", "tools": [], "skillIds": ["skill_UNKNOWN01"], "isEnabled": True})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_SKILL"
