"""AgentFactory 的配置加载和运行时组装测试。"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from runtime.agent_factory import AgentFactory  # noqa: E402
from storage.database import StateDatabase  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.types import AgentProfile, LLMProfile  # noqa: E402


class AgentFactoryTests(unittest.TestCase):
    """验证数据库配置可以组装为一个运行时 Agent。"""

    def setUp(self):
        """创建包含 LLM 和 Agent 配置的临时数据库。"""
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
        """关闭数据库并清理临时目录。"""
        self.database.close()
        self.temp_dir.cleanup()

    def test_load_assembles_agent_from_persisted_profile(self):
        """工厂应组装 LLM、工具、上下文和权限依赖。"""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret-value"}):
            with patch("runtime.agent.LLM") as llm_class:
                agent = AgentFactory(self.database).load(
                    "agent_1V3ASAXQ2A",
                    session_id="session_4N9C1R7WBA",
                )

        self.assertEqual(agent.session_id, "session_4N9C1R7WBA")
        self.assertEqual(agent.workspace, str(Path(self.temp_dir.name).resolve()))
        self.assertEqual(agent.ctx.agent_id, "agent_1V3ASAXQ2A")
        self.assertIn("read", agent.tools.map)
        self.assertIn("write", agent.tools.map)
        self.assertEqual(llm_class.call_count, 2)

    def test_load_raises_for_unknown_agent(self):
        """不存在的 Agent 配置不能创建默认 Agent。"""
        with self.assertRaises(ValueError):
            AgentFactory(self.database).load("agent_8LRT3N5QYB")


if __name__ == "__main__":
    unittest.main()
