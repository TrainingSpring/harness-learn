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

    call_stream = call_responses_stream


def _runtime(llm, context):
    execution_context = ExecutionContext("/workspace", "agent_TEST00001", "session_TEST01")
    tools = Tools(execution_context)
    permission = PermissionManager(
        mode=PermissionMode.BUILD,
        session_id=execution_context.session_id,
        project_path=execution_context.project_path,
    )
    return Runtime(llm, tools, execution_context, permission, context)


def test_runtime_stores_its_context_but_not_context_service():
    context = Context(RecordingLLM(), session_id="session_TEST01")
    runtime = _runtime(RecordingLLM(), context)

    assert runtime.context is context
    assert not hasattr(runtime, "context_service")


def test_runtime_uses_context_model_input_without_legacy_get_msg():
    """Runtime 必须通过正式的 to_model_input 接口读取调用方 Context。"""
    llm = RecordingLLM()
    context = Context(RecordingLLM(), session_id="session_TEST01")
    runtime = _runtime(llm, context)
    context.append_user_message("当前会话")

    list(runtime.run())

    assert llm.inputs[0][-1]["content"] == "当前会话"
    assert not hasattr(context, "get_msg")


def test_run_reads_its_bound_context():
    llm = RecordingLLM()
    context_a = Context(RecordingLLM(), session_id="session_TEST01")
    context_a.append_user_message("会话 A")
    runtime = _runtime(llm, context_a)

    list(runtime.run())

    assert llm.inputs[0][-1]["content"] == "会话 A"

def test_runtime_rejects_a_context_from_another_session():
    execution_context = ExecutionContext("/workspace", "agent_TEST00001", "session_TEST01")
    tools = Tools(execution_context)
    permission = PermissionManager(
        mode=PermissionMode.BUILD,
        session_id=execution_context.session_id,
        project_path=execution_context.project_path,
    )
    context = Context(RecordingLLM(), session_id="session_TEST02")

    with pytest.raises(ValueError, match="session_id"):
        Runtime(RecordingLLM(), tools, execution_context, permission, context)
