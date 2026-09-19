"""持久化领域对象契约测试。"""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from storage.types import (  # noqa: E402
    AgentProfile,
    ContextItem,
    LLMProfile,
    Session,
    SessionAgent,
)


class StorageTypeTests(unittest.TestCase):
    """验证首期简化后的持久化领域模型。"""

    def test_agent_profile_contains_tools_without_tool_config_object(self):
        """AgentProfile 直接保存工具名称集合。"""
        profile = AgentProfile(
            id="agent_1V3ASAXQ2A",
            name="代码专家",
            description="负责实现代码功能",
            personality="务实",
            expertise=["Python"],
            llm_profile_id="llm_7KQ2M8P4XZ",
            tools=["read", "write"],
            permission_mode="build",
        )

        self.assertEqual(profile.tools, ["read", "write"])
        self.assertFalse(hasattr(profile, "instructions"))

    def test_session_agent_connects_agent_to_one_session(self):
        """会话成员直接使用稳定 agent_id，不再创建临时参与者 ID。"""
        member = SessionAgent(
            session_id="session_4N9C1R7WBA",
            agent_id="agent_1V3ASAXQ2A",
            role="PRIMARY",
        )

        self.assertEqual(member.agent_id, "agent_1V3ASAXQ2A")
        self.assertEqual(member.role, "PRIMARY")
        self.assertFalse(hasattr(member, "id"))

    def test_context_item_has_at_most_one_direct_target(self):
        """首期用单个目标字段表达定向消息，群发使用 PUBLIC。"""
        item = ContextItem(
            id="item_3F7XK9A2VC",
            session_id="session_4N9C1R7WBA",
            sequence_no=1,
            kind="USER_MESSAGE",
            author_agent_id=None,
            target_agent_id="agent_1V3ASAXQ2A",
            visibility="TARGETED",
            payload={"text": "请检查代码"},
        )

        self.assertEqual(item.target_agent_id, "agent_1V3ASAXQ2A")

    def test_public_context_item_cannot_have_a_target(self):
        """PUBLIC 与单目标不能同时出现，避免可见性语义冲突。"""
        with self.assertRaises(ValueError):
            ContextItem(
                id="item_3F7XK9A2VC",
                session_id="session_4N9C1R7WBA",
                sequence_no=1,
                kind="AGENT_MESSAGE",
                author_agent_id="agent_1V3ASAXQ2A",
                target_agent_id="agent_1V3ASAXQ2A",
                visibility="PUBLIC",
                payload={"text": "公开消息"},
            )

    def test_session_rejects_deferred_open_mode(self):
        """当前版本只支持固定成员的 DIRECT 和 GROUP 会话。"""
        with self.assertRaises(ValueError):
            Session(
                id="session_4N9C1R7WBA",
                title=None,
                conversation_mode="OPEN",
                status="ACTIVE",
            )

    def test_llm_profile_keeps_api_key_without_a_credential_reference(self):
        """LLM 配置直接保存 API Key，不再保留环境变量引用字段。"""
        profile = LLMProfile(
            id="llm_7KQ2M8P4XZ",
            name="代码模型",
            provider="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-5",
            api_key="sk-local-test-key",
        )

        self.assertEqual(profile.api_key, "sk-local-test-key")
        self.assertFalse(hasattr(profile, "credential_ref"))


if __name__ == "__main__":
    unittest.main()
