"""SessionService 与 SessionExecution 的会话边界测试。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from head.types import LLMResponse, LLMResponseOutputItem  # noqa: E402
from permission.types import (  # noqa: E402
    PermissionAction,
    PermissionDecision,
    PermissionRequest,
    PermissionResponse,
    PermissionScope,
)
from runtime.runtime_events import PermissionRequiredEvent  # noqa: E402
from session.session_service import SessionService  # noqa: E402
from storage.context_service import ContextService  # noqa: E402
from storage.database import StateDatabase  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.context_item import ContextItemRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.types import AgentProfile, LLMProfile  # noqa: E402


class FakeRuntime:
    """用可观察的最小 Runtime 验证 Session 层只做调度。"""

    def __init__(self, agent_id: str, session_id: str) -> None:
        self.agent_id = agent_id
        self.session_id = session_id
        self.contexts = []
        self.wait_for_permission = False
        self.cancel_calls = 0

    def cancel(self):
        """记录 Session 只取消当前成员 Runtime 的调用。"""
        self.cancel_calls += 1
        self.wait_for_permission = False

    def run(self, context):
        self.contexts.append(context)
        if self.wait_for_permission:
            context.append_function_call(
                self.agent_id,
                call_id=f"call_{self.agent_id[-4:]}",
                name="read",
                arguments='{"target_path":"README.md"}',
            )
            yield PermissionRequiredEvent(
                type="permission_required",
                request=PermissionRequest(
                    action=PermissionAction.FILE_READ,
                    resource="README.md",
                    tool_name="read",
                    call_id=f"call_{self.agent_id[-4:]}",
                    session_id=self.session_id,
                ),
            )
            return
        yield from self._complete(context)

    def resolve_permission(self, context, response):
        self.contexts.append(context)
        context.append_function_call_output(
            self.agent_id,
            "已读取 README.md",
            call_id=response.call_id,
        )
        self.wait_for_permission = False
        yield from self._complete(context)

    def _complete(self, context):
        text = f"{self.agent_id} 已处理"
        context.append_agent_message(self.agent_id, text)
        yield LLMResponse(
            type="done",
            data=[
                LLMResponseOutputItem(
                    type="message",
                    id=f"msg_{self.agent_id[-4:]}",
                    content=text,
                    name=None,
                    arguments=None,
                    call_id=None,
                    status="completed",
                )
            ],
            is_stop=True,
        )


class FakeSessionService(SessionService):
    """以受控 Runtime 替换 Service 内部装配，隔离模型调用。"""

    def __init__(self, database) -> None:
        super().__init__(database)
        self.runtimes = {}

    def _create_runtime(self, agent, member, *_args):
        runtime = FakeRuntime(member.agent_id, member.session_id)
        self.runtimes[(member.session_id, member.agent_id)] = runtime
        return runtime


class SessionExecutionTests(unittest.TestCase):
    """锁定 Session 拥有 Context、Runtime 保留 Agent Loop 的契约。"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = StateDatabase(self.temp_dir.name)
        self.database.initialize()
        LLMProfileRepository(self.database).save(
            LLMProfile(
                id="llm_7KQ2M8P4XZ",
                name="通用模型",
                provider="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-5",
                api_key="sk-test-key",
            )
        )
        agents = AgentProfileRepository(self.database)
        for agent_id in ("agent_1V3ASAXQ2A", "agent_9U3M7BKP2C"):
            agents.save(
                AgentProfile(
                    id=agent_id,
                    name=agent_id,
                    description="讨论角色",
                    personality="务实",
                    expertise=["Python"],
                    llm_profile_id="llm_7KQ2M8P4XZ",
                    tools=["read"],
                )
            )
        self.sessions = FakeSessionService(self.database)

    def tearDown(self):
        self.database.close()
        self.temp_dir.cleanup()

    def test_load_restores_governed_snapshot_into_the_only_session_context(self):
        created = self.sessions.create_direct_session("agent_1V3ASAXQ2A")
        session = created.session
        saved = [{"type": "message", "role": "developer", "content": "已有摘要"}]
        ContextService(
            ContextItemRepository(self.database), session.id
        ).save_current_context(saved)

        execution = self.sessions.load(session.id)

        self.assertEqual(execution.context.export(), saved)
        runtime = self.sessions.runtimes[(session.id, "agent_1V3ASAXQ2A")]
        self.assertEqual(runtime.contexts, [])
        self.assertEqual(len(execution.runtimes), 1)
        self.assertIs(execution.context, execution.context)

    def test_load_rebuilds_context_from_raw_timeline_when_snapshot_is_empty(self):
        created = self.sessions.create_direct_session("agent_1V3ASAXQ2A")
        session = created.session
        ContextService(
            ContextItemRepository(self.database), session.id
        ).append_user_message("从原始消息恢复")

        execution = self.sessions.load(session.id)

        self.assertEqual(
            execution.context.export(),
            [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "从原始消息恢复"}],
                }
            ],
        )

    def test_same_agent_in_two_sessions_gets_separate_context_and_runtime_state(self):
        first = self.sessions.create_direct_session("agent_1V3ASAXQ2A")
        second = self.sessions.create_direct_session("agent_1V3ASAXQ2A")
        first_session = first.session
        second_session = second.session

        list(first.send("仅第一会话的消息"))

        first_runtime = self.sessions.runtimes[
            (first_session.id, "agent_1V3ASAXQ2A")
        ]
        second_runtime = self.sessions.runtimes[
            (second_session.id, "agent_1V3ASAXQ2A")
        ]
        self.assertIsNot(first.context, second.context)
        self.assertIsNot(first_runtime, second_runtime)
        self.assertEqual(second.context.export(), [])

    def test_direct_send_persists_user_and_agent_events_with_current_context(self):
        execution = self.sessions.create_direct_session("agent_1V3ASAXQ2A")
        session = execution.session

        events = list(execution.send("请检查 README"))

        self.assertEqual([event.type for event in events], ["done"])
        self.assertEqual(
            [item["role"] for item in execution.context.export()],
            ["user", "assistant"],
        )
        persisted = ContextService(
            ContextItemRepository(self.database), session.id
        )
        self.assertEqual(persisted.load_current_context(), execution.context.export())
        self.assertEqual(
            [item.kind for item in persisted.load_visible("agent_1V3ASAXQ2A")],
            ["USER_MESSAGE", "AGENT_MESSAGE"],
        )
        runtime = self.sessions.runtimes[(session.id, "agent_1V3ASAXQ2A")]
        self.assertEqual(runtime.contexts, [execution.context])

    def test_group_runs_members_in_order_with_one_shared_context(self):
        execution = self.sessions.create_group_session(
            ["agent_1V3ASAXQ2A", "agent_9U3M7BKP2C"]
        )
        session = execution.session

        list(execution.send("请分别给出意见"))

        first = self.sessions.runtimes[(session.id, "agent_1V3ASAXQ2A")]
        second = self.sessions.runtimes[(session.id, "agent_9U3M7BKP2C")]
        self.assertEqual(first.contexts, [execution.context])
        self.assertEqual(second.contexts, [execution.context])
        self.assertEqual(
            [item["content"] for item in execution.context.export()],
            [
                "请分别给出意见",
                "agent_1V3ASAXQ2A 已处理",
                "agent_9U3M7BKP2C 已处理",
            ],
        )

    def test_permission_resume_uses_the_same_runtime_and_context_before_group_continues(self):
        execution = self.sessions.create_group_session(
            ["agent_1V3ASAXQ2A", "agent_9U3M7BKP2C"]
        )
        session = execution.session
        first = self.sessions.runtimes[(session.id, "agent_1V3ASAXQ2A")]
        second = self.sessions.runtimes[(session.id, "agent_9U3M7BKP2C")]
        first.wait_for_permission = True

        paused = list(execution.send("先读取文件"))
        self.assertIsInstance(paused[-1], PermissionRequiredEvent)
        self.assertEqual(second.contexts, [])

        events = list(execution.resolve_permission(
            PermissionResponse(
                call_id=paused[-1].request.call_id,
                decision=PermissionDecision.ALLOW,
                scope=PermissionScope.ONCE,
            )
        ))

        self.assertEqual([event.type for event in events], ["done", "done"])
        self.assertEqual(first.contexts, [execution.context, execution.context])
        self.assertEqual(second.contexts, [execution.context])
        persisted = ContextService(
            ContextItemRepository(self.database), session.id
        )
        self.assertEqual(
            [item.kind for item in persisted.load_visible("agent_1V3ASAXQ2A")],
            [
                "USER_MESSAGE",
                "FUNCTION_CALL",
                "FUNCTION_CALL_OUTPUT",
                "AGENT_MESSAGE",
                "AGENT_MESSAGE",
            ],
        )
        self.assertEqual(persisted.load_current_context(), execution.context.export())

    def test_cancel_only_stops_waiting_member_and_keeps_current_context(self):
        """取消权限暂停的 GROUP 会话不能影响其他成员或回退上下文。"""
        execution = self.sessions.create_group_session(
            ["agent_1V3ASAXQ2A", "agent_9U3M7BKP2C"]
        )
        session = execution.session
        first = self.sessions.runtimes[(session.id, "agent_1V3ASAXQ2A")]
        second = self.sessions.runtimes[(session.id, "agent_9U3M7BKP2C")]
        first.wait_for_permission = True

        paused = list(execution.send("读取后取消"))
        saved_before_cancel = execution.context.export()

        execution.cancel()

        self.assertEqual(first.cancel_calls, 1)
        self.assertEqual(second.cancel_calls, 0)
        self.assertEqual(
            ContextService(
                ContextItemRepository(self.database), session.id
            ).load_current_context(),
            saved_before_cancel,
        )
        with self.assertRaises(ValueError):
            list(execution.resolve_permission(
                PermissionResponse(
                    call_id=paused[-1].request.call_id,
                    decision=PermissionDecision.ALLOW,
                    scope=PermissionScope.ONCE,
                )
            ))


if __name__ == "__main__":
    unittest.main()
