import json

from loop.loop import AgentLoop
import os

RECORD_DIR = ".training"


# 写入记录
def write_record(agent:AgentLoop):
    workspace = agent.workspace
    msg = agent.message
    sys_msg = agent.sys_message
    sid = agent.sid
    tools = agent.tools
    content = {"workspace": workspace, "message": msg, "sys_message": sys_msg, "sid": sid, "tools": tools}

    record_dir = os.path.join(workspace, RECORD_DIR)
    config_path = os.path.join(record_dir, f"{sid}.json")
    try:
        os.makedirs(record_dir, exist_ok=True)

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(content, f, ensure_ascii=False)
    except Exception as e:
        raise Exception(f"Error 写入记录 {config_path}: {e}")


# 读取配置agent内容
def read_record(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = json.loads(f.read())
        agent = AgentLoop()
        agent.workspace = content["workspace"]
        agent.message = content["message"]
        agent.sys_message = content["sys_message"]
        agent.sid = content["sid"]

        return agent

    except Exception as e:
        raise Exception(f"Error 读取记录 {path}: {e}")
    pass

# 列出所有记录
def get_record_list(path):
    if not os.path.isdir(path):
        return []
    return sorted(
        item for item in os.listdir(path)
        if item.startswith("sid_") and item.endswith(".json")
        and os.path.isfile(os.path.join(path, item))
    )
