"""完整 Agent 的运行边界测试。"""

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
from session.session_service import SessionService  # noqa: E402
from storage.database import StateDatabase  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.types import AgentProfile, LLMProfile  # noqa: E402
from tools.types import Tool  # noqa: E402


class SummarizerLLM:
    """满足 Context 创建所需的最小模型接口。"""

    def __init__(self) -> None:
        self.system_prompt = ""


class AgentTests(unittest.TestCase):
    """验证 Agent 是由 Session 依赖完整组装的可执行对象。"""

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
        AgentProfileRepository(self.database).save(
            AgentProfile(
                id="agent_1V3ASAXQ2A",
                name="代码专家",
                description="负责实现代码功能",
                personality="务实",
                expertise=["Python"],
                llm_profile_id="llm_7KQ2M8P4XZ",
                tools=["read"],
            )
        )

    def tearDown(self):
        self.database.close()
        self.temp_dir.cleanup()

    def _load_agent(self, session_id: str) -> Agent:
        context = Context(SummarizerLLM(), session_id=session_id)
        execution_context = ExecutionContext("/workspace", "agent_1V3ASAXQ2A", session_id)
        permission = PermissionManager(
            mode=PermissionMode.BUILD,
            session_id=session_id,
            project_path=execution_context.project_path,
        )
        return AgentFactory(self.database).load(
            "agent_1V3ASAXQ2A",
            context=context,
            execution_context=execution_context,
            permission=permission,
            permission_mode="build",
        )

    def test_factory_load_returns_a_complete_agent(self):
        """Factory 返回的 Agent 应可直接执行，不再只是 Profile 包装。"""
        agent = self._load_agent("session_TEST01")

        self.assertIsInstance(agent, Agent)
        self.assertEqual(agent.agent_id, "agent_1V3ASAXQ2A")
        self.assertEqual(agent.name, "代码专家")
        self.assertEqual(agent.description, "负责实现代码功能")
        self.assertEqual(agent.personality, "务实")
        self.assertEqual(agent.expertise, ("Python",))
        self.assertEqual(
            tuple(tool.schema["name"] for tool in agent.tool_definitions),
            ("read",),
        )
        self.assertIs(agent.runtime.context, agent.context)
        self.assertIs(agent.runtime.tools, agent.tools)
        self.assertIs(agent.runtime.permission, agent.permission)
        self.assertFalse(hasattr(agent, "profile"))

    def test_one_logical_agent_creates_distinct_session_agents(self):
        """同一个 Agent ID 在两个 Session 中必须得到独立 Agent 与 Runtime。"""
        sessions = SessionService(self.database)
        first_execution = sessions.create_direct_session("agent_1V3ASAXQ2A")
        second_execution = sessions.create_direct_session("agent_1V3ASAXQ2A")
        first = first_execution.agents["agent_1V3ASAXQ2A"]
        second = second_execution.agents["agent_1V3ASAXQ2A"]

        self.assertIsNot(first, second)
        self.assertIsNot(first.runtime, second.runtime)
        self.assertIsNot(first.llm, second.llm)
        self.assertIsNot(first.tools, second.tools)
        self.assertIsNot(first.execution_context, second.execution_context)
        self.assertIsNot(first.context, second.context)
        self.assertEqual(first.execution_context.agent_id, second.execution_context.agent_id)

    def test_agent_keeps_immutable_tool_definitions(self):
        """Agent 应保留已验证工具定义，但工具执行实例属于当前 Session。"""
        agent = self._load_agent("session_TEST02")

        self.assertEqual(len(agent.tool_definitions), 1)
        self.assertIsInstance(agent.tool_definitions[0], Tool)
        self.assertEqual([tool["name"] for tool in agent.tools.list], ["read"])


if __name__ == "__main__":
    unittest.main()
