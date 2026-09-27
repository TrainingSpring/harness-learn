"""PromptBuilder 的 Agent 指令组装测试。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from context.context import Context  # noqa: E402
from head.types import LLMConfig  # noqa: E402
from permission.PermissionManager import PermissionManager  # noqa: E402
from permission.types import PermissionMode  # noqa: E402
from runtime.agent import Agent  # noqa: E402
from runtime.prompt_builder import PromptBuilder  # noqa: E402
from session.ExecutionContext import ExecutionContext  # noqa: E402
from tools.registry.catalog import ToolCatalog  # noqa: E402


class SummarizerLLM:
    def __init__(self) -> None:
        self.system_prompt = ""


class PromptBuilderTests(unittest.TestCase):
    """验证系统指令由 Agent 与运行时信息派生。"""

    def setUp(self):
        session_id = "session_TEST01"
        execution_context = ExecutionContext("/workspace", "agent_1V3ASAXQ2A", session_id)
        self.agent = Agent(
            agent_id="agent_1V3ASAXQ2A",
            name="代码审查专家",
            description="发现代码中的设计缺陷和安全问题",
            personality="严谨、谨慎",
            expertise=("Python", "安全审查"),
            llm_config=LLMConfig("https://api.openai.com/v1", "sk-test-key", "gpt-5"),
            tool_definitions=(ToolCatalog().get("read"),),
            context=Context(SummarizerLLM(), session_id=session_id),
            execution_context=execution_context,
            permission=PermissionManager(
                mode=PermissionMode.PLAN,
                session_id=session_id,
                project_path=execution_context.project_path,
            ),
            permission_mode="plan",
        )

    def test_build_contains_agent_semantics_and_runtime_capabilities(self):
        prompt = PromptBuilder().build(
            self.agent,
            session_context="当前任务是审查 src 目录",
            tools=["read"],
            permission_mode="PLAN",
        )

        self.assertIn("代码审查专家", prompt)
        self.assertIn("发现代码中的设计缺陷和安全问题", prompt)
        self.assertIn("严谨、谨慎", prompt)
        self.assertIn("Python、安全审查", prompt)
        self.assertIn("read", prompt)
        self.assertIn("PLAN", prompt)
        self.assertIn("当前任务是审查 src 目录", prompt)

    def test_build_uses_agent_tools_without_inventing_a_permission_mode(self):
        prompt = PromptBuilder().build(self.agent)

        self.assertIn("read", prompt)
        self.assertNotIn("当前权限模式", prompt)

    def test_build_mode_tells_agent_to_request_external_access_through_tools(self):
        prompt = PromptBuilder().build(self.agent, permission_mode="build")

        self.assertIn("工作目录外", prompt)
        self.assertIn("发起工具调用", prompt)
        self.assertIn("不要根据历史消息自行断言没有权限", prompt)

    def test_build_rejects_empty_agent_description(self):
        self.agent.description = ""

        with self.assertRaises(ValueError):
            PromptBuilder().build(self.agent)

    def test_build_includes_skill_metadata_without_skill_body(self):
        prompt = PromptBuilder().build(
            self.agent,
            skill_metadata="已配置的 Skills：\n- review: Review code",
        )
        self.assertIn("review", prompt)
        self.assertNotIn("Review carefully", prompt)


if __name__ == "__main__":
    unittest.main()
