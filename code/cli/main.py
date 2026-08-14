from loop.loop import AgentLoop
from tools import get_weather,get_location, read

def print_help():
    print("可用命令:")
    print("  /help   查看帮助")
    print("  /exit   退出")
    print("  /clear  清空当前会话上下文")
    print("  /tools  查看已注册工具")


def render_event(event):
    event_type = event.get("type")

    if event_type == "text":
        print(event.get("text", ""), end="", flush=True)

    elif event_type == "reasoning_summary":
        print(f"\n[reasoning] {event.get('text', '')}")

    elif event_type == "function_call":
        print(f"\n[tool] {event.get('name')}({event.get('arguments')})")

    elif event_type == "error":
        print(f"\n[error] {event.get('message', 'unknown error')}")

    elif event_type == "done":
        print()


def main():
    agent = AgentLoop()

    agent.register_tools([
        get_weather.GET_WEATHER_REGISTER,
        get_location.GET_LOCATION_REGISTER,
        read.READ_REGISTER
    ])

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

        if user_input == "/clear":
            agent.message = []
            print("会话上下文已清空。")
            continue

        try:
            for event in agent.run(user_input):
                render_event(event)
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
