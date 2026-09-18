import json
import os
import sys
from pathlib import Path

# 支持直接执行 `python code/cli/main.py`。
AGENT_PATH = Path(__file__).resolve().parents[1] / "agent"
if str(AGENT_PATH) not in sys.path:
    sys.path.insert(0, str(AGENT_PATH))

from context.context import Context
from head.llm import LLM
from head.types import LLMConfig
from permission.types import (
    PermissionDecision,
    PermissionMode,
    PermissionResponse,
    PermissionScope,
)
from runtime.agent import Agent as StableAgent
from session.session_agent_factory import SessionAgentRuntimeFactory
from runtime.runtime import PermissionRequiredEvent, Runtime
from storage.ids import generate_id
from storage.types import AgentProfile, SessionAgent
from tools.catalog import ToolCatalog

def print_help():
    print("可用命令:")
    print("  /help   查看帮助")
    print("  /exit   退出")
    print("  /clear  清空当前会话上下文")
    print("  /tools  查看已注册工具")
    print("  /resume 恢复历史会话")


def _read_key():
    """读取一个按键，并将方向键转换成统一的命令名。"""
    if os.name == "nt":
        import msvcrt
        import time

        key = msvcrt.getch()
        if key in (b"\x00", b"\xe0"):
            key = msvcrt.getch()
            return {b"H": "up", b"P": "down"}.get(key, "")
        if key == b"\x1b":
            # Windows Terminal / IDE terminals send ESC [ A/B or ESC O A/B.
            # getch() reads the bytes directly, so the terminal cannot consume
            # the sequence as its own history-navigation event.
            sequence = b""
            deadline = time.monotonic() + 0.2
            while time.monotonic() < deadline and len(sequence) < 2:
                if msvcrt.kbhit():
                    sequence += msvcrt.getch()
                else:
                    time.sleep(0.005)
            return {b"[A": "up", b"[B": "down", b"OA": "up", b"OB": "down"}.get(sequence, "escape")
        if key in (b"\r", b"\n"):
            return "enter"
        return key.decode(errors="ignore")

    import tty
    import termios

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        key = sys.stdin.read(1)
        if key == "\x1b":
            sequence = sys.stdin.read(2)
            return {"\x1b[A": "up", "\x1b[B": "down"}.get(key + sequence, "escape")
        if key in ("\r", "\n"):
            return "enter"
        return key
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _record_context_text(context: Context):
    lines = []
    for index, message in enumerate(context.messages, start=1):
        role = message.get("role", "unknown")
        message_type = message.get("type", "")
        content = message.get("content", message.get("output", ""))
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text", item.get("output", item))))
                else:
                    parts.append(str(item))
            content = "\n".join(parts)
        elif isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False)
        lines.append(f"[{index}] {role}/{message_type}\n{content}")
    return "\n\n".join(lines) or "(暂无上下文)"


def _show_context(context: Context):
    print("\n--- 已加载上下文 ---")
    print(_record_context_text(context))
    print("--- 上下文结束 ---")


def render_event(event):
    event_type = event.type

    if event_type == "text":
        print(event.text, end="", flush=True)

    elif event_type == "reasoning":
        print(f"{event.text}", end="",flush=True)
    elif event_type == "reasoning_summary":
        print(f"\n[reasoning_summary] {event.text}")

    elif event_type == "function_call":
        print(f"\n[tool] {event.name}({event.arguments})")

    elif event_type == "permission_required":
        render_permission_request(event)

    elif event_type == "error":
        print(f"\n[error] {event.message}")

    elif event_type == "done" and event.is_stop:
        # write_record(agent)
        print("[finished]")


def render_permission_request(event: PermissionRequiredEvent):
    """向用户展示一次待确认的权限请求。

    Args:
        event: Runtime 产生的权限请求事件，包含动作、工具和真实资源。

    CLI 展示的是 PermissionRequest.resource，而不是模型传入的相对路径，
    这样用户确认的是工具实际准备访问的位置。
    """
    request = event.request
    print("\n[permission required]")
    print(f"工具: {request.tool_name}")
    print(f"动作: {request.action.value}")
    print(f"资源: {request.resource or '(命令执行，无单一文件资源)'}")


def read_permission_response(event: PermissionRequiredEvent) -> PermissionResponse:
    """读取用户的权限选择并转换为 Runtime 的稳定响应对象。

    Args:
        event: 当前待确认权限事件，用于绑定 call_id。

    Returns:
        只包含 allow/deny、scope 和原 call_id 的 PermissionResponse。

    非法输入会循环询问；没有默认放行分支，避免回车或未知字符意外授予权限。
    """
    options = {
        "1": (PermissionDecision.ALLOW, PermissionScope.ONCE),
        "2": (PermissionDecision.ALLOW, PermissionScope.SESSION),
        "3": (PermissionDecision.ALLOW, PermissionScope.AGENT),
        "4": (PermissionDecision.DENY, PermissionScope.ONCE),
        "5": (PermissionDecision.DENY, PermissionScope.SESSION),
        "6": (PermissionDecision.DENY, PermissionScope.AGENT),
    }
    print("1. 允许本次  2. 当前会话允许  3. 当前 Agent 允许")
    print("4. 拒绝本次  5. 当前会话拒绝  6. 当前 Agent 拒绝")
    while True:
        choice = input("请选择: ").strip()
        selected = options.get(choice)
        if selected is None:
            print("无效选择，请输入 1-6。")
            continue
        decision, scope = selected
        return PermissionResponse(
            call_id=event.request.call_id,
            decision=decision,
            scope=scope,
        )


def run_agent_events(events, runtime):
    """消费 Agent 事件，并在权限事件处交互后继续消费恢复流。

    Args:
        events: ``runtime.run()`` 或 ``runtime.resolve_permission()`` 返回的事件流。
        runtime: 当前会话的 Runtime，用于接收用户确认并恢复 Agent Loop。

    该函数把 CLI 的交互循环与 Runtime 状态机隔离开：Runtime 只产生事件，
    CLI 只收集输入并转发 PermissionResponse。
    """
    current_events = events
    while True:
        for event in current_events:
            if event.type != "permission_required":
                render_event(event)
                continue
            render_permission_request(event)
            response = read_permission_response(event)
            current_events = runtime.resolve_permission(response)
            break
        else:
            return
BASE_URL = "http://192.168.31.6:18080"
API_KEY = "sk-5c206cdd7da2521f5949d6f78f9f40d1320caf8414eb187423c0e23e0619c8a8"
MODEL = "gpt-5.6-luna"
SYSTEM_PROMPT = "你是一个智能助手，帮助解决问题，实现用户的需求。 "


def build_runtime() -> tuple[Runtime, Context]:
    """为 CLI 创建稳定 Agent 和当前会话的隔离运行时。"""
    agent_id = generate_id("agent")
    session_id = generate_id("session")
    tool_names = ["read", "write"]
    profile = AgentProfile(
        id=agent_id,
        name="CLI Agent",
        description="命令行中的个人 Agent",
        personality="务实",
        expertise=["通用任务"],
        llm_profile_id=generate_id("llm"),
        tools=tool_names,
        permission_mode=PermissionMode.BUILD.value,
    )
    agent = StableAgent(
        agent_id=agent_id,
        profile=profile,
        llm_config=LLMConfig(BASE_URL, API_KEY, MODEL, SYSTEM_PROMPT),
        tool_definitions=tuple(ToolCatalog().get(name) for name in tool_names),
        permission_mode=PermissionMode.BUILD,
        workspace=os.getcwd(),
    )
    member = SessionAgent(session_id, agent_id, "PRIMARY")
    context = Context(
        LLM(BASE_URL, API_KEY, MODEL),
        session_id=session_id,
    )
    runtime = SessionAgentRuntimeFactory().create(agent, member, context)
    return runtime, context


def main():
    runtime, context = build_runtime()
    print("Agent CLI 已启动，输入 /help 查看命令。")

    while True:
        try:
            user_input = input("\n>").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n退出。")
            break

        if not user_input:
            continue

        if user_input == "/exit":
            print("退出。")
            break

        if user_input == "/help":
            print_help()
            continue

        if user_input == "/tools":
            print("已注册工具:")
            for tool in runtime.tools.list:
                print(f"- {tool['name']}")
            continue

        if user_input == "/resume":
            # agent = resume_record(agent)
            continue

        if user_input == "/clear":
            context.messages = []
            print("会话上下文已清空。")
            continue

        try:
            run_agent_events(runtime.run(user_input), runtime)
        except Exception as e:
            print(f"\n[error] {e}")


if __name__ == "__main__":
    main()
    # agent = AgentLoop()
    #
    # agent.register_tools([
    #     read.READ_REGISTER
    # ])
    # agent.eval("read", {
    #     "target_path":"屏幕截图 2026-08-14 221707.png"
    # })
