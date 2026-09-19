"""ContextService 的上下文持久化与 Responses 投影测试。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from storage.context_service import ContextService  # noqa: E402
from context.context import Context  # noqa: E402
from storage.database import StateDatabase  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.context_item import ContextItemRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.repositories.session import SessionRepository  # noqa: E402
from storage.types import AgentProfile, LLMProfile  # noqa: E402


class FakeContextLLM:
    """满足 Context 初始化所需接口的最小 LLM 替身。"""

    def __init__(self):
        self.system_prompt = ""


class ContextServiceTests(unittest.TestCase):
    """验证 ContextService 不暴露 SQL，并能生成模型输入投影。"""

    def setUp(self):
        """创建一个带两个固定 Agent 成员的协作会话。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = StateDatabase(self.temp_dir.name)
        self.database.initialize()
        LLMProfileRepository(self.database).save(
            LLMProfile(
                id="llm_7KQ2M8P4XZ",
                name="通用模型",
                provider="openai",
                base_url=None,
                model="gpt-5",
                api_key="sk-test-key",
            )
        )
        agents = AgentProfileRepository(self.database)
        for agent_id, name in (
            ("agent_1V3ASAXQ2A", "代码专家"),
            ("agent_9U3M7BKP2C", "测试专家"),
        ):
            agents.save(
                AgentProfile(
                    id=agent_id,
                    name=name,
                    description="开发工作",
                    personality="务实",
                    expertise=["Python"],
                    llm_profile_id="llm_7KQ2M8P4XZ",
                    tools=["read"],
                    permission_mode="BUILD",
                )
            )
        self.session = SessionRepository(self.database).create_with_agents(
            "GROUP",
            [
                ("agent_1V3ASAXQ2A", "MEMBER"),
                ("agent_9U3M7BKP2C", "MEMBER"),
            ],
        )
        self.service = ContextService(
            ContextItemRepository(self.database),
            self.session.id,
        )

    def tearDown(self):
        """关闭数据库并清理临时目录。"""
        self.database.close()
        self.temp_dir.cleanup()

    def test_append_events_and_load_visible_items(self):
        """服务层方法应写入业务事件并按 Agent 返回可见项。"""
        user_item = self.service.append_user_message("请检查代码")
        agent_item = self.service.append_agent_message(
            "agent_1V3ASAXQ2A",
            "我开始检查。",
        )
        targeted_item = self.service.append_agent_message(
            "agent_1V3ASAXQ2A",
            "只给测试 Agent 的提示",
            visibility="TARGETED",
            target_agent_id="agent_9U3M7BKP2C",
        )

        visible = self.service.load_visible("agent_9U3M7BKP2C")

        self.assertEqual(
            [item.id for item in visible],
            [user_item.id, agent_item.id, targeted_item.id],
        )

    def test_function_call_and_output_are_projected_to_responses_items(self):
        """工具事件应被转换成 Responses 所需的 function call 结构。"""
        call = self.service.append_function_call(
            "agent_1V3ASAXQ2A",
            call_id="call_001",
            name="read",
            arguments='{"target_path":"README.md"}',
        )
        output = self.service.append_function_call_output(
            "agent_1V3ASAXQ2A",
            call_id="call_001",
            output="读取成功",
            caused_by_item_id=call.id,
        )

        projected = self.service.to_responses_input(
            self.service.load_visible("agent_1V3ASAXQ2A")
        )

        self.assertEqual(projected[0]["type"], "function_call")
        self.assertEqual(projected[0]["call_id"], "call_001")
        self.assertEqual(projected[0]["name"], "read")
        self.assertEqual(projected[1]["type"], "function_call_output")
        self.assertEqual(projected[1]["call_id"], output.call_id)
        self.assertEqual(projected[1]["output"], "读取成功")

    def test_service_does_not_store_vendor_protocol_fields_in_payload(self):
        """数据库中的事件 payload 使用业务字段，Responses 字段只在投影时生成。"""
        item = self.service.append_agent_message(
            "agent_1V3ASAXQ2A",
            "完成",
        )

        self.assertEqual(item.payload, {"text": "完成"})
        self.assertNotIn("type", item.payload)
        self.assertNotIn("role", item.payload)

    def test_service_can_save_and_load_current_context(self):
        """ContextService 应暴露 Session 当前 Context 的持久化边界。"""
        messages = [
            {"type": "message", "role": "developer", "content": "摘要"},
        ]

        self.service.save_current_context(messages)

        self.assertEqual(self.service.load_current_context(), messages)

    def test_service_restores_saved_current_context_before_raw_events(self):
        """恢复时应优先使用已经治理过的 Session 当前上下文。"""
        self.service.append_user_message("原始事件")
        saved = [{"type": "message", "role": "developer", "content": "压缩摘要"}]
        self.service.save_current_context(saved)
        context = Context(FakeContextLLM(), session_id=self.session.id)

        self.service.restore_context(context, "agent_1V3ASAXQ2A")

        self.assertEqual(context.export(), saved)

    def test_service_builds_initial_context_from_raw_events_when_current_is_empty(self):
        """新旧 Session 没有当前快照时，应从原始业务事件构建输入。"""
        self.service.append_user_message("从原始事件恢复")
        context = Context(FakeContextLLM(), session_id=self.session.id)

        self.service.restore_context(context, "agent_1V3ASAXQ2A")

        self.assertEqual(context.messages[0]["role"], "user")
        self.assertEqual(context.messages[0]["content"][0]["text"], "从原始事件恢复")

    def test_service_saves_context_snapshot(self):
        """服务应能保存 Context 导出的独立快照。"""
        context = Context(FakeContextLLM(), session_id=self.session.id)
        context.append_user_message("当前上下文")

        self.service.save_context(context)

        self.assertEqual(self.service.load_current_context(), context.export())


if __name__ == "__main__":
    unittest.main()
