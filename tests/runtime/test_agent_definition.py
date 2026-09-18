"""AgentDefinition 的稳定身份与跨 Session 复用测试。"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from runtime.agent_definition import AgentDefinition  # noqa: E402
from runtime.session_agent_factory import SessionAgentRuntimeFactory  # noqa: E402
from runtime.agent_factory import AgentFactory  # noqa: E402
from storage.database import StateDatabase  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.types import AgentProfile, LLMProfile  # noqa: E402
from tools.types import Tool  # noqa: E402


class AgentDefinitionTests(unittest.TestCase):
    """验证 AgentFactory 只加载可跨会话复用的 Agent 定义。"""

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
                tools=["read"],
                permission_mode="BUILD",
            )
        )

    def tearDown(self):
        self.database.close()
        self.temp_dir.cleanup()

    def test_factory_load_returns_reusable_definition_without_session_state(self):
        """同一 AgentDefinition 不应携带 session、context 或工具执行环境。"""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret-value"}):
            definition = AgentFactory(self.database).load("agent_1V3ASAXQ2A")

        self.assertIsInstance(definition, AgentDefinition)
        self.assertEqual(definition.agent_id, "agent_1V3ASAXQ2A")
        self.assertEqual(definition.profile.id, definition.agent_id)
        self.assertEqual(
            tuple(tool.schema["name"] for tool in definition.tool_definitions),
            ("read",),
        )
        self.assertFalse(hasattr(definition, "session_id"))
        self.assertFalse(hasattr(definition, "context"))

    def test_one_definition_creates_distinct_session_execution_contexts(self):
        """同一稳定定义创建的两个执行实例必须拥有不同 Session 环境。"""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret-value"}):
            definition = AgentFactory(self.database).load("agent_1V3ASAXQ2A")
            first = definition.create_session_runtime("session_1ABCDEF234")
            second = definition.create_session_runtime("session_2ABCDEF234")

        self.assertIsNot(first, second)
        self.assertEqual(first.ctx.agent_id, second.ctx.agent_id)
        self.assertNotEqual(first.ctx.session_id, second.ctx.session_id)
        self.assertIsNot(first.tools, second.tools)

    def test_definition_contains_frozen_tool_definitions(self):
        """Definition 应冻结已验证的工具定义，避免每个 Session 重复发现模块。"""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret-value"}):
            definition = AgentFactory(self.database).load("agent_1V3ASAXQ2A")

        self.assertEqual(len(definition.tool_definitions), 1)
        self.assertIsInstance(definition.tool_definitions[0], Tool)

    def test_session_runtime_factory_validates_membership_before_creation(self):
        """Session 编排层应在创建执行环境前验证固定成员关系。"""
        from storage.repositories.session import SessionRepository

        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret-value"}):
            definition = AgentFactory(self.database).load("agent_1V3ASAXQ2A")

        session = SessionRepository(self.database).create_with_agents(
            "DIRECT", [(definition.agent_id, "PRIMARY")]
        )
        factory = SessionAgentRuntimeFactory(self.database)
        runtime = factory.create(definition, session.id)
        self.assertEqual(runtime.ctx.session_id, session.id)
        with self.assertRaises(ValueError):
            factory.create(definition, "session_2ABCDEF234")


if __name__ == "__main__":
    unittest.main()
