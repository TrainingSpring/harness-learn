import json
import os
import sys
from pathlib import Path

# 支持直接执行 `python code/cli/main.py`。
AGENT_PATH = Path(__file__).resolve().parents[1] / "agent"
if str(AGENT_PATH) not in sys.path:
    sys.path.insert(0, str(AGENT_PATH))

from records import get_record_list, read_record, write_record
from loop.loop import AgentLoop
import tools
from tools import bash  ,edit, read , write

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


def _record_context_text(agent):
    lines = []
    for index, message in enumerate(agent.message, start=1):
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


def _show_context(agent):
    print("\n--- 已加载上下文 ---")
    print(_record_context_text(agent))
    print("--- 上下文结束 ---")


def resume_record(current_agent):
    record_dir = os.path.join(current_agent.workspace, ".training")
    records = get_record_list(record_dir)
    if not records:
        print("暂无历史记录。")
        return current_agent

    selected = 0
    while True:
        print("\033[2J\033[H", end="")
        print("选择要恢复的会话（上下键选择，回车确认，Esc取消）：\n")
        for index, record in enumerate(records):
            marker = ">" if index == selected else " "
            print(f"{marker} {record}")

        key = _read_key()
        if key == "up":
            selected = (selected - 1) % len(records)
        elif key == "down":
            selected = (selected + 1) % len(records)
        elif key == "enter":
            print("=======record_dir=========  "+record_dir)
            print(f"=======selected=========  {selected}")
            print(f"=======records=========  {records}")
            try:
                loaded_agent = read_record(os.path.join(record_dir, records[selected]))
                loaded_agent.tools = []
                loaded_agent.tools_map = {}
                loaded_agent.register_tools([
                    write.REGISTER,
                    read.REGISTER,
                    edit.REGISTER,
                    bash.REGISTER,
                ])
                print("\n会话加载成功。")
                _show_context(loaded_agent)
                return loaded_agent
            except Exception as error:
                print(f"\n加载记录失败：{error}")
                return current_agent
        elif key == "escape":
            print("\n已取消恢复。")
            return current_agent


def render_event(event,agent):
    event_type = event.get("type")

    if event_type == "text":
        print(event.get("text", ""), end="", flush=True)

    elif event_type == "reasoning":
        print(f"{event.get('text', '')}", end="",flush=True)
    elif event_type == "reasoning_summary":
        print(f"\n[reasoning_summary] {event.get('text', '')}")

    elif event_type == "function_call":
        print(f"\n[tool] {event.get('name')}({event.get('arguments')})")

    elif event_type == "error":
        print(f"\n[error] {event.get('message', 'unknown error')}")

    elif event_type == "done" and event.get("is_stop"):
        write_record(agent)
        print("[finished]")


def main():
    agent = AgentLoop()
    agent = read_record(os.path.join(agent.workspace,".training","sid_e8317d01f81f20abcc5cd51c.json"))
    agent.register_tools([
        write.REGISTER,
        read.REGISTER,
        edit.REGISTER,
        bash.REGISTER
    ])

    _show_context(agent)
    # agent.compact_context()
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
            for tool in agent.tools:
                print(f"- {tool.get('name')}")
            continue

        if user_input == "/resume":
            agent = resume_record(agent)
            continue

        if user_input == "/clear":
            agent.message = []
            print("会话上下文已清空。")
            continue

        try:
            for event in agent.run(user_input):
                render_event(event,agent)
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
