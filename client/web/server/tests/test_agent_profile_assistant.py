"""Agent 角色草案生成服务测试。"""

from types import SimpleNamespace

from app.services.agent_profile_assistant import AgentProfileAssistant


class FakeRepository:
    """只提供草案服务所需的 LLM 配置查询假仓储。"""

    def __init__(self, profile):
        self.profile = profile

    def get(self, profile_id):
        return self.profile if self.profile and self.profile.id == profile_id else None


class FakeCredentialResolver:
    """返回固定测试凭据，避免单元测试读取真实环境变量。"""

    def resolve(self, _credential_ref):
        return "test-key"


class FakeLLM:
    """记录请求并返回模拟 Responses API 输出。"""

    def __init__(self, _base_url, _api_key, _model, _system_prompt):
        self.input = None

    def call_responses(self, input):
        self.input = input
        return SimpleNamespace(
            output_text='{"name":"研究助手","description":"研究资料","personality":"严谨","expertise":["Research"]}'
        )


def test_assistant_parses_model_json_into_profile_fields() -> None:
    """服务应解析模型 JSON，并只返回约定的四个字段。"""
    profile = SimpleNamespace(
        id="llm_TESTLLM001",
        base_url="https://api.example.com/v1",
        credential_ref="env:TEST_KEY",
        model="gpt-5",
    )
    assistant = AgentProfileAssistant(
        FakeRepository(profile),
        credential_resolver=FakeCredentialResolver(),
        llm_factory=FakeLLM,
    )

    result = assistant.suggest("帮助团队研究技术资料", "llm_TESTLLM001")

    assert result == {
        "name": "研究助手",
        "description": "研究资料",
        "personality": "严谨",
        "expertise": ["Research"],
    }
