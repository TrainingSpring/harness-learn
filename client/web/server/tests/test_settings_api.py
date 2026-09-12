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
