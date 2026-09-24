"""PromptBuilder 的 Agent 指令组装测试。"""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from runtime.prompt_builder import PromptBuilder  # noqa: E402
from storage.types import AgentProfile  # noqa: E402


class PromptBuilderTests(unittest.TestCase):
    """验证系统指令由 AgentProfile 和运行时信息派生。"""

    def setUp(self):
        """创建测试用 Agent 配置。"""
        self.profile = AgentProfile(
            id="agent_1V3ASAXQ2A",
            name="代码审查专家",
            description="发现代码中的设计缺陷和安全问题",
            personality="严谨、谨慎",
            expertise=["Python", "安全审查"],
            llm_profile_id="llm_7KQ2M8P4XZ",
            tools=["read"],
        )

    def test_build_contains_profile_semantics_and_runtime_capabilities(self):
        """生成结果应包含身份信息、能力、工具和权限模式。"""
        prompt = PromptBuilder().build(
            self.profile,
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

    def test_build_uses_profile_tools_without_inventing_a_permission_mode(self):
        """权限模式只能由 Session 显式传入，不能从 AgentProfile 推导。"""
        prompt = PromptBuilder().build(self.profile)

        self.assertIn("read", prompt)
        self.assertNotIn("当前权限模式", prompt)

    def test_build_mode_tells_agent_to_request_external_access_through_tools(self):
        """Build 不能让 Agent 因旧历史自行断言工作目录外不可访问。"""
        prompt = PromptBuilder().build(self.profile, permission_mode="build")

        self.assertIn("工作目录外", prompt)
        self.assertIn("发起工具调用", prompt)
        self.assertIn("不要根据历史消息自行断言没有权限", prompt)

    def test_build_rejects_empty_profile_description(self):
        """关键 Agent 描述为空时不能生成无意义指令。"""
        self.profile.description = ""

        with self.assertRaises(ValueError):
            PromptBuilder().build(self.profile)


if __name__ == "__main__":
    unittest.main()
