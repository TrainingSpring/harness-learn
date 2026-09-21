"""稳定 Agent 身份与跨 Session 复用测试。"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from runtime.agent import Agent  # noqa: E402
from runtime.agent_factory import AgentFactory  # noqa: E402
from session.session_service import SessionService  # noqa: E402
from storage.database import StateDatabase  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.types import AgentProfile, LLMProfile  # noqa: E402
from tools.types import Tool  # noqa: E402


class AgentTests(unittest.TestCase):
    """验证 AgentFactory 只加载可跨会话复用的稳定 Agent。"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = StateDatabase(self.temp_dir.name)
        self.database.initialize()
        LLMProfileRepository(self.database).save(
            LLMProfile(
                id="llm_7KQ2M8P4XZ",
                name="代码模型",
                provider="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-5",
                api_key="sk-test-key",
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
                tools=["read"],
                permission_mode="BUILD",
            )
        )

    def tearDown(self):
        self.database.close()
        self.temp_dir.cleanup()

    def test_factory_load_returns_reusable_agent_without_session_state(self):
        """稳定 Agent 不应携带 session、context 或工具执行环境。"""
        agent = AgentFactory(self.database).load("agent_1V3ASAXQ2A")

        self.assertIsInstance(agent, Agent)
        self.assertEqual(agent.agent_id, "agent_1V3ASAXQ2A")
        self.assertEqual(agent.profile.id, agent.agent_id)
        self.assertEqual(
            tuple(tool.schema["name"] for tool in agent.tool_definitions),
            ("read",),
        )
        self.assertFalse(hasattr(agent, "session_id"))
        self.assertFalse(hasattr(agent, "context"))

    def test_one_agent_creates_distinct_session_execution_contexts(self):
        """同一稳定 Agent 被 SessionService 打开时应获得隔离执行环境。"""
        sessions = SessionService(self.database)
        first_execution = sessions.create_direct_session("agent_1V3ASAXQ2A")
        second_execution = sessions.create_direct_session("agent_1V3ASAXQ2A")
        first = first_execution.runtimes["agent_1V3ASAXQ2A"]
        second = second_execution.runtimes["agent_1V3ASAXQ2A"]

        self.assertIsNot(first, second)
        self.assertEqual(first.ctx.agent_id, second.ctx.agent_id)
        self.assertNotEqual(first.ctx.session_id, second.ctx.session_id)
        self.assertIsNot(first.tools, second.tools)
        self.assertFalse(hasattr(first, "context"))
        self.assertFalse(hasattr(second, "context"))

    def test_agent_contains_frozen_tool_definitions(self):
        """Agent 应冻结已验证的工具定义，避免每个 Session 重复发现模块。"""
        agent = AgentFactory(self.database).load("agent_1V3ASAXQ2A")

        self.assertEqual(len(agent.tool_definitions), 1)
        self.assertIsInstance(agent.tool_definitions[0], Tool)

if __name__ == "__main__":
    unittest.main()
