"""设置 API 的公开字段、敏感信息和模型发现测试。"""

from unittest.mock import AsyncMock

from storage.types import LLMProfile


def test_list_llm_profiles_hides_api_key(client) -> None:
    """浏览器只知道 API Key 是否配置，不能获得真实值。"""
    response = client.get("/api/settings/llm-profiles")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item == {
        "id": "llm_TESTLLM001",
        "name": "本地 GPT",
        "provider": "openai",
        "baseUrl": "https://api.openai.com/v1",
        "model": "gpt-5",
        "hasApiKey": True,
        "options": {"temperature": 0.2},
    }
    assert "sk-test-key" not in response.text
    assert "apiKey" not in response.text


def test_get_llm_profile_api_key_returns_saved_key_for_editing(client) -> None:
    """编辑接口返回指定配置的实际 API Key，供本地 Web UI 回显。"""
    response = client.get("/api/settings/llm-profiles/llm_TESTLLM001/api-key")

    assert response.status_code == 200
    assert response.json() == {"apiKey": "sk-test-key"}


def test_get_llm_profile_api_key_rejects_unknown_profile(client) -> None:
    """读取不存在配置的 API Key 时仍保持稳定的 404 契约。"""
    response = client.get("/api/settings/llm-profiles/llm_UNKNOWN000/api-key")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "LLM_PROFILE_NOT_FOUND"


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


def test_create_llm_profile_generates_id_and_hides_api_key(client) -> None:
    """新增 LLM 配置后返回摘要，不把 API Key 暴露给浏览器。"""
    response = client.post(
        "/api/settings/llm-profiles",
        json={
            "name": "备用 GPT",
            "provider": "openai",
            "baseUrl": "https://api.example.com/v1",
            "model": "gpt-5-mini",
            "apiKey": "sk-backup-key",
            "options": {"temperature": 0.1},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["id"].startswith("llm_")
    assert len(payload["id"]) == len("llm_XXXXXXXXXX")
    assert payload["name"] == "备用 GPT"
    assert payload["hasApiKey"] is True
    assert payload["options"] == {"temperature": 0.1}
    assert "apiKey" not in payload
    assert "sk-backup-key" not in response.text


def test_create_llm_profile_rejects_duplicate_name(client) -> None:
    """LLM 配置名称冲突时返回统一的 409 错误。"""
    response = client.post(
        "/api/settings/llm-profiles",
        json={
            "name": "本地 GPT",
            "provider": "openai",
            "model": "gpt-5",
            "apiKey": "sk-other-key",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LLM_PROFILE_CONFLICT"


def test_update_llm_profile_preserves_api_key_when_omitted(client) -> None:
    """普通编辑不能因为前端看不到 API Key 而清空原密钥。"""
    response = client.patch(
        "/api/settings/llm-profiles/llm_TESTLLM001",
        json={
            "name": "更新后的 GPT",
            "provider": "openai",
            "baseUrl": "https://api.example.com/v1",
            "model": "gpt-5-mini",
            "options": {"temperature": 0.1},
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == "llm_TESTLLM001"
    assert response.json()["name"] == "更新后的 GPT"
    assert response.json()["hasApiKey"] is True
    assert "apiKey" not in response.text


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
            "apiKey": "sk-delete-key",
            "options": {},
        },
    )
    profile_id = created.json()["id"]

    response = client.delete(f"/api/settings/llm-profiles/{profile_id}")

    assert response.status_code == 204
    listed_ids = [item["id"] for item in client.get("/api/settings/llm-profiles").json()["items"]]
    assert profile_id not in listed_ids


def test_discover_draft_models_returns_only_model_ids(client, monkeypatch) -> None:
    """草稿连接可用表单中的 API Key 拉取模型，响应不会回显密钥。"""
    discover = AsyncMock(return_value=["gpt-5", "gpt-5-mini"])
    monkeypatch.setattr("app.api.settings.discover_models", discover)

    response = client.post(
        "/api/settings/llm-profiles/models",
        json={
            "provider": "openai",
            "baseUrl": "https://api.example.com/v1",
            "apiKey": "sk-draft-key",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"models": ["gpt-5", "gpt-5-mini"]}
    assert "sk-draft-key" not in response.text
    discover.assert_awaited_once_with("openai", "https://api.example.com/v1", "sk-draft-key")


def test_discover_saved_models_rejects_missing_api_key(client, monkeypatch) -> None:
    """已迁移但尚未补填密钥的配置不能请求服务商。"""
    current = LLMProfile(
        id="llm_TESTLLM001",
        name="无密钥配置",
        provider="openai",
        base_url="https://api.example.com/v1",
        model="gpt-5-mini",
        api_key="",
    )
    monkeypatch.setattr(
        client.app.state.services.llm_profiles,
        "get",
        lambda _profile_id: current,
    )

    response = client.get("/api/settings/llm-profiles/llm_TESTLLM001/models")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "API_KEY_REQUIRED"


def test_delete_llm_profile_returns_not_found_for_unknown_profile(client) -> None:
    """删除不存在的配置时返回稳定的 404 错误。"""
    response = client.delete("/api/settings/llm-profiles/llm_UNKNOWN000")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "LLM_PROFILE_NOT_FOUND"
