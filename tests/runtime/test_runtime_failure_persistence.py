"""Session Runtime 异常时的上下文持久化测试。"""

import sys
import tempfile
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from context.context import Context  # noqa: E402
from session.session_service import SessionExecution  # noqa: E402
from storage.context_service import ContextService  # noqa: E402
from storage.database import StateDatabase  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.context_item import ContextItemRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.repositories.session import SessionRepository  # noqa: E402
from storage.repositories.session_agent import SessionAgentRepository  # noqa: E402
from storage.types import AgentProfile, LLMProfile  # noqa: E402


class SummarizerLLM:
    """满足 Context 初始化所需的最小摘要模型。"""

    def __init__(self) -> None:
        self.system_prompt = ""


class FailingRuntime:
    """模拟在写入 function call 后抛出内部异常的 Runtime。"""

    def run(self, context):
        context.append_function_call(
            "agent_1V3ASAXQ2A",
            call_id="call_FAILURE001",
            name="read",
            arguments='{"target_path":"README.md"}',
        )
        raise RuntimeError("provider unavailable")
        yield


def test_runtime_failure_persists_new_protocol_items_and_current_context():
    """异常不能回退用户消息或丢失已产生的 function call。"""
    with tempfile.TemporaryDirectory() as workspace:
        database = StateDatabase(workspace)
        database.initialize()
        try:
            LLMProfileRepository(database).save(
                LLMProfile(
                    id="llm_7KQ2M8P4XZ",
                    name="测试模型",
                    provider="openai",
                    base_url=None,
                    model="gpt-5",
                    api_key="sk-test-key",
                )
            )
            AgentProfileRepository(database).save(
                AgentProfile(
                    id="agent_1V3ASAXQ2A",
                    name="测试 Agent",
                    description="",
                    personality="",
                    expertise=["Python"],
                    llm_profile_id="llm_7KQ2M8P4XZ",
                    tools=["read"],
                    permission_mode="BUILD",
                )
            )
            session = SessionRepository(database).create_with_agents(
                "DIRECT", [("agent_1V3ASAXQ2A", "PRIMARY")]
            )
            member = SessionAgentRepository(database).list_for_session(session.id)[0]
            context = Context(SummarizerLLM(), session_id=session.id)
            context_service = ContextService(ContextItemRepository(database), session.id)
            execution = SessionExecution(
                session=session,
                context=context,
                context_service=context_service,
                members=(member,),
                runtimes={member.agent_id: FailingRuntime()},
            )

            with pytest.raises(RuntimeError, match="provider unavailable"):
                list(execution.send("读取 README"))

            assert context_service.load_current_context() == context.export()
            assert [item.kind for item in context_service.load_visible(member.agent_id)] == [
                "USER_MESSAGE",
                "FUNCTION_CALL",
            ]
        finally:
            database.close()
