"""持久化领域对象契约测试。"""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from storage.types import (  # noqa: E402
    AgentDelegation,
    AgentProfile,
    ContextItem,
    LLMProfile,
    Session,
    SessionParticipant,
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

    def test_session_participant_connects_agent_to_one_session(self):
        """参与者保存会话内身份，而不是把 Agent 直接挂到 Session。"""
        participant = SessionParticipant(
            id="participant_8T2LQ6MZP1",
            session_id="session_4N9C1R7WBA",
            agent_id="agent_1V3ASAXQ2A",
            role="PRIMARY",
            join_reason="USER_SELECTED",
        )

        self.assertEqual(participant.agent_id, "agent_1V3ASAXQ2A")
        self.assertEqual(participant.role, "PRIMARY")

    def test_context_item_has_at_most_one_direct_target(self):
        """首期用单个目标字段表达定向消息，群发使用 PUBLIC。"""
        item = ContextItem(
            id="item_3F7XK9A2VC",
            session_id="session_4N9C1R7WBA",
            sequence_no=1,
            kind="USER_MESSAGE",
            author_participant_id=None,
            target_participant_id="participant_8T2LQ6MZP1",
            visibility="TARGETED",
            payload={"text": "请检查代码"},
        )

        self.assertEqual(item.target_participant_id, "participant_8T2LQ6MZP1")

    def test_public_context_item_cannot_have_a_target(self):
        """PUBLIC 与单目标不能同时出现，避免可见性语义冲突。"""
        with self.assertRaises(ValueError):
            ContextItem(
                id="item_3F7XK9A2VC",
                session_id="session_4N9C1R7WBA",
                sequence_no=1,
                kind="AGENT_MESSAGE",
                author_participant_id="participant_8T2LQ6MZP1",
                target_participant_id="participant_8T2LQ6MZP1",
                visibility="PUBLIC",
                payload={"text": "公开消息"},
            )

    def test_delegation_is_scoped_to_one_session(self):
        """委托记录同时引用请求者、执行者和会话。"""
        delegation = AgentDelegation(
            id="delegation_5H1R8DQP6M",
            session_id="session_4N9C1R7WBA",
            requester_participant_id="participant_8T2LQ6MZP1",
            worker_participant_id="participant_9U3M7BKP2C",
            request_item_id="item_3F7XK9A2VC",
            status="PENDING",
        )

        self.assertEqual(delegation.status, "PENDING")
        self.assertIsNone(delegation.result_item_id)

    def test_llm_profile_keeps_only_a_credential_reference(self):
        """LLM 配置保存凭据引用，不保存明文 API Key 字段。"""
        profile = LLMProfile(
            id="llm_7KQ2M8P4XZ",
            name="代码模型",
            provider="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-5",
            credential_ref="env:OPENAI_API_KEY",
        )

        self.assertEqual(profile.credential_ref, "env:OPENAI_API_KEY")
        self.assertFalse(hasattr(profile, "api_key"))


if __name__ == "__main__":
    unittest.main()
