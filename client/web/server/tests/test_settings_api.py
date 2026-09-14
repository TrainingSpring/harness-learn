"""只读设置 API 的公开字段和敏感信息测试。"""


def test_list_llm_profiles_hides_credential_reference(client) -> None:
    """浏览器只知道凭据是否配置，不能获得引用或真实值。"""
    response = client.get("/api/settings/llm-profiles")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item == {
        "id": "llm_TESTLLM001",
        "name": "本地 GPT",
        "provider": "openai",
        "baseUrl": "https://api.openai.com/v1",
        "model": "gpt-5",
        "hasCredential": True,
        "options": {"temperature": 0.2},
    }
    assert "SECRET_TEST_KEY" not in response.text
    assert "credentialRef" not in response.text


def test_list_tools_returns_display_metadata_only(client) -> None:
    """工具接口只公开 schema 和权限动作所需的展示信息。"""
    response = client.get("/api/settings/tools")

    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["name"] for item in items} >= {"read", "write", "edit", "bash"}
    read = next(item for item in items if item["name"] == "read")
    assert read["description"]
    assert read["inputSchema"]["type"] == "object"
    assert read["permissionAction"] == "filesystem.read"
    assert "module" not in read
    assert "permission" not in read


def test_create_llm_profile_generates_id_and_hides_credential_reference(client) -> None:
    """新增 LLM 配置后返回摘要，不把凭据引用暴露给浏览器。"""
    response = client.post(
        "/api/settings/llm-profiles",
        json={
            "name": "备用 GPT",
            "provider": "openai",
            "baseUrl": "https://api.example.com/v1",
            "model": "gpt-5-mini",
            "credentialRef": "env:BACKUP_OPENAI_KEY",
            "options": {"temperature": 0.1},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["id"].startswith("llm_")
    assert len(payload["id"]) == len("llm_XXXXXXXXXX")
    assert payload["name"] == "备用 GPT"
    assert payload["hasCredential"] is True
    assert payload["options"] == {"temperature": 0.1}
    assert "credentialRef" not in payload
    assert "BACKUP_OPENAI_KEY" not in response.text


def test_create_llm_profile_rejects_duplicate_name(client) -> None:
    """LLM 配置名称冲突时返回统一的 409 错误。"""
    response = client.post(
        "/api/settings/llm-profiles",
        json={
            "name": "本地 GPT",
            "provider": "openai",
            "model": "gpt-5",
            "credentialRef": "env:OTHER_KEY",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LLM_PROFILE_CONFLICT"


def test_update_llm_profile_preserves_credential_when_omitted(client) -> None:
    """普通编辑不能因为前端看不到凭据引用而清空原凭据。"""
    response = client.patch(
        "/api/settings/llm-profiles/llm_TESTLLM001",
        json={
            "name": "更新后的 GPT",
            "provider": "openai-compatible",
            "baseUrl": "https://api.example.com/v1",
            "model": "gpt-5-mini",
            "options": {"temperature": 0.1},
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == "llm_TESTLLM001"
    assert response.json()["name"] == "更新后的 GPT"
    assert response.json()["hasCredential"] is True
    assert "credentialRef" not in response.text


def test_update_llm_profile_rejects_unknown_profile(client) -> None:
    """更新不存在的配置时返回稳定的 404 错误。"""
    response = client.patch(
        "/api/settings/llm-profiles/llm_UNKNOWN000",
        json={
            "name": "无效配置",
            "provider": "openai",
            "model": "gpt-5",
            "options": {},
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "LLM_PROFILE_NOT_FOUND"


def test_delete_llm_profile_rejects_profile_used_by_agent(client) -> None:
    """仍被 Agent 引用的配置不能删除，避免破坏运行时引用。"""
    response = client.delete("/api/settings/llm-profiles/llm_TESTLLM001")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "LLM_PROFILE_IN_USE",
            "message": "LLM 配置仍被角色使用，不能删除",
            "details": None,
        }
    }


def test_delete_llm_profile_removes_unused_profile(client) -> None:
    """未被 Agent 引用的 LLM 配置可以被删除。"""
    created = client.post(
        "/api/settings/llm-profiles",
        json={
            "name": "可删除配置",
            "provider": "openai",
            "model": "gpt-5-mini",
            "credentialRef": "env:DELETE_TEST_KEY",
            "options": {},
        },
    )
    profile_id = created.json()["id"]

    response = client.delete(f"/api/settings/llm-profiles/{profile_id}")

    assert response.status_code == 204
    listed_ids = [item["id"] for item in client.get("/api/settings/llm-profiles").json()["items"]]
    assert profile_id not in listed_ids


def test_delete_llm_profile_returns_not_found_for_unknown_profile(client) -> None:
    """删除不存在的配置时返回稳定的 404 错误。"""
    response = client.delete("/api/settings/llm-profiles/llm_UNKNOWN000")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "LLM_PROFILE_NOT_FOUND"
