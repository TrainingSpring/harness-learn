"""工具调用期间共享、不可变的执行环境。"""

from dataclasses import dataclass, field
from typing import Protocol


class SessionProcessManagerProtocol(Protocol):
    """工具访问的最小 Session 进程协作接口，避免上下文反向依赖实现。"""

    def stop_all(self) -> None: ...


@dataclass(frozen=True)
class ExecutionContext:
    """描述一次 Agent 会话中工具运行所需的环境信息。

    Attributes:
        project_path: 用户为当前 Session 选择的项目目录；为空时不能执行项目工具。
        agent_id: 稳定的逻辑 Agent 标识，用于执行记录，不参与授权归属。
        session_id: 当前交互会话标识。
        max_tool_call_length: 单次工具文本输出允许返回给模型的最大字符数。
        max_read_lines: 单次文本读取允许返回的最大行片段数。
        max_directory_entries: 单次目录读取允许返回的最大条目数。
        max_image_bytes: 单张图片允许读入内存的最大字节数。
        max_write_bytes: 单次文本文件允许写入的最大 UTF-8 字节数。
        max_edit_source_bytes: Edit 完整读取源文本时允许的最大字节数。
        max_edit_operations: 单次 Edit 调用允许的最大替换条数。
        file_mutation_lock_timeout_seconds: 等待同进程文件提交锁的最长秒数。
        max_bash_command_chars: 单次前台 Shell 命令最大字符数。
        default_bash_timeout_seconds: 前台 Shell 命令未指定 timeout 时的默认秒数。
        max_bash_timeout_seconds: 前台 Shell 命令允许请求的最大秒数。
        max_bash_output_bytes: 单次前台命令每个输出流的本地字节上限。
        process_manager: 当前打开 Session 的非持久化后台进程管理器。
        max_process_log_bytes: 每个后台进程单个输出流的环形日志上限。
        max_process_log_return_chars: 单次日志 Tool 返回给模型的最大字符数。
        process_startup_probe_seconds: 启动后台进程后的短暂状态检查秒数。
    """

    project_path: str | None
    agent_id: str
    session_id: str
    max_tool_call_length: int = 20_000
    max_read_lines: int = 1_000
    max_directory_entries: int = 500
    max_image_bytes: int = 10 * 1024 * 1024
    max_write_bytes: int = 2 * 1024 * 1024
    max_edit_source_bytes: int = 2 * 1024 * 1024
    max_edit_operations: int = 100
    file_mutation_lock_timeout_seconds: float = 5.0
    max_bash_command_chars: int = 8_000
    default_bash_timeout_seconds: float = 30.0
    max_bash_timeout_seconds: float = 600.0
    max_bash_output_bytes: int = 256 * 1024
    process_manager: SessionProcessManagerProtocol | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    max_process_log_bytes: int = 4 * 1024 * 1024
    max_process_log_return_chars: int = 20_000
    process_startup_probe_seconds: float = 0.2

    def __post_init__(self) -> None:
        """尽早拒绝缺少身份或非法项目目录的执行上下文。"""
        if self.project_path is not None and not self.project_path:
            raise ValueError("project_path 必须是非空路径或 None")
        if not self.agent_id:
            raise ValueError("agent_id 不能为空")
        if not self.session_id:
            raise ValueError("session_id 不能为空")
        if self.max_tool_call_length <= 0:
            raise ValueError("max_tool_call_length 必须大于 0")
        if self.max_read_lines <= 0:
            raise ValueError("max_read_lines 必须大于 0")
        if self.max_directory_entries <= 0:
            raise ValueError("max_directory_entries 必须大于 0")
        if self.max_image_bytes <= 0:
            raise ValueError("max_image_bytes 必须大于 0")
        if self.max_write_bytes <= 0:
            raise ValueError("max_write_bytes 必须大于 0")
        if self.max_edit_source_bytes <= 0:
            raise ValueError("max_edit_source_bytes 必须大于 0")
        if self.max_edit_operations <= 0:
            raise ValueError("max_edit_operations 必须大于 0")
        if self.file_mutation_lock_timeout_seconds <= 0:
            raise ValueError("file_mutation_lock_timeout_seconds 必须大于 0")
        if self.max_bash_command_chars <= 0:
            raise ValueError("max_bash_command_chars 必须大于 0")
        if self.default_bash_timeout_seconds <= 0:
            raise ValueError("default_bash_timeout_seconds 必须大于 0")
        if self.max_bash_timeout_seconds <= 0:
            raise ValueError("max_bash_timeout_seconds 必须大于 0")
        if self.default_bash_timeout_seconds > self.max_bash_timeout_seconds:
            raise ValueError("default_bash_timeout_seconds 不能超过 max_bash_timeout_seconds")
        if self.max_bash_output_bytes <= 0:
            raise ValueError("max_bash_output_bytes 必须大于 0")
        if self.max_process_log_bytes <= 0:
            raise ValueError("max_process_log_bytes 必须大于 0")
        if self.max_process_log_return_chars <= 0:
            raise ValueError("max_process_log_return_chars 必须大于 0")
        if self.process_startup_probe_seconds <= 0:
            raise ValueError("process_startup_probe_seconds 必须大于 0")
