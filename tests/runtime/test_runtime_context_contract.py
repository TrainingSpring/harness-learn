"""Runtime 与外部 Context 的边界测试。"""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from context.context import Context  # noqa: E402
from head.types import LLMResponse  # noqa: E402
from permission.PermissionManager import PermissionManager  # noqa: E402
from permission.types import PermissionMode  # noqa: E402
from runtime.runtime import Runtime  # noqa: E402
from session.ExecutionContext import ExecutionContext  # noqa: E402
from tools.tools import Tools  # noqa: E402


class RecordingLLM:
    """记录每次模型输入，并立即结束一轮对话。"""

    def __init__(self):
        self.system_prompt = ""
        self.inputs = []

    def call_responses_stream(self, model_input, _tools):
        self.inputs.append(copy.deepcopy(model_input))
        yield LLMResponse(type="done", data=[], is_stop=True)


def _runtime(llm):
    execution_context = ExecutionContext("/workspace", "agent_TEST00001", "session_TEST01")
    tools = Tools(execution_context)
    permission = PermissionManager(
        mode=PermissionMode.BUILD,
        workspace="/workspace",
        agent_id=execution_context.agent_id,
    )
    return Runtime(llm, tools, execution_context, permission)


def test_runtime_does_not_store_context_or_context_service():
    runtime = _runtime(RecordingLLM())

    assert not hasattr(runtime, "context")
    assert not hasattr(runtime, "context_service")


def test_run_reads_only_the_context_passed_by_the_caller():
    llm = RecordingLLM()
    runtime = _runtime(llm)
    context_a = Context(RecordingLLM(), session_id="session_TEST01")
    context_b = Context(RecordingLLM(), session_id="session_TEST02")
    context_a.append_user_message("会话 A")
    context_b.append_user_message("会话 B")

    list(runtime.run(context_a))

    assert llm.inputs[0][-1]["content"] == "会话 A"
    assert all(item.get("content") != "会话 B" for item in llm.inputs[0])

    list(runtime.run(context_b))

    assert llm.inputs[1][-1]["content"] == "会话 B"


def test_run_requires_a_context_instance():
    runtime = _runtime(RecordingLLM())

    with pytest.raises(TypeError, match="context"):
        list(runtime.run("用户消息"))
