"""把尚未打包的 Agent 核心源码加入 Web 进程导入路径。"""

from pathlib import Path
import sys


def install_agent_source_path() -> Path:
    """注册现有 ``code/agent`` 源码目录并返回仓库根目录。

    Agent 核心目前使用 ``storage``、``runtime`` 等顶层导入且没有独立的
    Python 包元数据。Web 适配层集中在此处理源码路径，避免每个路由各自
    修改 ``sys.path``；核心完成打包后可以整体移除此边界。
    """
    repository_root = Path(__file__).resolve().parents[4]
    agent_source = repository_root / "code" / "agent"
    if str(agent_source) not in sys.path:
        sys.path.insert(0, str(agent_source))
    return repository_root

