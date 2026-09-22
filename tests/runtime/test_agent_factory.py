"""AgentFactory 的稳定 Agent 配置加载测试。"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from runtime.agent import Agent  # noqa: E402
from runtime.agent_factory import AgentFactory  # noqa: E402
from storage.database import StateDatabase  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.types import AgentProfile, LLMProfile  # noqa: E402


class AgentFactoryTests(unittest.TestCase):
    """验证数据库配置可以加载为稳定 Agent 定义。"""

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
                tools=["read", "write"],
            )
        )

    def tearDown(self):
        self.database.close()
        self.temp_dir.cleanup()

    def test_load_returns_stable_agent(self):
        """Factory 不应在加载 Agent 时创建 Session 执行状态。"""
        agent = AgentFactory(self.database).load("agent_1V3ASAXQ2A")

        self.assertIsInstance(agent, Agent)
        self.assertEqual(agent.agent_id, "agent_1V3ASAXQ2A")
        self.assertFalse(hasattr(agent, "workspace"))
        self.assertEqual(
            tuple(tool.schema["name"] for tool in agent.tool_definitions),
            ("read", "write"),
        )
        self.assertFalse(hasattr(agent, "session_id"))
        self.assertFalse(hasattr(agent, "context"))

    def test_load_raises_for_unknown_agent(self):
        """不存在的 Agent 配置不能创建默认定义。"""
        with self.assertRaises(ValueError):
            AgentFactory(self.database).load("agent_8LRT3N5QYB")


if __name__ == "__main__":
    unittest.main()
