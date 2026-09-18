"""稳定 Agent 身份与跨 Session 复用测试。"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from runtime.agent import Agent  # noqa: E402
from runtime.session_agent_factory import SessionAgentRuntimeFactory  # noqa: E402
from runtime.agent_factory import AgentFactory  # noqa: E402
from context.context import Context  # noqa: E402
from storage.database import StateDatabase  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.repositories.session_agent import SessionAgentRepository  # noqa: E402
from storage.types import AgentProfile, LLMProfile, SessionAgent  # noqa: E402
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

    def test_factory_load_returns_reusable_agent_without_session_state(self):
        """稳定 Agent 不应携带 session、context 或工具执行环境。"""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret-value"}):
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
        """同一稳定 Agent 通过 Session 工厂创建两个隔离执行环境。"""
        from storage.repositories.session import SessionRepository

        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret-value"}):
            agent = AgentFactory(self.database).load("agent_1V3ASAXQ2A")
        sessions = SessionRepository(self.database)
        first_session = sessions.create_with_agents("DIRECT", [(agent.agent_id, "PRIMARY")])
        second_session = sessions.create_with_agents("DIRECT", [(agent.agent_id, "PRIMARY")])
        members = SessionAgentRepository(self.database)
        factory = SessionAgentRuntimeFactory()
        first_context = Context(Mock(system_prompt=""), session_id=first_session.id)
        first = factory.create(
            agent,
            members.get(first_session.id, agent.agent_id),
            first_context,
        )
        second_context = Context(Mock(system_prompt=""), session_id=second_session.id)
        second = factory.create(
            agent,
            members.get(second_session.id, agent.agent_id),
            second_context,
        )

        self.assertIsNot(first, second)
        self.assertEqual(first.ctx.agent_id, second.ctx.agent_id)
        self.assertNotEqual(first.ctx.session_id, second.ctx.session_id)
        self.assertIsNot(first.tools, second.tools)
        self.assertIs(first.context, first_context)
        self.assertIs(second.context, second_context)

    def test_agent_contains_frozen_tool_definitions(self):
        """Agent 应冻结已验证的工具定义，避免每个 Session 重复发现模块。"""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret-value"}):
            agent = AgentFactory(self.database).load("agent_1V3ASAXQ2A")

        self.assertEqual(len(agent.tool_definitions), 1)
        self.assertIsInstance(agent.tool_definitions[0], Tool)

    def test_session_runtime_factory_validates_membership_before_creation(self):
        """Session 编排层应在创建执行环境前验证固定成员关系。"""
        from storage.repositories.session import SessionRepository

        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret-value"}):
            agent = AgentFactory(self.database).load("agent_1V3ASAXQ2A")

        session = SessionRepository(self.database).create_with_agents(
            "DIRECT", [(agent.agent_id, "PRIMARY")]
        )
        member = SessionAgentRepository(self.database).get(session.id, agent.agent_id)
        factory = SessionAgentRuntimeFactory()
        context = Context(Mock(system_prompt=""), session_id=session.id)
        runtime = factory.create(
            agent,
            member,
            context,
        )
        self.assertEqual(runtime.ctx.session_id, session.id)
        self.assertIs(runtime.context, context)
        with self.assertRaises(ValueError):
            factory.create(
                agent,
                SessionAgent(session.id, "agent_9U3M7BKP2C", "PRIMARY"),
                context,
            )
        with self.assertRaises(ValueError):
            factory.create(
                agent,
                member,
                Context(Mock(system_prompt=""), session_id="session_2ABCDEF234"),
            )

if __name__ == "__main__":
    unittest.main()
