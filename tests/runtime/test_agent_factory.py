"""AgentFactory 的 storage 到运行时映射测试。"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from context.context import Context  # noqa: E402
from permission.PermissionManager import PermissionManager  # noqa: E402
from permission.types import PermissionMode  # noqa: E402
from runtime.agent import Agent  # noqa: E402
from runtime.agent_factory import AgentFactory  # noqa: E402
from session.ExecutionContext import ExecutionContext  # noqa: E402
from storage.database import StateDatabase  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.repositories.skill import SkillRepository  # noqa: E402
from storage.types import AgentProfile, LLMProfile, SkillProfile  # noqa: E402


class SummarizerLLM:
    def __init__(self) -> None:
        self.system_prompt = ""


class AgentFactoryTests(unittest.TestCase):
    """验证持久化配置被显式映射为完整 Agent。"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = StateDatabase(self.temp_dir.name)
        self.database.initialize()
        LLMProfileRepository(self.database).save(
            LLMProfile(
                id="llm_7KQ2M8P4XZ",
                name="代码模型",
                protocol="responses",
                base_url="https://api.openai.com/v1",
                model="gpt-5",
                api_key="sk-test-key",
            )
        )
        SkillRepository(self.database).upsert(
            SkillProfile(
                id="skill_REVIEW0001",
                name="review",
                description="Review code",
                root_path="/skills/review",
                instructions="Review the code carefully.",
                license=None,
                compatibility=None,
                metadata={},
                allowed_tools=["read"],
                content_digest="digest-review",
                status="AVAILABLE",
                validation_error=None,
            )
        )
        AgentProfileRepository(self.database).save(
            AgentProfile(
                id="agent_1V3ASAXQ2A",
                name="代码专家",
                description="负责实现代码功能",
                personality="务实",
                expertise=["Python"],
                llm_profile_id="llm_7KQ2M8P4XZ",
                tools=["read", "write"],
                skill_ids=["skill_REVIEW0001"],
            )
        )

    def tearDown(self):
        self.database.close()
        self.temp_dir.cleanup()

    def _session_dependencies(self):
        session_id = "session_TEST01"
        context = Context(SummarizerLLM(), session_id=session_id)
        execution_context = ExecutionContext("/workspace", "agent_1V3ASAXQ2A", session_id)
        permission = PermissionManager(
            mode=PermissionMode.BUILD,
            session_id=session_id,
            project_path=execution_context.project_path,
        )
        return context, execution_context, permission

    def test_load_maps_storage_fields_into_a_complete_agent(self):
        context, execution_context, permission = self._session_dependencies()
        agent = AgentFactory(self.database).load(
            "agent_1V3ASAXQ2A",
            context=context,
            execution_context=execution_context,
            permission=permission,
            permission_mode="build",
        )

        self.assertIsInstance(agent, Agent)
        self.assertEqual(agent.name, "代码专家")
        self.assertEqual(agent.expertise, ("Python",))
        self.assertEqual(agent.llm_config.model, "gpt-5")
        self.assertEqual(
            tuple(tool.schema["name"] for tool in agent.tool_definitions),
            ("read", "write"),
        )
        self.assertIs(agent.context, context)
        self.assertIs(agent.execution_context, execution_context)
        self.assertIs(agent.permission, permission)
        self.assertFalse(hasattr(agent, "profile"))
        self.assertEqual([skill.id for skill in agent.skills], ["skill_REVIEW0001"])
        self.assertEqual(agent.skills[0].instructions, "Review the code carefully.")

    def test_load_llm_config_only_exposes_connection_configuration(self):
        config = AgentFactory(self.database).load_llm_config("agent_1V3ASAXQ2A")

        self.assertEqual(config.base_url, "https://api.openai.com/v1")
        self.assertEqual(config.model, "gpt-5")
        self.assertEqual(config.api_key, "sk-test-key")
        self.assertFalse(hasattr(config, "instructions"))

    def test_load_raises_for_unknown_agent(self):
        context, execution_context, permission = self._session_dependencies()
        with self.assertRaises(ValueError):
            AgentFactory(self.database).load(
                "agent_8LRT3N5QYB",
                context=context,
                execution_context=execution_context,
                permission=permission,
                permission_mode="plan",
            )


if __name__ == "__main__":
    unittest.main()
