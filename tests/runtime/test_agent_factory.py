"""AgentFactory 的 AgentDefinition 配置加载测试。"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from runtime.agent_definition import AgentDefinition  # noqa: E402
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
                credential_ref="env:OPENAI_API_KEY",
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
                permission_mode="BUILD",
            )
        )

    def tearDown(self):
        self.database.close()
        self.temp_dir.cleanup()

    def test_load_returns_stable_agent_definition(self):
        """Factory 不应在加载定义时创建 Session 执行状态。"""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret-value"}):
            definition = AgentFactory(self.database).load("agent_1V3ASAXQ2A")

        self.assertIsInstance(definition, AgentDefinition)
        self.assertEqual(definition.agent_id, "agent_1V3ASAXQ2A")
        self.assertEqual(definition.workspace, str(Path(self.temp_dir.name).resolve()))
        self.assertEqual(
            tuple(tool.schema["name"] for tool in definition.tool_definitions),
            ("read", "write"),
        )
        self.assertFalse(hasattr(definition, "session_id"))
        self.assertFalse(hasattr(definition, "context"))

    def test_load_raises_for_unknown_agent(self):
        """不存在的 Agent 配置不能创建默认定义。"""
        with self.assertRaises(ValueError):
            AgentFactory(self.database).load("agent_8LRT3N5QYB")


if __name__ == "__main__":
    unittest.main()
